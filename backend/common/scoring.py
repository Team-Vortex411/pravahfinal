"""Deterministic contractual KPI scoring. The LLM never owns this number."""

from decimal import Decimal, ROUND_HALF_UP


def _d(value):
    return Decimal(str(value))


def _round(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def kpi_score(actual, target, direction, max_score=120):
    if actual is None or target in (None, 0, 0.0):
        return None
    actual_d = _d(actual)
    target_d = _d(target)
    cap = _d(max_score or 120)
    if direction == "LOWER_IS_BETTER":
        if actual_d == 0:
            raw = cap
        else:
            raw = (target_d / actual_d) * Decimal(100)
    else:
        raw = (actual_d / target_d) * Decimal(100)
    if raw > cap:
        raw = cap
    if raw < 0:
        raw = Decimal(0)
    return _round(raw)


def performance_label(overall):
    if overall is None:
        return "Unscored"
    if overall >= 105:
        return "High Performer"
    if overall >= 100:
        return "Strong"
    if overall >= 90:
        return "Moderate"
    return "Low"


def score_pilot(kpis, actuals_by_kpi_id):
    """kpis: iterable of KPI models. actuals_by_kpi_id: {id: float}."""
    rows = []
    weighted_total = Decimal(0)
    weight_sum = Decimal(0)
    must_have_failures = []
    for kpi in kpis:
        actual = actuals_by_kpi_id.get(kpi.id)
        score = kpi_score(actual, kpi.target, kpi.direction, kpi.max_score)
        weight = _d(kpi.weight)
        weight_sum += weight
        weighted = None
        variance = None
        if score is not None:
            weighted = _round(_d(score) * weight / Decimal(100))
            weighted_total += _d(weighted)
        if actual is not None:
            variance = _round(_d(actual) - _d(kpi.target))
        critical = False
        if kpi.priority == "MUST_HAVE" and score is not None and score < 90:
            critical = True
            must_have_failures.append(kpi.name)
        rows.append(
            {
                "kpi_id": kpi.id,
                "name": kpi.name,
                "target": kpi.target,
                "actual": actual,
                "unit": kpi.unit,
                "weight": kpi.weight,
                "priority": kpi.priority,
                "priority_label": kpi.get_priority_display(),
                "direction": kpi.direction,
                "max_score": kpi.max_score,
                "score": score,
                "weighted_score": weighted,
                "variance": variance,
                "critical_gap": critical,
            }
        )
    overall = _round(weighted_total) if rows and any(r["score"] is not None for r in rows) else None
    return {
        "overall": overall,
        "label": performance_label(overall),
        "weight_total": _round(weight_sum) if rows else 0,
        "weights_valid": abs(float(weight_sum) - 100) < 0.2 if rows else False,
        "kpis": rows,
        "must_have_failures": must_have_failures,
        "engine": "deterministic",
        "disclaimer": "Official score is computed by the platform scoring engine from field-verified KPI values. It is decision-support information only.",
    }
