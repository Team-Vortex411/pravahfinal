"""LangChain-organised AI workflows.

React never calls Qwen. Django builds a prompt, calls Qwen2.5-3B-Instruct
when configured, validates JSON, and otherwise returns a clearly labelled
demo analysis so the prototype remains usable.
"""

import json
import re

import httpx
from django.conf import settings

DEMO_NOTICE = "AI service unavailable. Showing demo analysis so the prototype remains functional."

SYSTEM = (
    "You are an analyst inside PRAVAH, an Indian government innovation-procurement "
    "decision-support system. You assist. You do not select startups, award contracts, "
    "or replace the competent authority. Use only the facts provided. Do not invent "
    "KPI values, evidence, milestones, names, or field observations. Return JSON only."
)


def _langchain_prompt(system, human):
    try:
        from langchain_core.prompts import ChatPromptTemplate

        tmpl = ChatPromptTemplate.from_messages(
            [
                ("system", "{system}"),
                ("human", "{human}"),
            ]
        )
        messages = tmpl.format_messages(system=system, human=human)
        return [{"role": m.type if m.type != "human" else "user", "content": m.content} for m in messages]
    except Exception:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": human},
        ]


def _parse_json(text):
    try:
        from langchain_core.output_parsers import JsonOutputParser

        return JsonOutputParser().parse(text)
    except Exception:
        if not text:
            raise ValueError("Empty model response")
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("Model did not return JSON")
        return json.loads(match.group(0))


def _call_qwen(system, human):
    if not settings.QWEN_API_URL:
        raise RuntimeError("QWEN_API_URL is not configured")
    messages = _langchain_prompt(system, human)
    headers = {"Content-Type": "application/json"}
    if settings.QWEN_API_KEY:
        headers["Authorization"] = f"Bearer {settings.QWEN_API_KEY}"
    payload = {
        "model": settings.QWEN_MODEL or "Qwen2.5-3B-Instruct",
        "messages": messages,
        "temperature": 0.2,
    }
    with httpx.Client(timeout=60) as client:
        response = client.post(settings.QWEN_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    if isinstance(data, dict) and data.get("choices"):
        return data["choices"][0]["message"]["content"]
    if isinstance(data, dict) and "content" in data:
        return data["content"]
    if isinstance(data, dict) and "text" in data:
        return data["text"]
    return json.dumps(data)


def run_workflow(name, human, required, demo_builder, validator=None):
    """Orchestrate prompt → model → JSON validation, with a labelled demo fallback."""
    demo = False
    notice = ""
    parsed = None
    try:
        if settings.DEMO_MODE and not settings.QWEN_API_URL:
            raise RuntimeError("demo mode without Qwen endpoint")
        raw = _call_qwen(SYSTEM + f" Workflow: {name}.", human)
        parsed = _parse_json(raw)
        missing = [key for key in required if key not in parsed]
        if missing:
            raise ValueError("Malformed AI JSON, missing: " + ", ".join(missing))
        if validator:
            validator(parsed)
    except Exception as exc:
        if not settings.DEMO_MODE and settings.QWEN_API_URL:
            return {
                "ok": False,
                "demo": False,
                "notice": f"AI response could not be validated ({exc}). It was not stored as verified data.",
                "result": None,
            }
        parsed = demo_builder()
        demo = True
        notice = DEMO_NOTICE
    parsed["workflow"] = name
    return {"ok": True, "demo": demo, "notice": notice, "result": parsed, "model": settings.QWEN_MODEL}


def _clip(text, n=1800):
    text = (text or "").strip()
    return text[:n]


def analyze_proposal(problem, startup, proposal_text, documents):
    human = "\n".join(
        [
            f"Problem title: {problem.get('title')}",
            f"Department: {problem.get('department')}",
            f"Description: {_clip(problem.get('description'), 800)}",
            f"Requirements: {problem.get('technical_requirements')}",
            f"Expected outcome: {problem.get('expected_outcome')}",
            f"Startup: {startup.get('company_name')} ({startup.get('domain')})",
            f"Technologies: {startup.get('technologies')}",
            f"Experience: {startup.get('relevant_experience')}",
            f"Documents: {documents}",
            f"Proposal text: {_clip(proposal_text, 2000)}",
            "Return JSON with keys solution_summary, technical_approach, problem_understanding, "
            "matched_requirements, missing_requirements, concerns, experience_observations, "
            "document_observations, ai_score (0-100).",
        ]
    )

    def demo():
        reqs = problem.get("technical_requirements") or []
        blob = (proposal_text or "").lower() + " " + (startup.get("description") or "").lower()
        matched, missing = [], []
        for req in reqs:
            words = [w for w in re.findall(r"[a-z]{4,}", req.lower())]
            if any(w in blob for w in words[:3]) or not words:
                matched.append(req)
            else:
                missing.append(req)
        if not matched and reqs:
            matched = reqs[:2]
            missing = reqs[2:]
        score = 72 + min(16, len(matched) * 4) - min(10, len(missing) * 3)
        concerns = []
        if missing:
            concerns.append("Some stated requirements are not clearly evidenced in the submitted proposal text.")
        if "security" not in blob and "encrypt" not in blob:
            concerns.append("Security architecture is not clearly explained.")
        if "scale" not in blob and "scalab" not in blob:
            concerns.append("Scalability across government sites is not clearly explained.")
        return {
            "solution_summary": (
                f"{startup.get('company_name')} proposes a {startup.get('domain')} approach for "
                f"“{problem.get('title')}”, drawing on {startup.get('technologies') or 'its stated stack'}."
            ),
            "technical_approach": _clip(proposal_text, 420) or startup.get("capabilities") or "Approach details were limited in the submission.",
            "problem_understanding": f"The proposal addresses {problem.get('department')} needs around {problem.get('expected_outcome', '')[:220]}",
            "matched_requirements": matched[:6],
            "missing_requirements": missing[:6],
            "concerns": concerns or ["No major technical concern was inferred from the available text."],
            "experience_observations": startup.get("relevant_experience") or "Relevant experience narrative was not detailed.",
            "document_observations": documents or "Document metadata was not available to the analysis.",
            "ai_score": max(55, min(94, score)),
        }

    def validator(parsed):
        score = float(parsed.get("ai_score"))
        if score < 0 or score > 100:
            raise ValueError("ai_score out of range")

    return run_workflow("proposal-analysis", human, [
        "solution_summary",
        "technical_approach",
        "matched_requirements",
        "missing_requirements",
        "concerns",
        "ai_score",
    ], demo, validator)


def extract_kpis_from_text(text, hint_kpis=None):
    human = (
        "Extract ONLY KPI definitions from the contract text. Do not extract parties, payments, "
        "or unrelated clauses. Return JSON {\"kpis\": [{\"name\", \"target\", \"unit\", \"direction\"}]}. "
        "direction is higher_is_better or lower_is_better.\n\n"
        + _clip(text, 3000)
    )

    def demo():
        found = []
        patterns = [
            (r"accuracy[^0-9]{0,40}(\d+(?:\.\d+)?)\s*%", "Accuracy", "percent", "higher_is_better"),
            (r"uptime[^0-9]{0,40}(\d+(?:\.\d+)?)\s*%", "Uptime", "percent", "higher_is_better"),
            (r"response time[^0-9]{0,40}(\d+(?:\.\d+)?)\s*seconds", "Response Time", "seconds", "lower_is_better"),
        ]
        low = (text or "").lower()
        for pat, name, unit, direction in patterns:
            m = re.search(pat, low)
            if m:
                found.append({"name": name, "target": float(m.group(1)), "unit": unit, "direction": direction})
        if not found and hint_kpis:
            found = hint_kpis
        if not found:
            found = [
                {"name": "Accuracy", "target": 90, "unit": "percent", "direction": "higher_is_better"},
                {"name": "Response Time", "target": 2, "unit": "seconds", "direction": "lower_is_better"},
            ]
        return {"kpis": found}

    return run_workflow("contract-kpi-extraction", human, ["kpis"], demo)


def extract_weekly_kpis(kpi_config, report_text, claims):
    human = (
        "Extract ONLY KPI actual values for this week from the verified report. "
        "Do not extract unrelated narrative. Return JSON {\"week\": number, \"kpis\": "
        "[{\"name\", \"actual\", \"unit\"}]}.\n"
        f"KPI configuration: {kpi_config}\nClaims: {claims}\nReport: {_clip(report_text, 2000)}"
    )

    def demo():
        kpis = []
        for claim in claims or []:
            if claim.get("actual") is None:
                continue
            kpis.append(
                {
                    "name": claim.get("name"),
                    "actual": claim.get("actual"),
                    "unit": claim.get("unit") or "",
                }
            )
        if not kpis:
            for cfg in kpi_config or []:
                m = re.search(rf"{re.escape(cfg.get('name',''))}[^0-9]{{0,30}}(\d+(?:\.\d+)?)", report_text or "", re.I)
                if m:
                    kpis.append({"name": cfg.get("name"), "actual": float(m.group(1)), "unit": cfg.get("unit")})
        return {"week": None, "kpis": kpis}

    return run_workflow("weekly-kpi-extraction", human, ["kpis"], demo)


def extract_kpis_from_claims(claims, narrative, kpi_config):
    """Final KPI extraction. Values are taken from the verified report, never invented."""
    human = (
        "Extract ONLY final KPI actuals from the field-verified report. "
        "If a value is not present, omit it. Do not invent numbers. "
        "Return JSON {\"kpis\": [{\"name\", \"actual\", \"unit\"}]}.\n"
        f"Configuration: {kpi_config}\nClaims: {claims}\nNarrative: {_clip(narrative, 2000)}"
    )

    def demo():
        kpis = []
        for claim in claims or []:
            if claim.get("actual") is None:
                continue
            kpis.append({"name": claim.get("name"), "actual": claim.get("actual"), "unit": claim.get("unit") or ""})
        return {"kpis": kpis}

    return run_workflow("final-kpi-extraction", human, ["kpis"], demo)


def analyze_progress(kpi_rows, narrative):
    human = (
        "Provide advisory progress analysis from verified weekly KPI data only. "
        "Return JSON with progress_summary, trend, improving, declining, concern, improvement_tip. "
        f"KPI rows: {kpi_rows}\nNarrative: {_clip(narrative, 800)}"
    )

    def demo():
        improving, declining = [], []
        for row in kpi_rows or []:
            points = row.get("points") or []
            if len(points) < 2:
                continue
            delta = points[-1]["actual"] - points[0]["actual"]
            better = delta > 0 if row.get("direction") != "LOWER_IS_BETTER" else delta < 0
            (improving if better else declining).append(row.get("name"))
        trend = "improving" if improving and not declining else "mixed" if improving else "flat"
        tip = "Focus the next week on the KPI furthest from its contractual target, and attach field evidence with the report."
        if declining:
            tip = f"Stabilise {declining[0]} before expanding sites. Recheck calibration, data quality, and the field procedure."
        summary = "Verified weekly figures show movement against the contractual targets. This note is advisory and is not a procurement decision."
        if improving:
            summary = (
                f"{', '.join(improving)} improved across verified weeks"
                + (f", while {', '.join(declining)} needs attention." if declining else ".")
            )
        return {
            "progress_summary": summary,
            "trend": trend,
            "improving": improving,
            "declining": declining,
            "concern": declining[0] + " is moving away from the target." if declining else "No declining verified KPI in the current series.",
            "improvement_tip": tip,
        }

    return run_workflow("weekly-progress", human, ["progress_summary", "improvement_tip"], demo)


def analyze_final(score, weekly, verification, complaints):
    human = (
        "Analyse verified final KPI performance. Do not invent numbers. "
        "Return JSON with achievement_summary, strong_areas, weak_areas, priority_notes, interpretation, ai_assessment. "
        f"Score: {score}\nWeekly: {weekly}\nVerification: {verification}\nComplaints: {complaints}"
    )

    def demo():
        rows = (score or {}).get("kpis") or []
        strong = [r["name"] for r in rows if (r.get("score") or 0) >= 100]
        weak = [r["name"] for r in rows if r.get("score") is not None and r["score"] < 95]
        failures = (score or {}).get("must_have_failures") or []
        return {
            "achievement_summary": (
                f"Official weighted score is {(score or {}).get('overall')} ({(score or {}).get('label')}). "
                "This interpretation uses only stored verified values."
            ),
            "strong_areas": strong,
            "weak_areas": weak,
            "priority_notes": [
                f"MUST HAVE gap: {name} is below 90 and must not be masked by optional KPIs." for name in failures
            ] or ["No MUST HAVE KPI is currently below the 90 attention line."],
            "interpretation": "Continuous scoring shows the degree of target achievement. It is not a pass/fail award.",
            "ai_assessment": (score or {}).get("overall"),
        }

    return run_workflow("final-performance", human, ["achievement_summary", "strong_areas", "weak_areas"], demo)


def scaleup_recommendation(context):
    human = (
        "Write advisory scale-up considerations for government reviewers. "
        "Do not phrase the output as a procurement order. Return JSON with recommended_focus (list), "
        "scaleup_considerations (list), cautions (list), suggested_choice. "
        f"Context: {json.dumps(context)[:3500]}"
    )

    def demo():
        score = (context.get("score") or {}).get("overall")
        failures = (context.get("score") or {}).get("must_have_failures") or []
        complaints = context.get("open_complaints") or 0
        choice = "CONSIDER_SCALEUP"
        if failures or (score is not None and score < 90):
            choice = "DO_NOT_RECOMMEND" if score is not None and score < 90 else "ADDITIONAL_PILOT"
        elif score is not None and score < 100:
            choice = "CONSIDER_PROCUREMENT"
        focus = []
        for row in (context.get("score") or {}).get("kpis") or []:
            if row.get("score") is not None and row["score"] < 100:
                focus.append(f"Improve {row['name']} consistency against the target of {row['target']} {row['unit']}.")
        if not focus:
            focus.append("Maintain current verified performance during any wider deployment.")
        return {
            "recommended_focus": focus[:4],
            "scaleup_considerations": [
                "KPI targets and weights used here are the locked contractual configuration.",
                "Field verification status should be read together with the score, not after it.",
                "No automatic procurement award is made by this recommendation.",
            ],
            "cautions": (
                [f"{complaints} complaint(s) remain open."] if complaints else ["No unresolved critical complaint was stored."]
            ) + ([f"MUST HAVE attention: {', '.join(failures)}."] if failures else []),
            "suggested_choice": choice,
        }

    return run_workflow("scaleup", human, ["recommended_focus", "scaleup_considerations"], demo)


def generate_report(context):
    human = (
        "Write a narrative evidence report. Separate verified facts from interpretation. "
        "Do not invent numbers. Return JSON with narrative (string) and evidence_map (list of {claim, source}). "
        f"Context: {json.dumps(context)[:4000]}"
    )

    def demo():
        score = context.get("score") or {}
        startup = context.get("startup") or {}
        ps = context.get("problem") or {}
        lines = [
            f"VERIFIED FACTS — {startup.get('company_name')} piloted “{ps.get('title')}” under {context.get('pilot_code')}.",
            f"Official weighted score: {score.get('overall')} ({score.get('label')}). Source: deterministic scoring engine on field-verified KPI actuals.",
            f"Field verification: {context.get('verification_status') or 'not recorded'}.",
            f"Open complaints: {context.get('open_complaints', 0)}.",
            "AI INTERPRETATION — The narrative below restates stored figures and must not be treated as a new measurement.",
            context.get("progress_summary") or "Weekly trend is available on the pilot record.",
        ]
        evidence = [
            {"claim": "Overall score", "source": "Pilot score engine / verified final KPI results"},
            {"claim": "Weekly trend", "source": "Weekly reports verified by the Field Evaluator"},
            {"claim": "Complaints", "source": "Complaint register"},
            {"claim": "Milestones", "source": "Milestone records on the pilot contract"},
            {"claim": "Documents", "source": "Document register"},
        ]
        return {"narrative": "\n\n".join(lines), "evidence_map": evidence}

    return run_workflow("evidence-report", human, ["narrative"], demo)


def summarize(text, purpose):
    human = f"Summarise for a government reviewer. Purpose: {purpose}. Return JSON {{\"summary\": string}}. Text: {_clip(text, 2000)}"

    def demo():
        snippet = _clip(text, 320)
        return {"summary": snippet or "No text was available to summarise."}

    return run_workflow("summarise", human, ["summary"], demo)
