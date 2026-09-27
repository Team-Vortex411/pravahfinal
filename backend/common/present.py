from django.utils import timezone

from common.scoring import score_pilot


def _date(value):
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _dt(value):
    if not value:
        return None
    return value.isoformat()


def is_startup(user):
    return bool(user and getattr(user, "is_authenticated", False) and user.role == "STARTUP")


def person(user, hide=False):
    if not user:
        return None
    if hide:
        return {"display": "Assigned Field Evaluator", "role": "FIELD_EVALUATOR"}
    return {
        "id": user.id,
        "name": user.display_name,
        "email": user.email,
        "role": user.role,
        "role_label": user.get_role_display(),
        "designation": user.designation,
        "phone": user.phone,
        "employee_id": user.employee_id,
        "department": user.department.name if user.department_id else None,
    }


def department(dep):
    if not dep:
        return None
    return {"id": dep.id, "name": dep.name, "code": dep.code, "ministry": dep.ministry}


def startup_data(startup, detailed=False):
    data = {
        "id": startup.id,
        "company_name": startup.company_name,
        "domain": startup.domain,
        "technologies": startup.technologies,
        "dpiit_number": startup.dpiit_number,
        "city": startup.city,
        "state": startup.state,
        "experience_years": startup.experience_years,
        "team_size": startup.team_size,
        "description": startup.description,
        "contact_person": startup.contact_person,
        "email": startup.user.email if startup.user_id else None,
    }
    if detailed:
        data["gstin"] = startup.gstin
        data["capabilities"] = startup.capabilities
        data["relevant_experience"] = startup.relevant_experience
    return data


def problem_data(ps, match=None, include_internal=False):
    data = {
        "id": ps.id,
        "code": ps.code,
        "title": ps.title,
        "description": ps.description,
        "department": department(ps.department),
        "location": ps.location,
        "technology_domain": ps.technology_domain,
        "expected_outcome": ps.expected_outcome,
        "technical_requirements": ps.technical_requirements or [],
        "eligibility_criteria": ps.eligibility_criteria or [],
        "required_documents": ps.required_documents or [],
        "application_deadline": _date(ps.application_deadline),
        "pilot_joining_deadline": _date(ps.pilot_joining_deadline),
        "pilot_location": ps.pilot_location,
        "pilot_duration_weeks": ps.pilot_duration_weeks,
        "status": ps.status,
        "application_count": getattr(ps, "application_count", None),
        "created_at": _dt(ps.created_at),
    }
    if match:
        data["match"] = match
    if include_internal:
        data["technical_evaluator"] = person(ps.technical_evaluator)
        data["procurement_officer"] = person(ps.procurement_officer)
    return data


def document_data(doc, viewer=None):
    hide_verifier_contact = is_startup(viewer)
    verifier = None
    if doc.verified_by_id:
        if hide_verifier_contact and doc.verified_by.role == "FIELD_EVALUATOR":
            verifier = {"display": "Field Evaluator"}
        else:
            verifier = {"id": doc.verified_by_id, "name": doc.verified_by.display_name, "role": doc.verified_by.role}
    return {
        "id": doc.id,
        "name": doc.name,
        "document_type": doc.document_type,
        "document_type_label": doc.get_document_type_display(),
        "file_name": doc.file_name,
        "object_key": doc.object_key if not is_startup(viewer) else None,
        "size_bytes": doc.size_bytes,
        "verification_status": doc.verification_status,
        "verified_by": verifier,
        "verified_date": _date(doc.verified_date),
        "expiry_date": _date(doc.expiry_date),
        "no_expiry": doc.no_expiry,
        "currently_valid": doc.currently_valid,
        "notes": doc.notes,
        "version": doc.version,
        "replaces": doc.replaces_id,
        "startup_id": doc.startup_id,
        "startup_name": doc.startup.company_name if doc.startup_id else None,
        "application_id": doc.application_id,
        "pilot_id": doc.pilot_id,
        "created_at": _dt(doc.created_at),
        "download_url": f"/api/documents/{doc.id}/download/",
    }


def evaluation_data(ev):
    if not ev:
        return None
    composite = ev.composite_out_of_10()
    return {
        "id": ev.id,
        "scores": ev.scores or {},
        "comments": ev.comments,
        "decision": ev.decision,
        "decision_label": ev.get_decision_display(),
        "composite_out_of_10": composite,
        "technical_score": None if composite is None else round(composite * 10, 1),
        "evaluator": person(ev.evaluator),
        "decided_at": _dt(ev.decided_at),
    }


SCORE_KEYS = [
    ("technical_feasibility", "Technical Feasibility"),
    ("innovation", "Innovation"),
    ("problem_relevance", "Problem Relevance"),
    ("scalability", "Scalability"),
    ("technical_capability", "Technical Capability"),
    ("relevant_experience", "Relevant Experience"),
]


def application_data(app, viewer=None, detailed=False):
    ps = app.problem_statement
    data = {
        "id": app.id,
        "code": app.code,
        "status": app.status,
        "status_label": app.get_status_display(),
        "eligibility_confirmed": app.eligibility_confirmed,
        "eligibility_checks": app.eligibility_checks or {},
        "pilot_readiness": app.pilot_readiness,
        "submitted_at": _dt(app.submitted_at),
        "updated_at": _dt(app.updated_at),
        "startup": startup_data(app.startup, detailed=detailed or not is_startup(viewer)),
        "problem": {
            "id": ps.id,
            "code": ps.code,
            "title": ps.title,
            "department": ps.department.name if ps.department_id else None,
            "location": ps.location,
            "technology_domain": ps.technology_domain,
            "application_deadline": _date(ps.application_deadline),
            "pilot_joining_deadline": _date(ps.pilot_joining_deadline),
        },
        "timeline": application_timeline(app),
    }
    if detailed:
        data["proposal_text"] = app.proposal_text
        data["ai_analysis"] = app.ai_analysis or {}
        data["clarification_request"] = app.clarification_request
        data["clarification_response"] = app.clarification_response
        data["rejection_reason"] = app.rejection_reason
        data["problem_detail"] = problem_data(ps, include_internal=not is_startup(viewer))
        data["documents"] = [document_data(d, viewer) for d in app.documents.all()]
        data["evaluation"] = evaluation_data(getattr(app, "evaluation", None) if hasattr(app, "evaluation") else None)
        try:
            data["evaluation"] = evaluation_data(app.evaluation)
        except Exception:
            data["evaluation"] = None
        data["startup_profile"] = startup_data(app.startup, detailed=True)
    return data


def application_timeline(app):
    steps = [
        ("SUBMITTED", "Application Submitted"),
        ("ELIGIBILITY_CHECK", "Eligibility Check"),
        ("READINESS", "Pilot Readiness Check"),
        ("UNDER_TECHNICAL_EVALUATION", "Technical Evaluation"),
        ("APPROVED_FOR_PILOT", "Pilot Approval"),
        ("PILOT", "Pilot"),
    ]
    order = {
        "SUBMITTED": 0,
        "ELIGIBILITY_CHECK": 1,
        "REJECTED_DEADLINE": 2,
        "UNDER_TECHNICAL_EVALUATION": 3,
        "CLARIFICATION_REQUIRED": 3,
        "APPROVED_FOR_PILOT": 4,
        "REJECTED": 3,
        "CONTRACT_PENDING": 5,
        "PILOT_ACTIVE": 5,
        "PILOT_COMPLETED": 5,
        "PILOT_CANCELLED": 5,
    }
    current = order.get(app.status, 0)
    items = []
    for idx, (key, label) in enumerate(steps):
        state = "upcoming"
        if app.status == "REJECTED_DEADLINE" and key == "READINESS":
            state = "rejected"
        elif app.status == "REJECTED" and key == "UNDER_TECHNICAL_EVALUATION":
            state = "rejected"
        elif app.status == "PILOT_CANCELLED" and key == "PILOT":
            state = "cancelled"
        elif idx < current:
            state = "done"
        elif idx == current:
            state = "current"
        items.append({"key": key, "label": label, "state": state})
    if app.status in {"PILOT_ACTIVE", "PILOT_COMPLETED", "CONTRACT_PENDING", "PILOT_CANCELLED"}:
        items[-1]["state"] = "cancelled" if app.status == "PILOT_CANCELLED" else "current" if app.status != "PILOT_COMPLETED" else "done"
    return items


def kpi_data(kpi):
    return {
        "id": kpi.id,
        "name": kpi.name,
        "target": kpi.target,
        "unit": kpi.unit,
        "weight": kpi.weight,
        "priority": kpi.priority,
        "priority_label": kpi.get_priority_display(),
        "direction": kpi.direction,
        "max_score": kpi.max_score,
        "source": kpi.source,
    }


def milestone_data(m):
    return {
        "id": m.id,
        "name": m.name,
        "amount": float(m.amount),
        "due_week": m.due_week,
        "status": m.status,
        "order": m.order,
    }


def weekly_data(report, viewer=None):
    hide = is_startup(viewer)
    return {
        "id": report.id,
        "week": report.week,
        "narrative": report.narrative,
        "comments": report.comments,
        "kpi_claims": report.kpi_claims or [],
        "status": report.status,
        "due_date": _date(report.due_date),
        "submitted_at": _dt(report.submitted_at),
        "delay_reason": report.delay_reason,
        "delay_review": report.delay_review,
        "delay_review_note": report.delay_review_note,
        "verification_status": report.verification_status,
        "verified_at": _dt(report.verified_at),
        "verified_by": {"display": "Field Evaluator"} if hide and report.verified_by_id else person(report.verified_by),
        "observations": report.observations,
        "ai_progress": report.ai_progress or {},
        "results": [
            {
                "kpi_id": row.kpi_id,
                "name": row.kpi.name,
                "actual": row.actual,
                "unit": row.unit,
                "evidence_ref": row.evidence_ref,
                "note": row.note,
            }
            for row in report.results.select_related("kpi").all()
        ],
    }


def final_data(report, viewer=None):
    if not report:
        return None
    hide = is_startup(viewer)
    return {
        "id": report.id,
        "narrative": report.narrative,
        "kpi_claims": report.kpi_claims or [],
        "submitted_at": _dt(report.submitted_at),
        "verification_status": report.verification_status,
        "verified_at": _dt(report.verified_at),
        "verified_by": {"display": "Field Evaluator"} if hide and report.verified_by_id else person(report.verified_by),
        "observations": report.observations,
        "extracted_kpis": report.extracted_kpis or [],
        "extraction_demo": report.extraction_demo,
        "ai_analysis": report.ai_analysis or {},
    }


def complaint_data(item, viewer=None):
    hide = is_startup(viewer)
    return {
        "id": item.id,
        "pilot_id": item.pilot_id,
        "pilot_code": item.pilot.code,
        "problem": item.pilot.problem_statement.title,
        "startup": item.pilot.startup.company_name,
        "category": item.category,
        "description": item.description,
        "status": item.status,
        "startup_response": item.startup_response,
        "officer_action": item.officer_action,
        "raised_by": {"display": "Field Evaluator"} if hide else person(item.raised_by),
        "created_at": _dt(item.created_at),
    }


def contract_data(contract):
    if not contract:
        return None
    return {
        "id": contract.id,
        "contract_no": contract.contract_no,
        "status": contract.status,
        "kpi_method": contract.kpi_method,
        "body_text": contract.body_text,
        "sent_at": _dt(contract.sent_at),
        "accepted_at": _dt(contract.accepted_at),
        "replacement_log": contract.replacement_log or [],
        "extracted_kpis": contract.extracted_kpis or [],
        "extraction_demo": contract.extraction_demo,
        "extraction_notice": contract.extraction_notice,
        "kpis_finalized": contract.kpis_finalized,
        "has_unsigned": bool(contract.unsigned_key),
        "has_signed": bool(contract.signed_key),
    }


def kpi_series(pilot):
    series = []
    kpis = list(pilot.kpis.all())
    reports = list(pilot.weekly_reports.filter(verification_status="VERIFIED").prefetch_related("results"))
    by_week = {r.week: r for r in reports}
    for kpi in kpis:
        points = []
        for week in sorted(by_week):
            report = by_week[week]
            for row in report.results.all():
                if row.kpi_id == kpi.id:
                    points.append({"week": week, "actual": row.actual, "evidence_ref": row.evidence_ref})
        series.append(
            {
                "kpi_id": kpi.id,
                "name": kpi.name,
                "unit": kpi.unit,
                "target": kpi.target,
                "direction": kpi.direction,
                "priority": kpi.priority,
                "weight": kpi.weight,
                "points": points,
            }
        )
    return series


def official_score(pilot):
    final = getattr(pilot, "final_report", None)
    try:
        final = pilot.final_report
    except Exception:
        final = None
    if not final or final.verification_status != "VERIFIED":
        return None
    actuals = {}
    extracted = {item.get("name", "").lower(): item.get("actual") for item in (final.extracted_kpis or [])}
    for kpi in pilot.kpis.all():
        actual = extracted.get(kpi.name.lower())
        if actual is None:
            for key, value in extracted.items():
                if key and (key in kpi.name.lower() or kpi.name.lower() in key):
                    actual = value
                    break
        if actual is not None:
            actuals[kpi.id] = actual
    if not actuals:
        return None
    scored = score_pilot(pilot.kpis.all(), actuals)
    scored["source"] = "Field-verified final KPI values"
    return scored


def recommendation_data(rec):
    if not rec:
        return None
    return {
        "id": rec.id,
        "pilot_id": rec.pilot_id,
        "choice": rec.choice,
        "choice_label": rec.get_choice_display() if rec.choice else "",
        "narrative": rec.narrative,
        "scaleup_tips": rec.scaleup_tips or {},
        "evidence_report": rec.evidence_report,
        "officer_note": rec.officer_note,
        "ai_demo": rec.ai_demo,
        "ai_notice": rec.ai_notice,
        "evidence_links": rec.evidence_links or [],
        "recorded_by": person(rec.recorded_by),
        "updated_at": _dt(rec.updated_at),
        "disclaimer": "Final award rests with the competent government authority.",
    }


def pilot_data(pilot, viewer=None, detailed=False):
    hide_field = is_startup(viewer)
    data = {
        "id": pilot.id,
        "code": pilot.code,
        "status": pilot.status,
        "location": pilot.location,
        "start_date": _date(pilot.start_date),
        "end_date": _date(pilot.end_date),
        "joining_deadline": _date(pilot.joining_deadline),
        "duration_weeks": pilot.duration_weeks,
        "reporting_frequency": pilot.reporting_frequency,
        "kpi_locked": pilot.kpi_locked,
        "cancellation_reason": pilot.cancellation_reason,
        "cancelled_at": _dt(pilot.cancelled_at),
        "startup": startup_data(pilot.startup, detailed=not hide_field),
        "problem": {
            "id": pilot.problem_statement_id,
            "code": pilot.problem_statement.code,
            "title": pilot.problem_statement.title,
            "department": pilot.problem_statement.department.name,
            "location": pilot.problem_statement.location,
            "technology_domain": pilot.problem_statement.technology_domain,
        },
        "application_id": pilot.application_id,
        "application_code": pilot.application.code,
        "field_evaluator": person(pilot.field_evaluator, hide=hide_field),
        "created_at": _dt(pilot.created_at),
    }
    if not hide_field:
        data["procurement_officer"] = person(pilot.procurement_officer)
        data["cancelled_by"] = person(pilot.cancelled_by)
    if detailed:
        data["responsibilities"] = pilot.responsibilities
        data["government_support"] = pilot.government_support
        data["payment_conditions"] = pilot.payment_conditions
        data["security_requirements"] = pilot.security_requirements
        try:
            data["contract"] = contract_data(pilot.contract)
        except Exception:
            data["contract"] = None
        data["milestones"] = [milestone_data(m) for m in pilot.milestones.all()]
        data["kpis"] = [kpi_data(k) for k in pilot.kpis.all()]
        data["weekly_reports"] = [weekly_data(r, viewer) for r in pilot.weekly_reports.all()]
        data["kpi_series"] = kpi_series(pilot)
        try:
            data["final_report"] = final_data(pilot.final_report, viewer)
        except Exception:
            data["final_report"] = None
        data["complaints"] = [complaint_data(c, viewer) for c in pilot.complaints.all()]
        data["score"] = official_score(pilot)
        try:
            data["recommendation"] = recommendation_data(pilot.recommendation)
        except Exception:
            data["recommendation"] = None
        data["documents"] = [document_data(d, viewer) for d in pilot.documents.all()]
        data["timeline"] = pilot_timeline(pilot)
    else:
        data["score"] = official_score(pilot) if pilot.status == "COMPLETED" else None
    return data


def pilot_timeline(pilot):
    events = [
        {"label": "Pilot record created", "at": _dt(pilot.created_at), "state": "done"},
    ]
    contract = getattr(pilot, "contract", None)
    try:
        contract = pilot.contract
    except Exception:
        contract = None
    if contract and contract.sent_at:
        events.append({"label": "Contract sent to startup", "at": _dt(contract.sent_at), "state": "done"})
    if contract and contract.accepted_at:
        events.append({"label": "Contract accepted and signed copy stored", "at": _dt(contract.accepted_at), "state": "done"})
    if pilot.start_date:
        events.append({"label": "Pilot start", "at": _date(pilot.start_date), "state": "done" if pilot.status in {"ACTIVE", "COMPLETED", "CANCELLED"} else "upcoming"})
    if pilot.status == "CANCELLED":
        events.append({"label": "Pilot cancelled", "at": _dt(pilot.cancelled_at), "state": "cancelled", "detail": pilot.cancellation_reason})
    if pilot.status == "COMPLETED":
        events.append({"label": "Pilot completed", "at": _date(pilot.end_date), "state": "done"})
    return events


def notification_data(item):
    return {
        "id": item.id,
        "title": item.title,
        "body": item.body,
        "category": item.category,
        "link": item.link,
        "is_read": item.is_read,
        "created_at": _dt(item.created_at),
    }


def visible_notifications(user):
    from django.db.models import Q
    from notifications.models import Notification

    return Notification.objects.filter(Q(recipient=user) | Q(role=user.role, recipient__isnull=True)).distinct()
