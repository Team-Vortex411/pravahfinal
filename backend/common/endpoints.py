from datetime import date, timedelta

from django.contrib.auth import authenticate
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from accounts.models import Department, User
from applications.models import Application
from common.access import can_view_application, can_view_document, can_view_pilot, require
from common.audit import audit, notify
from common.present import (
    application_data,
    complaint_data,
    department,
    document_data,
    evaluation_data,
    notification_data,
    person,
    pilot_data,
    problem_data,
    startup_data,
    visible_notifications,
)
from complaints.models import Complaint
from documents.models import Document
from documents.services import apply_expiry_state, scan_expiries
from embeddings.services import recommendations_for_startup, similar_startups_for_problem, upsert_problem_embedding, upsert_startup_embedding
from evaluations.models import Evaluation
from notifications.models import AuditLog
from notifications.services import build_alerts
from pilots.models import Pilot
from problem_statements.models import ProblemStatement
from startups.models import Startup

SCORE_FIELDS = [
    "technical_feasibility",
    "innovation",
    "problem_relevance",
    "scalability",
    "technical_capability",
    "relevant_experience",
]


def _next(prefix, model):
    return f"{prefix}-{timezone.now().year}-{model.objects.count() + 1:04d}"


@api_view(["GET"])
def health(request):
    from django.conf import settings

    db = "ok"
    try:
        User.objects.exists()
    except Exception as exc:
        db = str(exc)
    return Response(
        {
            "status": "ok" if db == "ok" else "degraded",
            "demo_mode": settings.DEMO_MODE,
            "services": {
                "database": db,
                "object_storage": "neon" if settings.OBJECT_STORAGE_ENDPOINT else "local",
                "embeddings": settings.EMBEDDING_MODEL,
                "pgvector": settings.USE_PGVECTOR,
                "qwen": "configured" if settings.QWEN_API_URL else "demo-fallback",
                "qwen_model": settings.QWEN_MODEL,
            },
        }
    )


@api_view(["GET"])
def meta(request):
    from django.conf import settings

    return Response(
        {
            "name": "PRAVAH",
            "principle": "AI assists → Rules check → Humans verify → Government decides",
            "disclaimer": "Final award rests with the competent government authority.",
            "demo_mode": settings.DEMO_MODE,
            "roles": [{"value": k, "label": v} for k, v in User.Role.choices],
            "document_types": [{"value": k, "label": v} for k, v in Document.Type.choices],
            "application_statuses": [k for k, _ in Application.Status.choices],
            "departments": [department(d) for d in Department.objects.all()],
            "score_fields": SCORE_FIELDS,
            "illustrative": {
                "problem_statements": 8,
                "applications": 42,
                "active_pilots": 5,
                "pending_evaluations": 11,
            },
            "live": {
                "problem_statements": ProblemStatement.objects.count(),
                "applications": Application.objects.count(),
                "active_pilots": Pilot.objects.filter(status=Pilot.Status.ACTIVE).count(),
                "pending_evaluations": Application.objects.filter(status=Application.Status.UNDER_TECHNICAL_EVALUATION).count(),
                "expiring_documents": Document.objects.filter(verification_status=Document.Verification.EXPIRING_SOON).count(),
                "startups": Startup.objects.count(),
            },
        }
    )


@api_view(["GET"])
def demo_accounts(request):
    featured = []
    for email, blurb in [
        ("admin@gov.in", "Create problem statements, assign officers, watch alerts."),
        ("evaluator@gov.in", "Verify documents and record a technical decision."),
        ("procurement@gov.in", "Configure KPIs, contracts, complaints and recommendations."),
        ("field@gov.in", "Verify weekly evidence. Your name is hidden from startups."),
        ("nova@novatech.in", "NovaTech — Arjun Malhotra. Recommendations, pilot and report."),
    ]:
        user = User.objects.filter(email=email).first()
        if user:
            featured.append(
                {
                    "email": email,
                    "password": "demo123",
                    "name": user.display_name,
                    "role": user.role,
                    "role_label": user.get_role_display(),
                    "blurb": blurb,
                }
            )
    others = []
    for user in User.objects.filter(role=User.Role.STARTUP).exclude(email="nova@novatech.in").select_related("startup")[:8]:
        others.append(
            {
                "email": user.email,
                "password": "demo123",
                "name": user.startup.company_name if hasattr(user, "startup") else user.display_name,
                "role": user.role,
                "role_label": "Startup",
            }
        )
    return Response({"password": "demo123", "featured": featured, "startups": others})


@api_view(["POST"])
def login(request):
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password") or ""
    user = authenticate(request, email=email, password=password)
    if not user:
        user = User.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(password):
            return Response({"detail": "Email or password is not recognised."}, status=400)
    token, _ = Token.objects.get_or_create(user=user)
    audit(user, "login", "user", user.id)
    return Response({"token": token.key, "user": person(user) | _startup_extra(user)})


def _startup_extra(user):
    extra = {"startup": None}
    if user.role == User.Role.STARTUP and hasattr(user, "startup"):
        extra["startup"] = startup_data(user.startup, detailed=True)
    extra["role_label"] = user.get_role_display()
    extra["name"] = user.display_name
    return extra


@api_view(["POST"])
def logout(request):
    user, error = require(request)
    if error:
        return error
    Token.objects.filter(user=user).delete()
    return Response({"ok": True})


@api_view(["GET"])
def me(request):
    user, error = require(request)
    if error:
        return error
    payload = person(user)
    payload.update(_startup_extra(user))
    return Response(payload)


@api_view(["POST"])
def register(request):
    data = request.data
    required = ["email", "password", "company_name", "domain", "technologies", "city", "state", "contact_person"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        return Response({"detail": "Missing fields: " + ", ".join(missing)}, status=400)
    email = data["email"].strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        return Response({"detail": "An account with this email already exists."}, status=400)
    user = User.objects.create_user(
        username=email,
        email=email,
        password=data["password"],
        first_name=(data.get("contact_person") or "").split(" ")[0],
        last_name=" ".join((data.get("contact_person") or "").split(" ")[1:]),
        role=User.Role.STARTUP,
    )
    startup = Startup.objects.create(
        user=user,
        company_name=data["company_name"],
        domain=data["domain"],
        technologies=data["technologies"],
        dpiit_number=data.get("dpiit_number") or "",
        gstin=data.get("gstin") or "",
        city=data["city"],
        state=data["state"],
        experience_years=int(data.get("experience_years") or 0),
        team_size=int(data.get("team_size") or 1),
        description=data.get("description") or "",
        capabilities=data.get("capabilities") or data.get("description") or "",
        relevant_experience=data.get("relevant_experience") or "",
        contact_person=data["contact_person"],
    )
    upsert_startup_embedding(startup)
    token, _ = Token.objects.get_or_create(user=user)
    audit(user, "register", "startup", startup.id, startup.company_name)
    payload = person(user)
    payload.update(_startup_extra(user))
    return Response({"token": token.key, "user": payload}, status=201)


@api_view(["GET", "POST"])
def employees(request):
    user, error = require(request, User.Role.GOVERNMENT_ADMIN, User.Role.PROCUREMENT_OFFICER)
    if error:
        return error
    if request.method == "GET":
        qs = User.objects.exclude(role=User.Role.STARTUP).select_related("department")
        return Response([person(item) for item in qs])
    if user.role != User.Role.GOVERNMENT_ADMIN:
        return Response({"detail": "Only a government administrator can add an employee."}, status=403)
    data = request.data
    email = (data.get("email") or "").strip().lower()
    if not email or not data.get("name") or not data.get("role"):
        return Response({"detail": "Name, email and role are required."}, status=400)
    if data["role"] not in dict(User.Role.choices) or data["role"] == User.Role.STARTUP:
        return Response({"detail": "Choose a government role."}, status=400)
    if User.objects.filter(email__iexact=email).exists():
        return Response({"detail": "Email already in use."}, status=400)
    parts = data["name"].split()
    dept = Department.objects.filter(id=data.get("department_id")).first()
    created = User.objects.create_user(
        username=email,
        email=email,
        password=data.get("password") or "demo123",
        first_name=parts[0],
        last_name=" ".join(parts[1:]),
        role=data["role"],
        designation=data.get("designation") or "",
        employee_id=data.get("employee_id") or "",
        phone=data.get("phone") or "",
        department=dept,
    )
    audit(user, "create_employee", "user", created.id, email)
    return Response(person(created), status=201)


@api_view(["GET", "POST"])
def problem_list(request):
    if request.method == "GET":
        qs = ProblemStatement.objects.select_related("department", "technical_evaluator", "procurement_officer").annotate(
            application_count=Count("applications")
        )
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(code__icontains=q) | Q(technology_domain__icontains=q) | Q(location__icontains=q))
        viewer = getattr(request, "user", None)
        include_internal = bool(viewer and getattr(viewer, "is_authenticated", False) and viewer.role != User.Role.STARTUP)
        startup = None
        applied = set()
        if viewer and getattr(viewer, "is_authenticated", False) and viewer.role == User.Role.STARTUP and hasattr(viewer, "startup"):
            startup = viewer.startup
            applied = set(startup.applications.values_list("problem_statement_id", flat=True))
        rows = []
        for ps in qs:
            match = None
            if startup and ps.id not in applied:
                from embeddings.services import score_pair

                match = score_pair(startup, ps)
            rows.append(problem_data(ps, match=match, include_internal=include_internal))
        return Response(rows)
    user, error = require(request, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    data = request.data
    required = ["title", "description", "department_id", "location", "technology_domain", "expected_outcome", "application_deadline", "pilot_joining_deadline", "pilot_location"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        return Response({"detail": "Missing fields: " + ", ".join(missing)}, status=400)
    dept = Department.objects.filter(id=data.get("department_id")).first()
    if not dept:
        return Response({"detail": "Department not found."}, status=400)
    ps = ProblemStatement.objects.create(
        code=_next("PS", ProblemStatement),
        title=data["title"],
        description=data["description"],
        department=dept,
        location=data["location"],
        technology_domain=data["technology_domain"],
        expected_outcome=data["expected_outcome"],
        technical_requirements=_as_list(data.get("technical_requirements")),
        eligibility_criteria=_as_list(data.get("eligibility_criteria")),
        required_documents=_as_list(data.get("required_documents")) or ["DPIIT", "GST", "PAN", "TECHNICAL_PROPOSAL"],
        application_deadline=data["application_deadline"],
        pilot_joining_deadline=data["pilot_joining_deadline"],
        pilot_location=data["pilot_location"],
        pilot_duration_weeks=int(data.get("pilot_duration_weeks") or 12),
        technical_evaluator_id=data.get("technical_evaluator") or None,
        procurement_officer_id=data.get("procurement_officer") or None,
        created_by=user,
    )
    upsert_problem_embedding(ps)
    audit(user, "create_problem", "problem", ps.id, ps.title)
    notify("New problem statement", ps.title, category="PROBLEM", link=f"/startup/problem-statements/{ps.id}", role=User.Role.STARTUP)
    ps.application_count = 0
    return Response(problem_data(ps, include_internal=True), status=201)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [line.strip() for line in value.split("\n") if line.strip()]
    return []


@api_view(["GET", "PATCH"])
def problem_detail(request, pk):
    ps = ProblemStatement.objects.select_related("department", "technical_evaluator", "procurement_officer").filter(id=pk).first()
    if not ps:
        return Response({"detail": "Problem statement not found."}, status=404)
    viewer = getattr(request, "user", None)
    include_internal = bool(viewer and getattr(viewer, "is_authenticated", False) and viewer.role not in {User.Role.STARTUP, None})
    if request.method == "GET":
        match = None
        if viewer and getattr(viewer, "is_authenticated", False) and viewer.role == User.Role.STARTUP and hasattr(viewer, "startup"):
            from embeddings.services import score_pair

            if not viewer.startup.applications.filter(problem_statement=ps).exists():
                match = score_pair(viewer.startup, ps)
        ps.application_count = ps.applications.count()
        payload = problem_data(ps, match=match, include_internal=include_internal)
        if include_internal:
            payload["similar_startups"] = [
                {"startup": startup_data(startup), "match": match}
                for _score, startup, match in similar_startups_for_problem(ps, limit=5)
            ]
            payload["applications"] = [
                application_data(app, viewer)
                for app in ps.applications.select_related("startup", "problem_statement__department")
            ]
        return Response(payload)
    user, error = require(request, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    data = request.data
    for field in ["title", "description", "location", "technology_domain", "expected_outcome", "pilot_location", "status"]:
        if field in data:
            setattr(ps, field, data[field])
    for field in ["technical_requirements", "eligibility_criteria", "required_documents"]:
        if field in data:
            setattr(ps, field, _as_list(data[field]))
    for field in ["application_deadline", "pilot_joining_deadline"]:
        if data.get(field):
            setattr(ps, field, data[field])
    if data.get("pilot_duration_weeks"):
        ps.pilot_duration_weeks = int(data["pilot_duration_weeks"])
    if data.get("department_id"):
        ps.department = Department.objects.get(id=data["department_id"])
    ps.save()
    upsert_problem_embedding(ps)
    audit(user, "update_problem", "problem", ps.id)
    ps.application_count = ps.applications.count()
    return Response(problem_data(ps, include_internal=True))


@api_view(["POST"])
def problem_assign(request, pk):
    user, error = require(request, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    ps = ProblemStatement.objects.filter(id=pk).first()
    if not ps:
        return Response({"detail": "Problem statement not found."}, status=404)
    if "technical_evaluator" in request.data:
        ps.technical_evaluator_id = request.data.get("technical_evaluator") or None
    if "procurement_officer" in request.data:
        ps.procurement_officer_id = request.data.get("procurement_officer") or None
    ps.save()
    audit(user, "assign_problem", "problem", ps.id)
    if ps.technical_evaluator_id:
        notify("Problem statement assigned", ps.title, category="ASSIGNMENT", link=f"/evaluator/applications", recipient=ps.technical_evaluator)
    if ps.procurement_officer_id:
        notify("Problem statement assigned", ps.title, category="ASSIGNMENT", link="/procurement/dashboard", recipient=ps.procurement_officer)
    ps.application_count = ps.applications.count()
    return Response(problem_data(ps, include_internal=True))


@api_view(["GET"])
def startup_matches(request):
    user, error = require(request, User.Role.STARTUP)
    if error:
        return error
    startup = user.startup
    exclude = startup.applications.values_list("problem_statement_id", flat=True)
    ranked = recommendations_for_startup(startup, limit=6, exclude_ids=exclude)
    return Response(
        [
            problem_data(ps, match=match)
            for _score, ps, match in ranked
        ]
    )


@api_view(["GET", "PATCH"])
def startup_list(request):
    user, error = require(request)
    if error:
        return error
    if request.method == "GET":
        if user.role == User.Role.STARTUP:
            return Response([startup_data(user.startup, detailed=True)])
        qs = Startup.objects.select_related("user")
        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(company_name__icontains=q) | Q(domain__icontains=q) | Q(city__icontains=q) | Q(dpiit_number__icontains=q))
        return Response([startup_data(item, detailed=True) for item in qs])
    if user.role != User.Role.STARTUP:
        return Response({"detail": "Only a startup can edit this profile."}, status=403)
    startup = user.startup
    data = request.data
    for field in ["company_name", "domain", "technologies", "dpiit_number", "gstin", "city", "state", "description", "capabilities", "relevant_experience", "contact_person"]:
        if field in data:
            setattr(startup, field, data[field])
    if "experience_years" in data:
        startup.experience_years = int(data["experience_years"] or 0)
    if "team_size" in data:
        startup.team_size = int(data["team_size"] or 1)
    startup.save()
    if data.get("contact_person"):
        parts = data["contact_person"].split()
        user.first_name = parts[0]
        user.last_name = " ".join(parts[1:])
        user.save(update_fields=["first_name", "last_name"])
    upsert_startup_embedding(startup)
    audit(user, "update_startup", "startup", startup.id)
    return Response(startup_data(startup, detailed=True))


@api_view(["GET"])
def startup_detail(request, pk):
    user, error = require(request)
    if error:
        return error
    startup = Startup.objects.filter(id=pk).first()
    if not startup:
        return Response({"detail": "Startup not found."}, status=404)
    if user.role == User.Role.STARTUP and startup.user_id != user.id:
        return Response({"detail": "You cannot open another startup's profile."}, status=403)
    payload = startup_data(startup, detailed=True)
    if user.role != User.Role.STARTUP:
        payload["applications"] = [application_data(app, user) for app in startup.applications.select_related("problem_statement__department")]
        payload["documents"] = [document_data(doc, user) for doc in startup.documents.all()[:20]]
    return Response(payload)
