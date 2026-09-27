from django.utils import timezone

from common.audit import audit, notify
from common.present import official_score
from pilots.models import Contract, KPI, Milestone, Pilot
from storage.pdf import render_pdf
from storage.services import delete_object, put_bytes


class WorkflowError(Exception):
    pass


def render_contract_text(pilot, contract_no=""):
    ps = pilot.problem_statement
    startup = pilot.startup
    lines = [
        f"PILOT CONTRACT  {contract_no}",
        "",
        "This pilot contract records a time-bound field trial. It is not a procurement award.",
        "Final award rests with the competent government authority.",
        "",
        "# Parties",
        f"Department: {ps.department.name}",
        f"Startup: {startup.company_name}  DPIIT {startup.dpiit_number or '—'}  GSTIN {startup.gstin or '—'}",
        f"Problem statement: {ps.code} — {ps.title}",
        "",
        "# Pilot",
        f"Location: {pilot.location}",
        f"Start date: {pilot.start_date}",
        f"End date: {pilot.end_date}",
        f"Pilot joining deadline: {pilot.joining_deadline}",
        f"Duration: {pilot.duration_weeks} weeks",
        f"Reporting frequency: {pilot.reporting_frequency}",
        "",
        "# Responsibilities of the startup",
        pilot.responsibilities or "—",
        "",
        "# Government support",
        pilot.government_support or "—",
        "",
        "# Payment conditions",
        pilot.payment_conditions or "Payment is conditional on verified milestones and is not an award of scale-up procurement.",
        "",
        "# Security requirements",
        pilot.security_requirements or "—",
        "",
        "# Milestones",
    ]
    for m in pilot.milestones.all():
        lines.append(f"- {m.name} | due week {m.due_week} | amount INR {m.amount} | {m.status}")
    lines.append("")
    lines.append("# Required KPIs")
    method = getattr(getattr(pilot, "contract", None), "kpi_method", Contract.KPIMethod.MANUAL)
    try:
        method = pilot.contract.kpi_method
    except Exception:
        method = Contract.KPIMethod.MANUAL
    if method == Contract.KPIMethod.EXTRACT:
        lines.append("KPI configuration method: automatic extraction from the signed contract, followed by Procurement Officer review.")
        lines.append("Accuracy target 90 percent. Direction: higher is better. Weight 40 percent. Priority MUST HAVE.")
        lines.append("Response Time target 2 seconds. Direction: lower is better. Weight 20 percent. Priority BETTER TO HAVE.")
        lines.append("Uptime target 99 percent. Direction: higher is better. Weight 25 percent. Priority MUST HAVE.")
        lines.append("Field adoption target 80 percent. Direction: higher is better. Weight 15 percent. Priority NICE TO HAVE.")
    else:
        lines.append("KPI configuration method: manual entry by the Procurement Officer. Do not re-extract KPIs from this contract.")
        for kpi in pilot.kpis.all():
            lines.append(
                f"- {kpi.name}: target {kpi.target} {kpi.unit}; weight {kpi.weight}%; "
                f"priority {kpi.get_priority_display()}; direction {kpi.direction}; maximum score {kpi.max_score}."
            )
    lines += [
        "",
        "# Acceptance",
        "By signing, the startup confirms it can deploy by the pilot joining deadline and will submit weekly evidence for field verification.",
        "Unsigned file is replaced by the signed contract object on acceptance. The replacement is written to the audit log.",
    ]
    return "\n".join(lines)


def write_unsigned_contract(pilot):
    contract = pilot.contract
    text = render_contract_text(pilot, contract.contract_no)
    contract.body_text = text
    pdf = render_pdf(f"Pilot contract {contract.contract_no}", text.splitlines(), subtitle=pilot.problem_statement.title)
    if contract.unsigned_key:
        delete_object(contract.unsigned_key)
    contract.unsigned_key = put_bytes(pdf, f"{contract.contract_no}.pdf", prefix="contracts/unsigned")
    contract.save(update_fields=["body_text", "unsigned_key"])
    return contract


def validate_kpis(items):
    if not items:
        raise WorkflowError("Add at least one KPI.")
    total = 0.0
    cleaned = []
    for idx, item in enumerate(items, start=1):
        try:
            weight = float(item.get("weight"))
            target = float(item.get("target"))
            max_score = float(item.get("max_score") or 120)
        except (TypeError, ValueError):
            raise WorkflowError("KPI target, weight and maximum score must be numbers.")
        direction = item.get("direction") or "HIGHER_IS_BETTER"
        priority = item.get("priority") or "MUST_HAVE"
        if direction not in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}:
            raise WorkflowError("KPI direction must be HIGHER_IS_BETTER or LOWER_IS_BETTER.")
        if priority not in {"MUST_HAVE", "BETTER_TO_HAVE", "NICE_TO_HAVE"}:
            raise WorkflowError("KPI priority is not recognised.")
        if not item.get("name"):
            raise WorkflowError("Every KPI needs a name.")
        total += weight
        cleaned.append(
            {
                "name": item["name"].strip(),
                "target": target,
                "unit": item.get("unit") or "",
                "weight": weight,
                "priority": priority,
                "direction": direction,
                "max_score": max_score,
                "order": idx,
            }
        )
    if abs(total - 100) > 0.2:
        raise WorkflowError(f"KPI weights must total 100%. Current total is {total:.1f}%.")
    return cleaned


def replace_kpis(pilot, items, source="MANUAL"):
    if pilot.kpi_locked:
        raise WorkflowError("KPI configuration is locked after the pilot starts.")
    cleaned = validate_kpis(items)
    pilot.kpis.all().delete()
    for item in cleaned:
        KPI.objects.create(pilot=pilot, source=source, **item)
    return cleaned


def replace_milestones(pilot, items):
    pilot.milestones.all().delete()
    for idx, item in enumerate(items or [], start=1):
        Milestone.objects.create(
            pilot=pilot,
            name=item.get("name") or f"Milestone {idx}",
            amount=item.get("amount") or 0,
            due_week=item.get("due_week") or idx,
            status=item.get("status") or "PENDING",
            order=idx,
        )


def refresh_score_cache(pilot):
    scored = official_score(pilot)
    pilot.score_cache = scored or {}
    pilot.save(update_fields=["score_cache", "updated_at"])
    return scored


def notify_role(role, title, body, category, link):
    notify(title, body, category=category, link=link, role=role)
