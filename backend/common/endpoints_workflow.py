from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from accounts.models import User
from ai import orchestrator
from applications.models import Application
from common.access import can_view_application, can_view_document, can_view_pilot, require
from common.audit import audit, notify
from common.present import (
    application_data,
    complaint_data,
    document_data,
    evaluation_data,
    notification_data,
    official_score,
    pilot_data,
    recommendation_data,
    startup_data,
    visible_notifications,
)
from complaints.models import Complaint
from documents.models import Document
from documents.services import apply_expiry_state, scan_expiries
from evaluations.models import Evaluation
from notifications.models import AuditLog
from notifications.services import build_alerts
from pilots.models import Contract, Pilot
from pilots.services import WorkflowError, refresh_score_cache, replace_kpis, replace_milestones, write_unsigned_contract
from problem_statements.models import ProblemStatement
from recommendations.models import Recommendation
from reports.models import FieldVerification, FinalReport, WeeklyKPIResult, WeeklyReport
from storage.services import StorageError, delete_object, extract_text_from_bytes, open_object, put_upload, read_bytes

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


def _bad(exc, status=400):
    return Response({"detail": str(exc)}, status=status)


@api_view(["GET", "POST"])
def application_list(request):
    user, error = require(request)
    if error:
        return error
    if request.method == "GET":
        qs = Application.objects.select_related("startup", "problem_statement__department")
        if user.role == User.Role.STARTUP:
            qs = qs.filter(startup__user=user)
        elif user.role == User.Role.TECHNICAL_EVALUATOR:
            qs = qs.filter(problem_statement__technical_evaluator=user)
        elif user.role == User.Role.PROCUREMENT_OFFICER:
            qs = qs.filter(problem_statement__procurement_officer=user)
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return Response([application_data(app, user) for app in qs])
    if user.role != User.Role.STARTUP:
        return Response({"detail": "Only a startup can apply."}, status=403)
    data = request.data
    ps = ProblemStatement.objects.filter(id=data.get("problem_statement")).first()
    if not ps:
        return Response({"detail": "Problem statement not found."}, status=404)
    if ps.status not in {ProblemStatement.Status.OPEN, ProblemStatement.Status.PILOT_ACTIVE}:
        return Response({"detail": "This problem statement is not open for applications."}, status=400)
    if timezone.localdate() > ps.application_deadline:
        return Response({"detail": "The application deadline has passed."}, status=400)
    if Application.objects.filter(startup=user.startup, problem_statement=ps).exists():
        return Response({"detail": "You already have an application for this problem statement."}, status=400)
    readiness = (data.get("pilot_readiness") or "").upper()
    if readiness not in {"YES", "NO"}:
        return Response({"detail": "Confirm whether you can be ready by the pilot joining deadline."}, status=400)
    if not data.get("eligibility_confirmed"):
        return Response({"detail": "Eligibility must be confirmed before submission."}, status=400)
    app = Application.objects.create(
        code=_next("APP", Application),
        startup=user.startup,
        problem_statement=ps,
        eligibility_confirmed=True,
        eligibility_checks=data.get("eligibility_checks") or {},
        pilot_readiness=readiness,
        proposal_text=data.get("proposal_text") or "",
        status=Application.Status.SUBMITTED,
    )
    for doc_id in data.get("document_ids") or []:
        doc = Document.objects.filter(id=doc_id, startup=user.startup).first()
        if doc:
            if doc.document_type == Document.Type.TECHNICAL_PROPOSAL:
                doc.application = app
                doc.save(update_fields=["application"])
            app.documents.add(doc)
    if readiness == "NO":
        app.status = Application.Status.REJECTED_DEADLINE
        app.rejection_reason = "REJECTED — CANNOT MEET PILOT DEADLINE"
        app.save(update_fields=["status", "rejection_reason"])
        audit(user, "apply_rejected_deadline", "application", app.id)
        notify(
            "Application closed",
            "REJECTED — CANNOT MEET PILOT DEADLINE. This application cannot continue.",
            category="APPLICATION",
            link=f"/startup/applications/{app.id}",
            recipient=user,
        )
        return Response(application_data(app, user, detailed=True), status=201)
    app.status = Application.Status.ELIGIBILITY_CHECK
    required = set(ps.required_documents or [])
    attached_types = set(app.documents.values_list("document_type", flat=True))
    if required and required.issubset(attached_types | {"SOLUTION"}):
        app.status = Application.Status.UNDER_TECHNICAL_EVALUATION
    app.save(update_fields=["status"])
    _run_proposal_analysis(app)
    audit(user, "apply", "application", app.id, ps.title)
    if ps.technical_evaluator_id:
        notify("New application", f"{user.startup.company_name} applied to {ps.title}.", category="APPLICATION", link=f"/evaluator/applications/{app.id}", recipient=ps.technical_evaluator)
    notify("Application submitted", f"{app.code} is now {app.get_status_display()}.", category="APPLICATION", link=f"/startup/applications/{app.id}", recipient=user)
    return Response(application_data(app, user, detailed=True), status=201)


def _run_proposal_analysis(app):
    ps = app.problem_statement
    startup = app.startup
    docs = ", ".join(f"{d.get_document_type_display()} ({d.verification_status})" for d in app.documents.all())
    result = orchestrator.analyze_proposal(
        {
            "title": ps.title,
            "department": ps.department.name,
            "description": ps.description,
            "technical_requirements": ps.technical_requirements,
            "expected_outcome": ps.expected_outcome,
        },
        startup_data(startup, detailed=True),
        app.proposal_text,
        docs,
    )
    app.ai_analysis = result
    app.save(update_fields=["ai_analysis"])
    return result


@api_view(["GET"])
def application_detail(request, pk):
    user, error = require(request)
    if error:
        return error
    app = (
        Application.objects.select_related("startup__user", "problem_statement__department", "problem_statement__technical_evaluator", "evaluation")
        .filter(id=pk)
        .first()
    )
    if not app:
        return Response({"detail": "Application not found."}, status=404)
    if not can_view_application(user, app):
        return Response({"detail": "You cannot access this application."}, status=403)
    return Response(application_data(app, user, detailed=True))


@api_view(["POST"])
def application_eligibility(request, pk):
    user, error = require(request, User.Role.GOVERNMENT_ADMIN, User.Role.TECHNICAL_EVALUATOR)
    if error:
        return error
    app = Application.objects.filter(id=pk).first()
    if not app or not can_view_application(user, app):
        return Response({"detail": "Application not found."}, status=404)
    app.eligibility_checks = request.data.get("checks") or app.eligibility_checks
    app.eligibility_confirmed = bool(request.data.get("confirmed", True))
    if app.status == Application.Status.SUBMITTED:
        app.status = Application.Status.ELIGIBILITY_CHECK
    note = request.data.get("note") or ""
    if request.data.get("fail"):
        app.status = Application.Status.REJECTED
        app.rejection_reason = note or "Eligibility criteria were not met."
    app.save()
    audit(user, "eligibility", "application", app.id, app.status)
    return Response(application_data(app, user, detailed=True))


@api_view(["POST"])
def clarification_response(request, pk):
    user, error = require(request, User.Role.STARTUP)
    if error:
        return error
    app = Application.objects.filter(id=pk, startup__user=user).first()
    if not app:
        return Response({"detail": "Application not found."}, status=404)
    text = (request.data.get("response") or "").strip()
    if not text:
        return Response({"detail": "Write a clarification response."}, status=400)
    app.clarification_response = text
    if app.status == Application.Status.CLARIFICATION_REQUIRED:
        app.status = Application.Status.UNDER_TECHNICAL_EVALUATION
    app.save()
    if app.problem_statement.technical_evaluator_id:
        notify(
            "Clarification received",
            f"{app.startup.company_name} responded on {app.code}.",
            category="CLARIFICATION",
            link=f"/evaluator/applications/{app.id}",
            recipient=app.problem_statement.technical_evaluator,
        )
    audit(user, "clarification_response", "application", app.id)
    return Response(application_data(app, user, detailed=True))


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def document_list(request):
    user, error = require(request)
    if error:
        return error
    if request.method == "GET":
        scan_expiries()
        qs = Document.objects.select_related("startup", "verified_by")
        if user.role == User.Role.STARTUP:
            qs = qs.filter(startup__user=user)
        elif user.role == User.Role.FIELD_EVALUATOR:
            qs = qs.filter(pilot__field_evaluator=user)
        dtype = request.GET.get("type")
        status = request.GET.get("status")
        if dtype:
            qs = qs.filter(document_type=dtype)
        if status:
            qs = qs.filter(verification_status=status)
        return Response([document_data(doc, user) for doc in qs[:200]])
    if "file" not in request.FILES:
        return Response({"detail": "Attach a file."}, status=400)
    uploaded = request.FILES["file"]
    try:
        key = put_upload(uploaded, prefix=f"startups/{user.id}")
    except StorageError as exc:
        return _bad(exc)
    startup = None
    if user.role == User.Role.STARTUP:
        startup = user.startup
    else:
        startup_id = request.data.get("startup_id")
        startup = Startup_lookup(startup_id) if startup_id else None
    replaces = Document.objects.filter(id=request.data.get("replaces") or 0).first()
    if replaces and user.role == User.Role.STARTUP and replaces.startup_id != user.startup.id:
        return Response({"detail": "You cannot replace another startup's document."}, status=403)
    doc = Document.objects.create(
        startup=startup or (replaces.startup if replaces else None),
        application_id=request.data.get("application_id") or None,
        pilot_id=request.data.get("pilot_id") or None,
        name=request.data.get("name") or uploaded.name,
        document_type=request.data.get("document_type") or Document.Type.OTHER,
        object_key=key,
        file_name=uploaded.name,
        content_type=uploaded.content_type or "",
        size_bytes=uploaded.size or 0,
        verification_status=Document.Verification.PENDING_VERIFICATION,
        currently_valid=False,
        replaces=replaces,
        version=(replaces.version + 1) if replaces else 1,
        notes=request.data.get("notes") or "",
    )
    if doc.application_id:
        doc.application.documents.add(doc)
    audit(user, "upload_document", "document", doc.id, doc.document_type)
    if startup and startup.user_id != user.id:
        notify("Document uploaded", doc.name, category="DOCUMENT", link="/evaluator/documents", role=User.Role.TECHNICAL_EVALUATOR)
    elif user.role == User.Role.STARTUP:
        notify("Document received for verification", f"{startup.company_name} uploaded {doc.get_document_type_display()}.", category="DOCUMENT", link="/evaluator/documents", role=User.Role.TECHNICAL_EVALUATOR)
    return Response(document_data(doc, user), status=201)


def Startup_lookup(startup_id):
    from startups.models import Startup

    return Startup.objects.filter(id=startup_id).first()


@api_view(["GET"])
def document_detail(request, pk):
    user, error = require(request)
    if error:
        return error
    doc = Document.objects.select_related("startup", "verified_by", "application").filter(id=pk).first()
    if not doc or not can_view_document(user, doc):
        return Response({"detail": "Document not found."}, status=404)
    return Response(document_data(doc, user))


@api_view(["GET"])
def document_download(request, pk):
    user, error = require(request)
    if error:
        return error
    doc = Document.objects.select_related("startup", "application", "pilot").filter(id=pk).first()
    if not doc or not can_view_document(user, doc):
        return Response({"detail": "Document not found."}, status=404)
    audit(user, "download_document", "document", doc.id)
    return open_object(doc.object_key)


@api_view(["PATCH"])
def document_verify(request, pk):
    user, error = require(request, User.Role.TECHNICAL_EVALUATOR, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    doc = Document.objects.select_related("startup__user").filter(id=pk).first()
    if not doc:
        return Response({"detail": "Document not found."}, status=404)
    action = (request.data.get("action") or "").upper()
    doc.notes = request.data.get("notes") or doc.notes
    if action == "VERIFY":
        doc.no_expiry = bool(request.data.get("no_expiry"))
        doc.expiry_date = None if doc.no_expiry else request.data.get("expiry_date") or None
        doc.verified_by = user
        doc.verified_date = timezone.localdate()
        doc.verification_status = Document.Verification.VERIFIED_VALID
        doc.currently_valid = True
        doc.save()
        apply_expiry_state(doc)
        if doc.startup_id:
            notify("Document verified", f"{doc.get_document_type_display()} is {doc.verification_status.replace('_', ' ').title()}.", category="DOCUMENT", link="/startup/documents", recipient=doc.startup.user)
    elif action == "REJECT":
        doc.verification_status = Document.Verification.REJECTED
        doc.currently_valid = False
        doc.verified_by = user
        doc.verified_date = timezone.localdate()
        doc.save()
        if doc.startup_id:
            notify("Document rejected", doc.notes or doc.name, category="DOCUMENT", link="/startup/documents", recipient=doc.startup.user)
    elif action == "CLARIFICATION":
        doc.verification_status = Document.Verification.PENDING_VERIFICATION
        doc.currently_valid = False
        doc.save()
        if doc.startup_id:
            notify("Clarification requested on a document", doc.notes or "Please review the evaluator note and upload a clearer copy.", category="CLARIFICATION", link="/startup/documents", recipient=doc.startup.user)
    else:
        return Response({"detail": "Action must be VERIFY, REJECT or CLARIFICATION."}, status=400)
    audit(user, "verify_document", "document", doc.id, action)
    return Response(document_data(doc, user))


@api_view(["PATCH"])
def document_expiry(request, pk):
    user, error = require(request, User.Role.TECHNICAL_EVALUATOR, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    doc = Document.objects.filter(id=pk).first()
    if not doc:
        return Response({"detail": "Document not found."}, status=404)
    doc.no_expiry = bool(request.data.get("no_expiry"))
    doc.expiry_date = None if doc.no_expiry else request.data.get("expiry_date")
    doc.save()
    apply_expiry_state(doc)
    audit(user, "set_expiry", "document", doc.id, str(doc.expiry_date))
    return Response(document_data(doc, user))


@api_view(["POST"])
def expiry_scan(request):
    user, error = require(request, User.Role.GOVERNMENT_ADMIN, User.Role.TECHNICAL_EVALUATOR)
    if error:
        return error
    changed = scan_expiries()
    return Response({"updated": changed})


@api_view(["GET", "POST"])
def evaluation_list(request):
    user, error = require(request, User.Role.TECHNICAL_EVALUATOR, User.Role.GOVERNMENT_ADMIN, User.Role.PROCUREMENT_OFFICER)
    if error:
        return error
    if request.method == "GET":
        qs = Evaluation.objects.select_related("application__startup", "application__problem_statement", "evaluator")
        if user.role == User.Role.TECHNICAL_EVALUATOR:
            qs = qs.filter(application__problem_statement__technical_evaluator=user)
        return Response(
            [
                evaluation_data(item)
                | {
                    "application_id": item.application_id,
                    "application_code": item.application.code,
                    "startup": item.application.startup.company_name,
                    "problem": item.application.problem_statement.title,
                }
                for item in qs
            ]
        )
    return _save_evaluation(request, user, None)


@api_view(["PATCH"])
def evaluation_detail(request, pk):
    user, error = require(request, User.Role.TECHNICAL_EVALUATOR, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    ev = Evaluation.objects.filter(id=pk).first()
    if not ev:
        return Response({"detail": "Evaluation not found."}, status=404)
    return _save_evaluation(request, user, ev)


def _save_evaluation(request, user, ev):
    data = request.data
    app = None
    if ev:
        app = ev.application
    else:
        app = Application.objects.filter(id=data.get("application")).first()
        if not app:
            return Response({"detail": "Application not found."}, status=404)
        ev, _ = Evaluation.objects.get_or_create(application=app, defaults={"evaluator": user})
    if not can_view_application(user, app):
        return Response({"detail": "You are not assigned to this application."}, status=403)
    scores = data.get("scores") or ev.scores or {}
    clean = {}
    for key in SCORE_FIELDS:
        if key in scores and scores[key] not in ("", None):
            value = float(scores[key])
            if value < 0 or value > 10:
                return Response({"detail": f"{key.replace('_', ' ')} must be between 0 and 10."}, status=400)
            clean[key] = value
    ev.scores = {**ev.scores, **clean}
    if "comments" in data:
        ev.comments = data.get("comments") or ""
    ev.evaluator = user
    decision = data.get("decision")
    if decision:
        if decision not in dict(Evaluation.Decision.choices):
            return Response({"detail": "Decision is not recognised."}, status=400)
        ev.decision = decision
        ev.decided_at = timezone.now()
        if decision == Evaluation.Decision.APPROVE_FOR_PILOT:
            app.status = Application.Status.APPROVED_FOR_PILOT
            notify("Approved for pilot", f"{app.startup.company_name} was approved for a pilot on {app.problem_statement.title}. This is not a procurement award.", category="EVALUATION", link="/procurement/dashboard", role=User.Role.PROCUREMENT_OFFICER)
            notify("Approved for pilot", "A technical evaluator approved your application for pilot. A procurement officer will configure the contract. This is not an automatic award.", category="EVALUATION", link=f"/startup/applications/{app.id}", recipient=app.startup.user)
        elif decision == Evaluation.Decision.REJECT:
            app.status = Application.Status.REJECTED
            app.rejection_reason = data.get("comments") or ev.comments or "Rejected in technical evaluation."
            notify("Application rejected", app.rejection_reason, category="EVALUATION", link=f"/startup/applications/{app.id}", recipient=app.startup.user)
        elif decision == Evaluation.Decision.REQUEST_CLARIFICATION:
            app.status = Application.Status.CLARIFICATION_REQUIRED
            app.clarification_request = data.get("comments") or ev.comments
            notify("Clarification requested", app.clarification_request or "Please respond to the technical clarification.", category="CLARIFICATION", link=f"/startup/applications/{app.id}", recipient=app.startup.user)
        app.save()
    ev.save()
    audit(user, "evaluation", "application", app.id, ev.decision)
    return Response(evaluation_data(ev) | {"application_status": app.status})


@api_view(["GET", "POST"])
def pilot_list(request):
    user, error = require(request)
    if error:
        return error
    if request.method == "GET":
        qs = Pilot.objects.select_related("startup", "problem_statement__department", "application", "field_evaluator", "procurement_officer")
        if user.role == User.Role.STARTUP:
            qs = qs.filter(startup__user=user)
        elif user.role == User.Role.FIELD_EVALUATOR:
            qs = qs.filter(field_evaluator=user)
        elif user.role == User.Role.PROCUREMENT_OFFICER:
            qs = qs.filter(procurement_officer=user)
        elif user.role == User.Role.TECHNICAL_EVALUATOR:
            qs = qs.filter(problem_statement__technical_evaluator=user)
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return Response([pilot_data(pilot, user) for pilot in qs])
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    app = Application.objects.select_related("startup", "problem_statement").filter(id=request.data.get("application")).first()
    if not app:
        return Response({"detail": "Application not found."}, status=404)
    if app.status != Application.Status.APPROVED_FOR_PILOT:
        return Response({"detail": "Only an application approved for pilot can be contracted."}, status=400)
    if hasattr(app, "pilot"):
        try:
            return Response(pilot_data(app.pilot, user, detailed=True))
        except Pilot.DoesNotExist:
            pass
    officer = user if user.role == User.Role.PROCUREMENT_OFFICER else app.problem_statement.procurement_officer
    pilot = Pilot.objects.create(
        code=_next("PIL", Pilot),
        application=app,
        startup=app.startup,
        problem_statement=app.problem_statement,
        procurement_officer=officer,
        location=request.data.get("location") or app.problem_statement.pilot_location,
        joining_deadline=app.problem_statement.pilot_joining_deadline,
        duration_weeks=app.problem_statement.pilot_duration_weeks,
        reporting_frequency="Weekly",
        status=Pilot.Status.DRAFT,
    )
    Contract.objects.create(pilot=pilot, contract_no=_next("PC", Contract), kpi_method=request.data.get("kpi_method") or Contract.KPIMethod.MANUAL)
    audit(user, "create_pilot", "pilot", pilot.id, app.code)
    return Response(pilot_data(pilot, user, detailed=True), status=201)


@api_view(["GET", "PATCH"])
def pilot_detail(request, pk):
    user, error = require(request)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot or not can_view_pilot(user, pilot):
        return Response({"detail": "Pilot not found."}, status=404)
    if request.method == "GET":
        return Response(pilot_data(pilot, user, detailed=True))
    if user.role not in {User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN}:
        return Response({"detail": "Only a procurement officer can edit the pilot contract."}, status=403)
    data = request.data
    for field in ["location", "responsibilities", "government_support", "payment_conditions", "security_requirements", "reporting_frequency"]:
        if field in data:
            setattr(pilot, field, data[field])
    for field in ["start_date", "end_date", "joining_deadline"]:
        if data.get(field):
            setattr(pilot, field, data[field])
    if data.get("duration_weeks"):
        pilot.duration_weeks = int(data["duration_weeks"])
    if data.get("field_evaluator"):
        field_user = User.objects.filter(id=data["field_evaluator"], role=User.Role.FIELD_EVALUATOR).first()
        if not field_user:
            return Response({"detail": "Field evaluator not found."}, status=400)
        pilot.field_evaluator = field_user
    pilot.save()
    contract = pilot.contract
    if data.get("kpi_method") in {Contract.KPIMethod.MANUAL, Contract.KPIMethod.EXTRACT}:
        if pilot.kpi_locked:
            return Response({"detail": "KPI method cannot change after the pilot starts."}, status=400)
        contract.kpi_method = data["kpi_method"]
        contract.save(update_fields=["kpi_method"])
    if "milestones" in data:
        replace_milestones(pilot, data.get("milestones") or [])
    audit(user, "update_pilot", "pilot", pilot.id)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


def _load_pilot(pk):
    return (
        Pilot.objects.select_related(
            "startup__user",
            "problem_statement__department",
            "application",
            "field_evaluator",
            "procurement_officer",
            "contract",
            "final_report",
            "recommendation",
        )
        .filter(id=pk)
        .first()
    )


@api_view(["POST"])
def pilot_kpis(request, pk):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot or not can_view_pilot(user, pilot):
        return Response({"detail": "Pilot not found."}, status=404)
    try:
        replace_kpis(pilot, request.data.get("kpis") or [], source=request.data.get("source") or "MANUAL")
    except WorkflowError as exc:
        return _bad(exc)
    if request.data.get("finalize"):
        pilot.contract.kpis_finalized = True
        pilot.contract.save(update_fields=["kpis_finalized"])
    audit(user, "set_kpis", "pilot", pilot.id)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
def lock_kpis(request, pk):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = Pilot.objects.filter(id=pk).first()
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    if abs(sum(k.weight for k in pilot.kpis.all()) - 100) > 0.2:
        return Response({"detail": "Lock is refused until KPI weights total 100%."}, status=400)
    pilot.kpi_locked = True
    pilot.save(update_fields=["kpi_locked"])
    pilot.contract.kpis_finalized = True
    pilot.contract.save(update_fields=["kpis_finalized"])
    audit(user, "lock_kpis", "pilot", pilot.id)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
def send_contract(request, pk):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    if not pilot.start_date or not pilot.end_date or not pilot.field_evaluator_id:
        return Response({"detail": "Set start date, end date and a field evaluator before sending the contract."}, status=400)
    contract = pilot.contract
    if contract.kpi_method == Contract.KPIMethod.MANUAL:
        if not pilot.kpis.exists():
            return Response({"detail": "Enter the official KPIs manually, or switch to extraction."}, status=400)
        if abs(sum(k.weight for k in pilot.kpis.all()) - 100) > 0.2:
            return Response({"detail": "KPI weights must total 100% before the contract is sent."}, status=400)
        contract.kpis_finalized = True
    write_unsigned_contract(pilot)
    contract.status = Contract.Status.SENT
    contract.sent_at = timezone.now()
    contract.save()
    pilot.status = Pilot.Status.CONTRACT_PENDING
    pilot.save(update_fields=["status"])
    app = pilot.application
    app.status = Application.Status.CONTRACT_PENDING
    app.save(update_fields=["status"])
    notify("Contract pending acceptance", f"Pilot contract {contract.contract_no} is ready for review and signature.", category="CONTRACT", link=f"/startup/pilots/{pilot.id}", recipient=pilot.startup.user)
    audit(user, "send_contract", "pilot", pilot.id, contract.contract_no)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["GET"])
def contract_file(request, pk):
    user, error = require(request)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot or not can_view_pilot(user, pilot):
        return Response({"detail": "Pilot not found."}, status=404)
    key = pilot.contract.signed_key or pilot.contract.unsigned_key
    if not key:
        return Response({"detail": "No contract file is stored yet."}, status=404)
    return open_object(key)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def sign_contract(request, pk):
    user, error = require(request, User.Role.STARTUP)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot or pilot.startup.user_id != user.id:
        return Response({"detail": "Pilot not found."}, status=404)
    contract = pilot.contract
    if contract.status not in {Contract.Status.SENT, Contract.Status.CONTRACT_ACCEPTED}:
        return Response({"detail": "There is no contract waiting for acceptance."}, status=400)
    if "file" not in request.FILES:
        return Response({"detail": "Upload the signed contract."}, status=400)
    try:
        signed_key = put_upload(request.FILES["file"], prefix=f"contracts/signed/{pilot.id}")
    except StorageError as exc:
        return _bad(exc)
    old_key = contract.unsigned_key
    if old_key:
        delete_object(old_key)
    contract.replacement_log = list(contract.replacement_log or []) + [
        {
            "at": timezone.now().isoformat(),
            "event": "Unsigned contract object deleted and replaced by the signed contract.",
            "previous_key": old_key,
            "signed_file": request.FILES["file"].name,
        }
    ]
    contract.unsigned_key = ""
    contract.signed_key = signed_key
    contract.status = Contract.Status.CONTRACT_ACCEPTED
    contract.accepted_at = timezone.now()
    Document.objects.create(
        startup=pilot.startup,
        pilot=pilot,
        application=pilot.application,
        name=f"Signed contract {contract.contract_no}",
        document_type=Document.Type.SIGNED_CONTRACT,
        object_key=signed_key,
        file_name=request.FILES["file"].name,
        size_bytes=request.FILES["file"].size or 0,
        verification_status=Document.Verification.VERIFIED_VALID,
        currently_valid=True,
        no_expiry=True,
        verified_date=timezone.localdate(),
    )
    if contract.kpi_method == Contract.KPIMethod.EXTRACT:
        text = extract_text_from_bytes(request.FILES["file"].name, read_bytes(signed_key)) or contract.body_text
        extracted = orchestrator.extract_kpis_from_text(text)
        contract.extracted_kpis = (extracted.get("result") or {}).get("kpis") or []
        contract.extraction_demo = bool(extracted.get("demo"))
        contract.extraction_notice = extracted.get("notice") or ""
        contract.kpis_finalized = False
        pilot.status = Pilot.Status.CONTRACT_ACCEPTED
        notify("Extracted KPIs need review", f"{contract.contract_no} was signed. Review extracted KPIs before the pilot starts.", category="KPI", link=f"/procurement/pilots/{pilot.id}/kpis", recipient=pilot.procurement_officer)
    else:
        pilot.status = Pilot.Status.ACTIVE
        pilot.kpi_locked = True
        pilot.application.status = Application.Status.PILOT_ACTIVE
        pilot.application.save(update_fields=["status"])
        _ensure_week_slots(pilot)
    contract.save()
    pilot.save()
    audit(user, "sign_contract", "pilot", pilot.id, "unsigned object replaced")
    notify("Contract accepted", f"{pilot.startup.company_name} accepted {contract.contract_no}.", category="CONTRACT", link=f"/procurement/pilots/{pilot.id}", recipient=pilot.procurement_officer)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


def _ensure_week_slots(pilot):
    if not pilot.start_date:
        return
    for week in range(1, min(pilot.duration_weeks, 8) + 1):
        due = pilot.start_date + timedelta(days=7 * week)
        WeeklyReport.objects.get_or_create(
            pilot=pilot,
            week=week,
            defaults={"status": WeeklyReport.Status.PENDING, "due_date": due},
        )


@api_view(["POST"])
def confirm_extracted(request, pk):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    items = request.data.get("kpis") or pilot.contract.extracted_kpis
    normalised = []
    for item in items:
        direction = item.get("direction") or "HIGHER_IS_BETTER"
        if direction == "higher_is_better":
            direction = "HIGHER_IS_BETTER"
        if direction == "lower_is_better":
            direction = "LOWER_IS_BETTER"
        normalised.append(
            {
                "name": item.get("name"),
                "target": item.get("target"),
                "unit": item.get("unit") or "",
                "weight": item.get("weight") or 0,
                "priority": item.get("priority") or "MUST_HAVE",
                "direction": direction,
                "max_score": item.get("max_score") or 120,
            }
        )
    try:
        replace_kpis(pilot, normalised, source="EXTRACT")
    except WorkflowError as exc:
        return _bad(exc)
    pilot.contract.kpis_finalized = True
    pilot.contract.extracted_kpis = normalised
    pilot.contract.save()
    if request.data.get("start", True):
        pilot.status = Pilot.Status.ACTIVE
        pilot.kpi_locked = True
        pilot.application.status = Application.Status.PILOT_ACTIVE
        pilot.application.save(update_fields=["status"])
        pilot.save()
        _ensure_week_slots(pilot)
    audit(user, "confirm_extracted_kpis", "pilot", pilot.id)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
def assign_field(request, pk):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = Pilot.objects.filter(id=pk).first()
    field_user = User.objects.filter(id=request.data.get("field_evaluator"), role=User.Role.FIELD_EVALUATOR).first()
    if not pilot or not field_user:
        return Response({"detail": "Pilot or field evaluator not found."}, status=404)
    pilot.field_evaluator = field_user
    pilot.save(update_fields=["field_evaluator"])
    notify("Pilot assigned", f"You are the field evaluator for {pilot.code}. Your identity is not shown to the startup.", category="ASSIGNMENT", link=f"/field/pilots/{pilot.id}", recipient=field_user)
    audit(user, "assign_field", "pilot", pilot.id)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
def cancel_pilot(request, pk):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = Pilot.objects.filter(id=pk).first()
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        return Response({"detail": "A cancellation reason is required."}, status=400)
    pilot.status = Pilot.Status.CANCELLED
    pilot.cancellation_reason = reason
    pilot.cancelled_at = timezone.now()
    pilot.cancelled_by = user
    pilot.save()
    pilot.application.status = Application.Status.PILOT_CANCELLED
    pilot.application.save(update_fields=["status"])
    notify("Pilot cancelled", reason, category="PILOT_CANCELLED", link=f"/startup/pilots/{pilot.id}", recipient=pilot.startup.user)
    if pilot.field_evaluator_id:
        notify("Pilot cancelled", reason, category="PILOT_CANCELLED", link=f"/field/pilots/{pilot.id}", recipient=pilot.field_evaluator)
    audit(user, "cancel_pilot", "pilot", pilot.id, reason)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def submit_report(request, pk):
    user, error = require(request, User.Role.STARTUP)
    if error:
        return error
    pilot = Pilot.objects.filter(id=pk, startup__user=user).first()
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    if pilot.status != Pilot.Status.ACTIVE:
        return Response({"detail": "Weekly reports can be submitted only on an active pilot."}, status=400)
    week = int(request.data.get("week") or 0)
    if week < 1:
        return Response({"detail": "Week number is required."}, status=400)
    report, _ = WeeklyReport.objects.get_or_create(pilot=pilot, week=week, defaults={"status": WeeklyReport.Status.PENDING})
    if not report.due_date and pilot.start_date:
        report.due_date = pilot.start_date + timedelta(days=7 * week)
    report.narrative = request.data.get("narrative") or report.narrative
    report.comments = request.data.get("comments") or ""
    claims = request.data.get("kpi_results") or request.data.get("kpi_claims") or []
    if isinstance(claims, str):
        import json

        claims = json.loads(claims)
    report.kpi_claims = claims
    report.submitted_at = timezone.now()
    today = timezone.localdate()
    report.status = WeeklyReport.Status.LATE if report.due_date and today > report.due_date else WeeklyReport.Status.SUBMITTED
    report.verification_status = ""
    report.save()
    if "file" in request.FILES:
        try:
            key = put_upload(request.FILES["file"], prefix=f"pilots/{pilot.id}/week-{week}")
        except StorageError as exc:
            return _bad(exc)
        Document.objects.create(
            startup=pilot.startup,
            pilot=pilot,
            name=request.FILES["file"].name,
            document_type=Document.Type.WEEKLY_EVIDENCE,
            object_key=key,
            file_name=request.FILES["file"].name,
            size_bytes=request.FILES["file"].size or 0,
            verification_status=Document.Verification.PENDING_VERIFICATION,
        )
    if pilot.field_evaluator_id:
        notify("Weekly report submitted", f"Week {week} from {pilot.startup.company_name} is awaiting field verification.", category="REPORT", link=f"/field/pilots/{pilot.id}/reports", recipient=pilot.field_evaluator)
    audit(user, "weekly_report", "pilot", pilot.id, f"week {week}")
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
def delay_excuse(request, pk):
    user, error = require(request, User.Role.STARTUP)
    if error:
        return error
    pilot = Pilot.objects.filter(id=pk, startup__user=user).first()
    report = WeeklyReport.objects.filter(pilot=pilot, week=request.data.get("week")).first() if pilot else None
    if not report:
        return Response({"detail": "Weekly report slot not found."}, status=404)
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        return Response({"detail": "Explain the delay."}, status=400)
    report.delay_reason = reason
    report.delay_review = "PENDING"
    report.save(update_fields=["delay_reason", "delay_review"])
    if pilot.field_evaluator_id:
        notify("Delay explanation received", f"Week {report.week}: {reason[:180]}", category="LATE_REPORT", link=f"/field/pilots/{pilot.id}/reports", recipient=pilot.field_evaluator)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
def review_delay(request, pk):
    user, error = require(request, User.Role.FIELD_EVALUATOR, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = Pilot.objects.filter(id=pk).first()
    if not pilot or not can_view_pilot(user, pilot):
        return Response({"detail": "Pilot not found."}, status=404)
    report = WeeklyReport.objects.filter(pilot=pilot, id=request.data.get("report_id")).first()
    if not report:
        return Response({"detail": "Report not found."}, status=404)
    action = (request.data.get("action") or "").upper()
    note = request.data.get("note") or ""
    report.delay_review_note = note
    if action == "RELAXATION":
        report.delay_review = "RELAXATION"
        report.status = WeeklyReport.Status.SUBMITTED
    elif action == "ACCEPT":
        report.delay_review = "ACCEPTED"
    elif action == "CLARIFICATION":
        report.delay_review = "CLARIFICATION"
        report.status = WeeklyReport.Status.NEEDS_CLARIFICATION
    elif action == "ESCALATE":
        report.delay_review = "ESCALATED"
        Complaint.objects.create(
            pilot=pilot,
            raised_by=user if user.role == User.Role.FIELD_EVALUATOR else pilot.field_evaluator,
            category="Repeated report delay",
            description=note or report.delay_reason or "Delay escalated to the Procurement Officer.",
        )
        if pilot.procurement_officer_id:
            notify("Delay escalated", f"{pilot.code} week {report.week}", category="COMPLAINT", link=f"/procurement/pilots/{pilot.id}/complaints", recipient=pilot.procurement_officer)
    else:
        return Response({"detail": "Action must be RELAXATION, ACCEPT, CLARIFICATION or ESCALATE."}, status=400)
    report.save()
    notify("Update on your delayed report", f"Week {report.week}: {report.delay_review.replace('_', ' ').title()}. {note}", category="LATE_REPORT", link=f"/startup/pilots/{pilot.id}/reports", recipient=pilot.startup.user)
    audit(user, "review_delay", "weekly_report", report.id, action)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
def verify_report(request, pk):
    user, error = require(request, User.Role.FIELD_EVALUATOR, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot or (user.role == User.Role.FIELD_EVALUATOR and pilot.field_evaluator_id != user.id):
        return Response({"detail": "Pilot not found."}, status=404)
    report = WeeklyReport.objects.filter(pilot=pilot, id=request.data.get("report_id")).first()
    if not report:
        return Response({"detail": "Report not found."}, status=404)
    status = (request.data.get("status") or "").upper()
    if status not in {"VERIFIED", "NEEDS_CLARIFICATION", "NOT_VERIFIED"}:
        return Response({"detail": "Status must be VERIFIED, NEEDS_CLARIFICATION or NOT_VERIFIED."}, status=400)
    report.verification_status = status
    report.observations = request.data.get("observations") or ""
    report.verified_by = user
    report.verified_at = timezone.now()
    report.status = {
        "VERIFIED": WeeklyReport.Status.VERIFIED,
        "NEEDS_CLARIFICATION": WeeklyReport.Status.NEEDS_CLARIFICATION,
        "NOT_VERIFIED": WeeklyReport.Status.REJECTED,
    }[status]
    report.save()
    FieldVerification.objects.create(
        pilot=pilot,
        weekly_report=report,
        verifier=user,
        status=status,
        observations=report.observations,
        activity_verified=bool(request.data.get("activity_verified")),
    )
    if status == "VERIFIED":
        extracted = orchestrator.extract_weekly_kpis(
            [{"name": k.name, "unit": k.unit, "target": k.target} for k in pilot.kpis.all()],
            report.narrative,
            report.kpi_claims,
        )
        WeeklyKPIResult.objects.filter(report=report).delete()
        claimed = {c.get("name", "").lower(): c for c in (report.kpi_claims or [])}
        for item in (extracted.get("result") or {}).get("kpis") or []:
            kpi = _match_kpi(pilot, item.get("name"))
            if not kpi or item.get("actual") is None:
                continue
            WeeklyKPIResult.objects.create(
                report=report,
                kpi=kpi,
                actual=item.get("actual"),
                unit=item.get("unit") or kpi.unit,
                evidence_ref=claimed.get((item.get("name") or "").lower(), {}).get("evidence_ref", ""),
                note="Extracted after field verification" + (" · demo analysis" if extracted.get("demo") else ""),
            )
        series = []
        for kpi in pilot.kpis.all():
            points = [
                {"week": row.report.week, "actual": row.actual}
                for row in WeeklyKPIResult.objects.filter(kpi=kpi, report__verification_status="VERIFIED").select_related("report")
            ]
            series.append({"name": kpi.name, "direction": kpi.direction, "target": kpi.target, "points": points})
        progress = orchestrator.analyze_progress(series, report.narrative)
        report.ai_progress = progress
        report.save(update_fields=["ai_progress"])
    notify(
        "Weekly report verification",
        f"Week {report.week} marked {status.replace('_', ' ').title()}.",
        category="FIELD_VERIFICATION",
        link=f"/startup/pilots/{pilot.id}",
        recipient=pilot.startup.user,
    )
    audit(user, "verify_weekly", "weekly_report", report.id, status)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


def _match_kpi(pilot, name):
    if not name:
        return None
    target = name.lower()
    for kpi in pilot.kpis.all():
        if kpi.name.lower() == target or target in kpi.name.lower() or kpi.name.lower() in target:
            return kpi
    return None


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def final_report(request, pk):
    user, error = require(request, User.Role.STARTUP)
    if error:
        return error
    pilot = Pilot.objects.filter(id=pk, startup__user=user).first()
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    if pilot.status not in {Pilot.Status.ACTIVE, Pilot.Status.COMPLETED}:
        return Response({"detail": "A final report is submitted on an active or completed pilot."}, status=400)
    import json

    claims = request.data.get("kpi_results") or request.data.get("kpi_claims") or []
    if isinstance(claims, str):
        claims = json.loads(claims)
    report, _ = FinalReport.objects.get_or_create(pilot=pilot)
    report.narrative = request.data.get("narrative") or ""
    report.kpi_claims = claims
    report.submitted_at = timezone.now()
    report.verification_status = ""
    report.save()
    if "file" in request.FILES:
        try:
            key = put_upload(request.FILES["file"], prefix=f"pilots/{pilot.id}/final")
        except StorageError as exc:
            return _bad(exc)
        Document.objects.create(
            startup=pilot.startup,
            pilot=pilot,
            name=request.FILES["file"].name,
            document_type=Document.Type.FINAL_EVIDENCE,
            object_key=key,
            file_name=request.FILES["file"].name,
            size_bytes=request.FILES["file"].size or 0,
        )
    if pilot.field_evaluator_id:
        notify("Final report submitted", pilot.code, category="FINAL_REPORT", link=f"/field/pilots/{pilot.id}/verification", recipient=pilot.field_evaluator)
    audit(user, "final_report", "pilot", pilot.id)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["POST"])
def verify_result(request, pk):
    user, error = require(request, User.Role.FIELD_EVALUATOR, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot or (user.role == User.Role.FIELD_EVALUATOR and pilot.field_evaluator_id != user.id):
        return Response({"detail": "Pilot not found."}, status=404)
    try:
        report = pilot.final_report
    except FinalReport.DoesNotExist:
        return Response({"detail": "No final report has been submitted."}, status=400)
    status = (request.data.get("status") or "").upper()
    if status not in {"VERIFIED", "NEEDS_CLARIFICATION", "NOT_VERIFIED"}:
        return Response({"detail": "Status must be VERIFIED, NEEDS_CLARIFICATION or NOT_VERIFIED."}, status=400)
    report.verification_status = status
    report.observations = request.data.get("observations") or ""
    report.verified_by = user
    report.verified_at = timezone.now()
    if status == "VERIFIED":
        extracted = orchestrator.extract_kpis_from_claims(report.kpi_claims, report.narrative, [{"name": k.name, "unit": k.unit} for k in pilot.kpis.all()])
        report.extracted_kpis = (extracted.get("result") or {}).get("kpis") or []
        report.extraction_demo = bool(extracted.get("demo"))
        pilot.status = Pilot.Status.COMPLETED
        pilot.application.status = Application.Status.PILOT_COMPLETED
        pilot.application.save(update_fields=["status"])
        pilot.save(update_fields=["status"])
    report.save()
    FieldVerification.objects.create(
        pilot=pilot,
        final_report=report,
        verifier=user,
        status=status,
        observations=report.observations,
        activity_verified=status == "VERIFIED",
    )
    if status == "VERIFIED":
        refresh_score_cache(pilot)
        if pilot.procurement_officer_id:
            notify("Final result verified", f"{pilot.code} can now be scored. The score uses verified values only.", category="FINAL_REPORT", link=f"/procurement/pilots/{pilot.id}", recipient=pilot.procurement_officer)
    notify("Final report verification", status.replace("_", " ").title(), category="FIELD_VERIFICATION", link=f"/startup/pilots/{pilot.id}/final-report", recipient=pilot.startup.user)
    audit(user, "verify_final", "pilot", pilot.id, status)
    return Response(pilot_data(_load_pilot(pk), user, detailed=True))


@api_view(["GET"])
def pilot_score(request, pk):
    user, error = require(request)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot or not can_view_pilot(user, pilot):
        return Response({"detail": "Pilot not found."}, status=404)
    scored = official_score(pilot)
    if not scored:
        return Response({"detail": "Official scoring waits for a field-verified final report. Unverified claims are not scored.", "score": None}, status=200)
    return Response(scored)


@api_view(["GET", "POST"])
def complaint_list(request):
    user, error = require(request)
    if error:
        return error
    if request.method == "GET":
        qs = Complaint.objects.select_related("pilot__startup", "pilot__problem_statement", "raised_by")
        if user.role == User.Role.STARTUP:
            qs = qs.filter(pilot__startup__user=user)
        elif user.role == User.Role.FIELD_EVALUATOR:
            qs = qs.filter(pilot__field_evaluator=user)
        elif user.role == User.Role.PROCUREMENT_OFFICER:
            qs = qs.filter(pilot__procurement_officer=user)
        return Response([complaint_data(item, user) for item in qs])
    if user.role != User.Role.FIELD_EVALUATOR:
        return Response({"detail": "Complaints are raised by the assigned field evaluator."}, status=403)
    pilot = Pilot.objects.filter(id=request.data.get("pilot"), field_evaluator=user).first()
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    item = Complaint.objects.create(
        pilot=pilot,
        raised_by=user,
        category=request.data.get("category") or "Other",
        description=request.data.get("description") or "",
    )
    if pilot.procurement_officer_id:
        notify("Field complaint", f"{item.category} on {pilot.code}. Evaluator identity is withheld from the startup.", category="COMPLAINT", link=f"/procurement/pilots/{pilot.id}/complaints", recipient=pilot.procurement_officer)
    notify("A field observation was recorded", "The procurement officer may ask you to respond. The evaluator's personal identity is not shared.", category="COMPLAINT", link=f"/startup/pilots/{pilot.id}", recipient=pilot.startup.user)
    audit(user, "complaint", "pilot", pilot.id, item.category)
    return Response(complaint_data(item, user), status=201)


@api_view(["POST"])
def complaint_respond(request, pk):
    user, error = require(request)
    if error:
        return error
    item = Complaint.objects.select_related("pilot__startup__user", "pilot__procurement_officer").filter(id=pk).first()
    if not item:
        return Response({"detail": "Complaint not found."}, status=404)
    action = (request.data.get("action") or "").upper()
    note = (request.data.get("note") or "").strip()
    if user.role == User.Role.STARTUP:
        if item.pilot.startup.user_id != user.id:
            return Response({"detail": "Complaint not found."}, status=404)
        if not note:
            return Response({"detail": "Write a response."}, status=400)
        item.startup_response = note
        item.status = Complaint.Status.RESPONDED
        item.save()
        if item.pilot.procurement_officer_id:
            notify("Startup responded to a complaint", note[:180], category="COMPLAINT", link=f"/procurement/pilots/{item.pilot_id}/complaints", recipient=item.pilot.procurement_officer)
    elif user.role in {User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN}:
        mapping = {
            "REQUEST_RESPONSE": Complaint.Status.RESPONSE_REQUESTED,
            "ACCEPT": Complaint.Status.ACCEPTED,
            "ESCALATE": Complaint.Status.ESCALATED,
            "CLOSE": Complaint.Status.CLOSED,
        }
        if action not in mapping:
            return Response({"detail": "Action must be REQUEST_RESPONSE, ACCEPT, ESCALATE or CLOSE."}, status=400)
        item.status = mapping[action]
        item.officer_action = note or item.officer_action
        item.save()
        notify("Complaint update", f"{item.get_status_display()}. {note}", category="COMPLAINT", link=f"/startup/pilots/{item.pilot_id}", recipient=item.pilot.startup.user)
    else:
        return Response({"detail": "You cannot update this complaint."}, status=403)
    audit(user, "complaint_action", "complaint", item.id, item.status)
    return Response(complaint_data(item, user))


@api_view(["GET"])
def alerts(request):
    user, error = require(request)
    if error:
        return error
    return Response(build_alerts(user))


@api_view(["GET"])
def notifications(request):
    user, error = require(request)
    if error:
        return error
    return Response([notification_data(item) for item in visible_notifications(user)[:40]])


@api_view(["POST"])
def notification_read(request, pk):
    user, error = require(request)
    if error:
        return error
    item = visible_notifications(user).filter(id=pk).first()
    if not item:
        return Response({"detail": "Notification not found."}, status=404)
    item.is_read = True
    item.save(update_fields=["is_read"])
    return Response(notification_data(item))


@api_view(["GET"])
def leaderboard(request):
    user, error = require(request)
    if error:
        return error
    rows = []
    for pilot in Pilot.objects.select_related("startup", "problem_statement").filter(status=Pilot.Status.COMPLETED):
        scored = official_score(pilot)
        if not scored or scored.get("overall") is None:
            continue
        rows.append(
            {
                "pilot_id": pilot.id,
                "pilot_code": pilot.code,
                "startup": pilot.startup.company_name,
                "problem": pilot.problem_statement.title,
                "score": scored["overall"],
                "label": scored["label"],
                "must_have_failures": scored["must_have_failures"],
                "disclaimer": "Decision support only. Leaderboard position does not award procurement.",
            }
        )
    rows.sort(key=lambda row: row["score"], reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
    return Response(rows)


@api_view(["GET"])
def recommendation_list(request):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN, User.Role.TECHNICAL_EVALUATOR)
    if error:
        return error
    rows = []
    for rec in Recommendation.objects.select_related("pilot__startup", "pilot__problem_statement"):
        payload = recommendation_data(rec)
        payload["startup"] = rec.pilot.startup.company_name
        payload["problem"] = rec.pilot.problem_statement.title
        payload["pilot_code"] = rec.pilot.code
        payload["score"] = official_score(rec.pilot)
        rows.append(payload)
    return Response(rows)


@api_view(["GET", "POST"])
def recommendation_detail(request, pk):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = _load_pilot(pk)
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    if request.method == "GET":
        try:
            return Response(recommendation_data(pilot.recommendation) | {"score": official_score(pilot), "pilot": pilot_data(pilot, user, detailed=True)})
        except Recommendation.DoesNotExist:
            return Response({"pilot": pilot_data(pilot, user, detailed=True), "score": official_score(pilot), "choice": ""})
    return _record_recommendation(request, user, pilot)


def _record_recommendation(request, user, pilot):
    choice = request.data.get("choice") or ""
    if choice and choice not in dict(Recommendation.Choice.choices):
        return Response({"detail": "Recommendation choice is not recognised."}, status=400)
    context = _ai_context(pilot)
    tips = orchestrator.scaleup_recommendation(context) if request.data.get("regenerate", True) else None
    narrative = ""
    report = ""
    demo = False
    notice = ""
    links = []
    if tips:
        demo = bool(tips.get("demo"))
        notice = tips.get("notice") or ""
        if request.data.get("include_report", True):
            generated = orchestrator.generate_report(context)
            report = (generated.get("result") or {}).get("narrative") or ""
            links = (generated.get("result") or {}).get("evidence_map") or []
            demo = demo or bool(generated.get("demo"))
            notice = notice or generated.get("notice") or ""
    rec, _ = Recommendation.objects.get_or_create(pilot=pilot)
    if choice:
        rec.choice = choice
    rec.officer_note = request.data.get("officer_note", rec.officer_note)
    if tips:
        rec.scaleup_tips = tips.get("result") or {}
        rec.narrative = (tips.get("result") or {}).get("achievement_summary") or rec.narrative
        rec.ai_demo = demo
        rec.ai_notice = notice
    if report:
        rec.evidence_report = report
        rec.evidence_links = links
    rec.recorded_by = user
    rec.save()
    audit(user, "recommendation", "pilot", pilot.id, rec.choice)
    return Response(recommendation_data(rec) | {"score": official_score(pilot)})


def _ai_context(pilot):
    score = official_score(pilot)
    open_complaints = pilot.complaints.exclude(status__in=["ACCEPTED", "CLOSED"]).count()
    try:
        final = pilot.final_report
        verification = final.verification_status
    except FinalReport.DoesNotExist:
        verification = ""
    return {
        "pilot_code": pilot.code,
        "startup": {"company_name": pilot.startup.company_name, "domain": pilot.startup.domain},
        "problem": {"title": pilot.problem_statement.title},
        "score": score,
        "open_complaints": open_complaints,
        "verification_status": verification,
        "milestones": list(pilot.milestones.values("name", "status")),
        "progress_summary": "",
    }


@api_view(["POST"])
def ai_analyze_proposal(request):
    user, error = require(request, User.Role.TECHNICAL_EVALUATOR, User.Role.GOVERNMENT_ADMIN, User.Role.PROCUREMENT_OFFICER)
    if error:
        return error
    app = Application.objects.filter(id=request.data.get("application_id")).select_related("startup", "problem_statement__department").first()
    if not app or not can_view_application(user, app):
        return Response({"detail": "Application not found."}, status=404)
    result = _run_proposal_analysis(app)
    return Response(result)


@api_view(["POST"])
def ai_extract_contract(request):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = Pilot.objects.filter(id=request.data.get("pilot_id")).first()
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    text = request.data.get("text") or pilot.contract.body_text
    result = orchestrator.extract_kpis_from_text(text)
    return Response(result)


@api_view(["POST"])
def ai_extract_weekly(request):
    user, error = require(request, User.Role.FIELD_EVALUATOR, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    report = WeeklyReport.objects.filter(id=request.data.get("report_id")).select_related("pilot").first()
    if not report:
        return Response({"detail": "Report not found."}, status=404)
    if report.verification_status != "VERIFIED":
        return Response({"detail": "Weekly KPI extraction runs only after field verification."}, status=400)
    result = orchestrator.extract_weekly_kpis(
        [{"name": k.name, "unit": k.unit} for k in report.pilot.kpis.all()],
        report.narrative,
        report.kpi_claims,
    )
    return Response(result)


@api_view(["POST"])
def ai_progress(request):
    user, error = require(request)
    if error:
        return error
    pilot = _load_pilot(request.data.get("pilot_id"))
    if not pilot or not can_view_pilot(user, pilot):
        return Response({"detail": "Pilot not found."}, status=404)
    from common.present import kpi_series

    result = orchestrator.analyze_progress(kpi_series(pilot), "")
    return Response(result)


@api_view(["POST"])
def ai_final(request):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN, User.Role.FIELD_EVALUATOR)
    if error:
        return error
    pilot = _load_pilot(request.data.get("pilot_id"))
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    score = official_score(pilot)
    if not score:
        return Response({"detail": "Final analysis waits for a verified final result."}, status=400)
    result = orchestrator.analyze_final(score, [], "", pilot.complaints.count())
    try:
        pilot.final_report.ai_analysis = result
        pilot.final_report.save(update_fields=["ai_analysis"])
    except FinalReport.DoesNotExist:
        pass
    return Response(result)


@api_view(["POST"])
def ai_scaleup(request):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = _load_pilot(request.data.get("pilot_id"))
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    return Response(orchestrator.scaleup_recommendation(_ai_context(pilot)))


@api_view(["POST"])
def ai_report(request):
    user, error = require(request, User.Role.PROCUREMENT_OFFICER, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    pilot = _load_pilot(request.data.get("pilot_id"))
    if not pilot:
        return Response({"detail": "Pilot not found."}, status=404)
    result = orchestrator.generate_report(_ai_context(pilot))
    rec, _ = Recommendation.objects.get_or_create(pilot=pilot)
    rec.evidence_report = (result.get("result") or {}).get("narrative") or rec.evidence_report
    rec.evidence_links = (result.get("result") or {}).get("evidence_map") or rec.evidence_links
    rec.ai_demo = bool(result.get("demo"))
    rec.ai_notice = result.get("notice") or ""
    rec.save()
    return Response(result | {"recommendation": recommendation_data(rec)})


@api_view(["POST"])
def ai_summarize(request):
    user, error = require(request)
    if error:
        return error
    return Response(orchestrator.summarize(request.data.get("text") or "", request.data.get("purpose") or "review"))


@api_view(["GET"])
def audit_logs(request):
    user, error = require(request, User.Role.GOVERNMENT_ADMIN)
    if error:
        return error
    rows = [
        {
            "id": item.id,
            "action": item.action,
            "entity": item.entity,
            "entity_id": item.entity_id,
            "detail": item.detail,
            "actor": item.actor.display_name if item.actor_id else "System",
            "created_at": item.created_at.isoformat(),
        }
        for item in AuditLog.objects.select_related("actor")[:40]
    ]
    return Response(rows)


@api_view(["GET"])
def dashboard(request):
    user, error = require(request)
    if error:
        return error
    from django.db.models import Count

    if user.role == User.Role.STARTUP:
        startup = user.startup
        docs = startup.documents.all()
        return Response(
            {
                "role": user.role,
                "profile_completion": _profile_completion(startup),
                "valid_documents": docs.filter(currently_valid=True).count(),
                "expiring_documents": docs.filter(verification_status=Document.Verification.EXPIRING_SOON).count(),
                "applications": startup.applications.count(),
                "active_pilots": startup.pilots.filter(status=Pilot.Status.ACTIVE).count(),
            }
        )
    data = {
        "role": user.role,
        "problem_statements": ProblemStatement.objects.count(),
        "applications": Application.objects.count(),
        "startups": User.objects.filter(role=User.Role.STARTUP).count(),
        "active_pilots": Pilot.objects.filter(status=Pilot.Status.ACTIVE).count(),
        "completed_pilots": Pilot.objects.filter(status=Pilot.Status.COMPLETED).count(),
        "pending_evaluations": Application.objects.filter(status=Application.Status.UNDER_TECHNICAL_EVALUATION).count(),
        "expiring_documents": Document.objects.filter(verification_status=Document.Verification.EXPIRING_SOON).count(),
        "open_complaints": Complaint.objects.exclude(status__in=["CLOSED", "ACCEPTED"]).count(),
        "applications_by_status": list(Application.objects.values("status").annotate(count=Count("id"))),
        "problems_by_status": list(ProblemStatement.objects.values("status").annotate(count=Count("id"))),
        "pilots_by_status": list(Pilot.objects.values("status").annotate(count=Count("id"))),
    }
    return Response(data)


def _profile_completion(startup):
    fields = [startup.company_name, startup.domain, startup.technologies, startup.dpiit_number, startup.city, startup.state, startup.description, startup.experience_years, startup.team_size]
    filled = sum(1 for value in fields if value not in ("", None, 0))
    return int(round(filled / len(fields) * 100))
