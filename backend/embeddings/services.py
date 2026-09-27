"""Problem ↔ startup semantic matching.

Primary path: sentence-transformers/all-MiniLM-L6-v2 (384-d) stored for
pgvector cosine search. Demo path: a deterministic 384-d hashing embedder
with a synonym normaliser so related procurement language still matches
when the transformer weights are not installed.
"""

import hashlib
import math
import re

from django.conf import settings

from embeddings.models import Embedding

SYNONYMS = {
    "ai": "machinelearning",
    "artificial": "machinelearning",
    "ml": "machinelearning",
    "machine": "machinelearning",
    "learning": "machinelearning",
    "prediction": "forecast",
    "predicting": "forecast",
    "predict": "forecast",
    "predictive": "forecast",
    "stockout": "shortage",
    "stockouts": "shortage",
    "stock-out": "shortage",
    "stock-outs": "shortage",
    "inventory": "stock",
    "medicine": "medicine",
    "medicines": "medicine",
    "drug": "medicine",
    "drugs": "medicine",
    "hospital": "hospital",
    "hospitals": "hospital",
    "demand": "demand",
    "forecasting": "forecast",
    "shortage": "shortage",
    "shortages": "shortage",
    "disease": "disease",
    "crop": "crop",
    "crops": "crop",
    "agriculture": "agriculture",
    "agricultural": "agriculture",
    "pest": "disease",
    "waste": "waste",
    "garbage": "waste",
    "bin": "waste",
    "collection": "collection",
    "traffic": "traffic",
    "congestion": "congestion",
    "mobility": "traffic",
    "water": "water",
    "leak": "leak",
    "leakage": "leak",
    "pipeline": "pipeline",
    "attendance": "attendance",
    "school": "school",
    "student": "student",
    "students": "student",
    "fleet": "fleet",
    "vehicle": "fleet",
    "maintenance": "maintenance",
    "telemedicine": "telehealth",
    "tele-diagnostics": "telehealth",
    "diagnostics": "telehealth",
    "triage": "telehealth",
    "iot": "iot",
    "sensor": "iot",
    "sensors": "iot",
    "vision": "vision",
    "computer": "vision",
    "nlp": "nlp",
    "routing": "routing",
    "grievance": "grievance",
    "cold": "coldchain",
    "chain": "coldchain",
    "cold-chain": "coldchain",
}

DOMAIN_HINTS = {
    "healthcare": {"medicine", "hospital", "telehealth", "forecast", "shortage"},
    "health": {"medicine", "hospital", "telehealth", "forecast"},
    "agriculture": {"crop", "disease", "agriculture"},
    "agritech": {"crop", "disease", "agriculture"},
    "urban": {"waste", "water", "collection"},
    "water": {"water", "leak", "pipeline", "iot"},
    "mobility": {"traffic", "congestion", "fleet"},
    "transport": {"traffic", "congestion", "fleet", "maintenance"},
    "education": {"attendance", "school", "student"},
    "edtech": {"attendance", "school", "student"},
}


def _tokens(text: str):
    raw = re.findall(r"[a-z0-9][a-z0-9+-]{1,}", (text or "").lower())
    out = []
    for tok in raw:
        tok = tok.replace("_", "")
        mapped = SYNONYMS.get(tok, tok)
        out.append(mapped)
    return out


def hash_embed(text: str, dim: int = 384):
    vec = [0.0] * dim
    tokens = _tokens(text)
    if not tokens:
        vec[0] = 1.0
        return vec
    for tok in tokens:
        digest = hashlib.sha256(tok.encode()).digest()
        idx = int.from_bytes(digest[:2], "big") % dim
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vec[idx] += sign
        idx2 = int.from_bytes(digest[3:5], "big") % dim
        vec[idx2] += 0.35 * sign
    # light bigrams so phrases survive wording changes
    for a, b in zip(tokens, tokens[1:]):
        digest = hashlib.sha256(f"{a}_{b}".encode()).digest()
        idx = int.from_bytes(digest[:2], "big") % dim
        vec[idx] += 0.8
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


_model = None
_model_failed = False


def _transformer():
    global _model, _model_failed
    if _model_failed:
        return None
    if _model is not None:
        return _model
    if settings.DEMO_MODE and not os_getenv_force():
        _model_failed = True
        return None
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        return _model
    except Exception:
        _model_failed = True
        return None


def os_getenv_force():
    import os

    return os.getenv("FORCE_TRANSFORMER", "").lower() in {"1", "true", "yes"}


def embed_text(text: str):
    model = _transformer()
    if model is not None:
        vec = model.encode(text or "", normalize_embeddings=True).tolist()
        return vec[: settings.EMBEDDING_DIM], settings.EMBEDDING_MODEL, False
    return hash_embed(text, settings.EMBEDDING_DIM), f"demo-hash:{settings.EMBEDDING_MODEL}", True


def cosine(a, b):
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return float(sum(a[i] * b[i] for i in range(n)))


def problem_source_text(ps) -> str:
    reqs = " ".join(ps.technical_requirements or [])
    elig = " ".join(ps.eligibility_criteria or [])
    return "\n".join(
        [
            ps.title,
            ps.description,
            ps.department.name if ps.department_id else "",
            ps.location,
            ps.technology_domain,
            ps.expected_outcome,
            reqs,
            elig,
            ps.pilot_location,
        ]
    )


def startup_source_text(startup) -> str:
    return "\n".join(
        [
            startup.company_name,
            startup.domain,
            startup.technologies,
            startup.city,
            startup.state,
            startup.description,
            startup.capabilities,
            startup.relevant_experience,
            f"experience {startup.experience_years} years",
            f"team {startup.team_size}",
        ]
    )


def upsert_problem_embedding(ps):
    text = problem_source_text(ps)
    vector, model_name, _demo = embed_text(text)
    Embedding.objects.update_or_create(
        entity_type=Embedding.Entity.PROBLEM,
        entity_id=ps.id,
        defaults={
            "vector": vector,
            "source_text": text,
            "model_name": model_name,
            "dimensions": len(vector),
        },
    )
    return vector


def upsert_startup_embedding(startup):
    text = startup_source_text(startup)
    vector, model_name, _demo = embed_text(text)
    Embedding.objects.update_or_create(
        entity_type=Embedding.Entity.STARTUP,
        entity_id=startup.id,
        defaults={
            "vector": vector,
            "source_text": text,
            "model_name": model_name,
            "dimensions": len(vector),
        },
    )
    return vector


DOMAIN_RULES = [
    ("Healthcare", {"medicine", "hospital", "telehealth", "coldchain", "pharmacist", "vaccine"}),
    ("Agriculture", {"crop", "agriculture", "soybean", "wheat"}),
    ("Water", {"water", "leak", "pipeline"}),
    ("Sanitation", {"waste", "collection"}),
    ("Mobility", {"traffic", "congestion"}),
    ("Fleet", {"fleet", "maintenance", "workshop"}),
    ("Education", {"school", "attendance", "student"}),
    ("Lighting", {"streetlight", "feeder"}),
    ("Grievance", {"grievance", "routing"}),
]


def _content_tokens(text):
    return {tok for tok in _tokens(text) if len(tok) > 3}


def _domain_bonus(startup, ps):
    startup_tokens = _content_tokens(startup_source_text(startup))
    problem_tokens = _content_tokens(problem_source_text(ps))
    bonus = 0
    reasons = []
    for label, keys in DOMAIN_RULES:
        if startup_tokens & keys and problem_tokens & keys:
            bonus += 10
            shared_keys = sorted((startup_tokens & problem_tokens) & keys)
            reasons.append(
                f"Domain compatibility: {startup.domain} and {ps.technology_domain}"
                + (f" share {', '.join(shared_keys)}" if shared_keys else f" both sit in {label.lower()}")
            )
            break
    if (startup.state or "").lower() and (startup.state or "").lower() in (ps.location or "").lower():
        bonus += 3
        reasons.append(f"Location compatibility: startup is based in {startup.state}")
    shared = sorted(startup_tokens & problem_tokens)
    shared = [tok for tok in shared if tok not in {"based", "years", "team", "with", "from", "that", "this"}][:6]
    if shared:
        reasons.append("Shared technical context: " + ", ".join(shared))
    return bonus, reasons, startup_tokens, problem_tokens


def score_pair(startup, ps, startup_vec=None, problem_vec=None):
    if startup_vec is None:
        row = Embedding.objects.filter(entity_type="startup", entity_id=startup.id).first()
        startup_vec = row.vector if row else embed_text(startup_source_text(startup))[0]
    if problem_vec is None:
        row = Embedding.objects.filter(entity_type="problem", entity_id=ps.id).first()
        problem_vec = row.vector if row else embed_text(problem_source_text(ps))[0]
    semantic = max(0.0, cosine(startup_vec, problem_vec))
    # MiniLM cosine is already well scaled. The demo hash embedder is sparse, so
    # values around 0.05–0.40 are the useful band. Both paths are shown.
    model_row = Embedding.objects.filter(entity_type="startup", entity_id=startup.id).first()
    hash_mode = not model_row or str(model_row.model_name).startswith("demo-hash")
    if hash_mode:
        calibrated = max(0.0, min(100.0, (semantic - 0.02) / 0.36 * 100))
    else:
        calibrated = max(0.0, min(100.0, semantic * 100))
    bonus, reasons, startup_tokens, problem_tokens = _domain_bonus(startup, ps)
    overlap = startup_tokens & problem_tokens
    coverage = len(overlap) / max(1, min(len(startup_tokens), len(problem_tokens)))
    overlap_pts = min(100.0, coverage * 100 + min(24, len(overlap) * 2))
    combined = 0.62 * calibrated + 0.38 * overlap_pts + bonus * 0.35
    if bonus >= 10:
        # Same declared domain: wording can differ and still be a recommendation.
        combined = max(combined, 76 + min(16, calibrated * 0.16) + min(4, len(overlap)))
    combined = min(96.0, max(0.0, combined))
    return {
        "score": int(round(combined)),
        "semantic": round(calibrated, 1),
        "metadata_adjustment": bonus,
        "reasons": reasons or ["Limited overlapping technical language"],
        "method": "pgvector cosine similarity" if settings.USE_PGVECTOR else "cosine similarity on 384-d embeddings, with declared domain rules",
        "model": model_row.model_name if model_row else settings.EMBEDDING_MODEL,
        "demo_embedder": hash_mode,
    }


def recommendations_for_startup(startup, limit=6, exclude_ids=None):
    exclude_ids = set(exclude_ids or [])
    srow = Embedding.objects.filter(entity_type="startup", entity_id=startup.id).first()
    if not srow:
        upsert_startup_embedding(startup)
        srow = Embedding.objects.filter(entity_type="startup", entity_id=startup.id).first()
    from problem_statements.models import ProblemStatement

    problems = list(ProblemStatement.objects.select_related("department").all())
    prows = {e.entity_id: e for e in Embedding.objects.filter(entity_type="problem")}
    ranked = []
    for ps in problems:
        if ps.id in exclude_ids:
            continue
        if ps.status not in {"OPEN", "PILOT_ACTIVE"}:
            continue
        vec = prows.get(ps.id).vector if prows.get(ps.id) else None
        match = score_pair(startup, ps, srow.vector, vec)
        if match["score"] < 60:
            continue
        ranked.append((match["score"], ps, match))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:limit]


def similar_startups_for_problem(ps, limit=5):
    from startups.models import Startup

    prow = Embedding.objects.filter(entity_type="problem", entity_id=ps.id).first()
    if not prow:
        upsert_problem_embedding(ps)
        prow = Embedding.objects.filter(entity_type="problem", entity_id=ps.id).first()
    ranked = []
    for startup in Startup.objects.all():
        match = score_pair(startup, ps, problem_vec=prow.vector)
        ranked.append((match["score"], startup, match))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:limit]
