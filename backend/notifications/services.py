from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from applications.models import Application
from documents.models import Document
from pilots.models import Pilot
from problem_statements.models import ProblemStatement
from reports.models import WeeklyReport


def build_alerts(user):
    alerts = []
    today = timezone.localdate()
    role = user.role

    if role in {"GOVERNMENT_ADMIN", "PROCUREMENT_OFFICER"}:
        cutoff = timezone.now() - timedelta(days=settings.NO_SELECTION_ALERT_DAYS)
        for ps in ProblemStatement.objects.filter(status=ProblemStatement.Status.OPEN, created_at__lt=cutoff):
            selected = ps.applications.filter(
                status__in=[
                    Application.Status.APPROVED_FOR_PILOT,
                    Application.Status.CONTRACT_PENDING,
                    Application.Status.PILOT_ACTIVE,
                    Application.Status.PILOT_COMPLETED,
                ]
            ).exists()
            if not selected:
                alerts.append(
                    {
                        "category": "NO_SELECTION",
                        "severity": "warning",
                        "title": "Problem Statement Alert",
                        "body": "No startup has been selected for this Problem Statement for an extended period. Please review eligibility, requirements, applications and timeline.",
                        "link": f"/government/problem-statements/{ps.id}",
                        "entity": ps.title,
                    }
                )

    doc_qs = Document.objects.select_related("startup").filter(
        verification_status__in=[Document.Verification.EXPIRING_SOON, Document.Verification.EXPIRED]
    )
    if role == "STARTUP":
        doc_qs = doc_qs.filter(startup__user=user)
    elif role == "TECHNICAL_EVALUATOR":
        pass
    elif role not in {"GOVERNMENT_ADMIN", "PROCUREMENT_OFFICER", "TECHNICAL_EVALUATOR"}:
        doc_qs = Document.objects.none()
    for doc in doc_qs[:12]:
        alerts.append(
            {
                "category": "DOCUMENT_EXPIRY",
                "severity": "danger" if doc.verification_status == "EXPIRED" else "warning",
                "title": "Expired document" if doc.verification_status == "EXPIRED" else "Document expiring soon",
                "body": f"{doc.startup.company_name if doc.startup_id else 'Startup'} — {doc.get_document_type_display()} ({doc.verification_status.replace('_', ' ').title()}).",
                "link": "/startup/documents" if role == "STARTUP" else "/evaluator/documents",
                "entity": doc.name,
            }
        )

    late = WeeklyReport.objects.select_related("pilot__startup", "pilot__problem_statement").filter(status=WeeklyReport.Status.LATE)
    if role == "STARTUP":
        late = late.filter(pilot__startup__user=user)
    elif role == "FIELD_EVALUATOR":
        late = late.filter(pilot__field_evaluator=user)
    elif role not in {"GOVERNMENT_ADMIN", "PROCUREMENT_OFFICER", "FIELD_EVALUATOR"}:
        late = WeeklyReport.objects.none()
    for report in late[:12]:
        alerts.append(
            {
                "category": "LATE_REPORT",
                "severity": "warning",
                "title": "Weekly pilot report is overdue",
                "body": f"{report.pilot.startup.company_name} — week {report.week} of {report.pilot.problem_statement.title}. Please submit the report or explain the delay.",
                "link": f"/startup/pilots/{report.pilot_id}/reports" if role == "STARTUP" else f"/field/pilots/{report.pilot_id}/reports",
                "entity": report.pilot.code,
            }
        )

    if role in {"GOVERNMENT_ADMIN", "PROCUREMENT_OFFICER"}:
        for pilot in Pilot.objects.filter(status=Pilot.Status.CANCELLED)[:5]:
            alerts.append(
                {
                    "category": "PILOT_CANCELLED",
                    "severity": "danger",
                    "title": "Pilot cancelled",
                    "body": pilot.cancellation_reason or "A procurement officer cancelled this pilot.",
                    "link": f"/procurement/pilots/{pilot.id}",
                    "entity": pilot.code,
                }
            )
    return alerts
