# PRAVAH — Government Innovation Procurement Platform

PRAVAH is a working prototype of a connected innovation-procurement lifecycle:

**Government problem → problem statement → startup discovery → eligibility and document verification → technical evaluation → pilot → field verification → KPI extraction → deterministic KPI scoring → procurement / scale-up recommendation.**

The operating rule is fixed:

> AI assists → Rules check → Humans verify → Government decides.

AI scores, summaries and recommendations are decision-support only. The platform does not select a startup, award procurement, or replace the competent government authority. Every recommendation screen states that **final award rests with the competent government authority**.

## What you can demonstrate

Sign in with password `demo123`.

| Account | Role | What to show |
| --- | --- | --- |
| `admin@gov.in` | Government Administrator | Create a problem statement, assign officers, open the no-selection alert |
| `evaluator@gov.in` | Technical Evaluator | Verify a document, read the AI proposal analysis, record a human decision |
| `procurement@gov.in` | Procurement Officer | Contract and KPI builder, complaints, leaderboard, recommendation |
| `field@gov.in` | Field Evaluator | Verify a weekly report. The startup never sees this person's name |
| `nova@novatech.in` | Startup (NovaTech, Arjun Malhotra) | AI match rings, completed medicine pilot, score 107.59, document expiry |

Other startup accounts (`waste@wasteflow.in`, `aqua@aquasense.in`, `cold@sheetal.in`, …) use the same password and cover an active pilot, a late report, an open complaint, and a contract waiting for signature.

The seeded workspace currently includes:

- 42 applications
- 5 active pilots
- 11 applications under technical evaluation
- 6 documents expiring soon
- a completed cohort on the leaderboard (NovaTech, AgroAI, MedPredict, SmartOps)
- one cancelled pilot and one problem statement with no selection for an extended period

The public landing page shows the illustrative programme snapshot required by the brief (8 / 42 / 5 / 11). After sign-in, dashboards show live counts from the database.

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | React, React Router, Vite, Tailwind CSS, lucide-react, Recharts |
| Backend | Django, Django REST Framework |
| Database | Neon PostgreSQL when `DATABASE_URL` is set; SQLite for local demo |
| Vectors | pgvector-compatible 384-d embeddings. Demo mode stores JSON vectors and computes cosine similarity. Set `USE_PGVECTOR=true` on Neon. |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` when installed; otherwise a clearly internal demo hash embedder of the same dimension |
| Files | Neon Object Storage (S3-compatible) when configured; local object keys otherwise |
| LLM | Qwen2.5-3B-Instruct via a backend-only Colab/OpenAI-compatible endpoint. LangChain builds the prompt and parses JSON. |
| Scoring | Deterministic Python engine. The model never owns the official number. |

The React app never receives `QWEN_API_KEY`.

## Local development

Requirements: Python 3.11+, Node 20+.

```bash
cd pravah
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

In another terminal:

```bash
cd pravah/frontend
npm install
npm run dev
```

Open the Vite URL. The dev server proxies `/api` to Django.

`seed_demo` refuses to run unless `DEMO_MODE=true`. It flushes the database and reloads the demonstration.

## Demo mode

`DEMO_MODE=true` keeps every major route usable when Qwen, Neon, or the embedding weights are absent.

- AI calls return a labelled **Demo AI Analysis** and the notice: “AI service unavailable. Showing demo analysis so the prototype remains functional.”
- Embeddings fall back to a 384-d hash embedder with a synonym normaliser, plus declared domain rules that are shown in the match reason. This is not silently described as MiniLM output.
- Files are stored under `backend/media/objects` using the same object-key model as Neon Object Storage.

## Neon PostgreSQL

1. Create a Neon project and copy the pooled connection string.
2. Set `DATABASE_URL` or `NEON_DATABASE_URL` in `.env`.
3. Enable pgvector in the Neon SQL editor:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

4. Install the optional driver extras if you want the native vector column:

```bash
pip install 'psycopg[binary]' pgvector
```

5. Set `USE_PGVECTOR=true`. The embedding service already stores 384-d vectors and runs cosine similarity. On Postgres you can migrate `embeddings_embedding.vector` from JSON to `vector(384)` and query with `<=>`. The API contract does not change.

Django selects SQLite only when both database URLs are empty, so a configured Neon URL is the application database. Do not use MongoDB.

## Neon Object Storage

Neon Object Storage is S3-compatible and is not the Postgres database.

```env
OBJECT_STORAGE_ENDPOINT=https://<your-neon-s3-endpoint>
OBJECT_STORAGE_BUCKET=pravah
OBJECT_STORAGE_ACCESS_KEY=
OBJECT_STORAGE_SECRET_KEY=
OBJECT_STORAGE_REGION=auto
```

Uploads are authorised in Django, written by object key, and downloaded only after a role check. PostgreSQL stores metadata (`document_type`, `verification_status`, `expiry_date`, `object_key`), not the file bytes.

If these variables are empty, the same keys are written on the local disk.

## pgvector and embeddings

Problem statements and startup profiles are embedded from a combined searchable text (title, description, department, location, domain, requirements, capabilities, experience).

Matching for a startup is:

```text
startup vector + problem vectors → cosine similarity → score and reasons
```

The LLM does not produce the match score. An optional AI explanation can be requested later; the number comes from the embedding service.

To use the real model instead of the demo hash embedder:

```bash
pip install sentence-transformers
# in .env
FORCE_TRANSFORMER=true
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Re-run `python manage.py seed_demo` so stored vectors are regenerated. Dimension is 384.

## Qwen on Colab

Run Qwen2.5-3B-Instruct behind an OpenAI-compatible chat-completions URL. Put the URL and key only in the backend environment:

```env
QWEN_API_URL=https://<colab-or-tunnel>/v1/chat/completions
QWEN_API_KEY=
QWEN_MODEL=Qwen2.5-3B-Instruct
```

Django calls it through `ai/orchestrator.py` (LangChain prompt template + JSON parser). Workflows:

- `POST /api/ai/analyze-proposal/`
- `POST /api/ai/extract-contract-kpis/`
- `POST /api/ai/extract-weekly-kpis/`
- `POST /api/ai/analyze-progress/`
- `POST /api/ai/analyze-final-performance/`
- `POST /api/ai/generate-scaleup-recommendation/`
- `POST /api/ai/generate-report/`
- `POST /api/ai/summarize/`

Malformed JSON is rejected. In demo mode the platform falls back to a labelled demo analysis instead of storing invented verified data.

KPI extraction is limited to KPI fields. Weekly and final extraction run only after the field evaluator marks the report verified. Official scores are then computed by `common/scoring.py`:

- Higher is better: `(Actual / Target) × 100`, capped at the KPI maximum (default 120)
- Lower is better: `(Target / Actual) × 100`, same cap
- Weighted score: `KPI score × weight`
- Weights must total 100%
- A MUST HAVE KPI under 90 is surfaced and cannot be hidden by an optional KPI

Labels: `>= 105` High Performer, `>= 100` Strong, `>= 90` Moderate, otherwise Low.

## API map

Base prefix `/api`. Authentication is a DRF token (`Authorization: Token …`).

Auth: `POST /api/auth/login/`, `POST /api/auth/register/`, `GET /api/auth/me/`, `GET /api/demo-accounts/`, `GET /api/health/`, `GET /api/meta/`

Problem statements, startups, applications, documents, evaluations, pilots, complaints, alerts, notifications, leaderboard and recommendations follow the brief. Extra prototype routes:

- `GET /api/match/problem-statements/` — startup semantic recommendations
- `GET /api/dashboard/` — role summary
- `POST /api/pilots/{id}/send-contract/`
- `GET /api/pilots/{id}/contract-file/`
- `POST /api/pilots/{id}/confirm-extracted-kpis/`
- `POST /api/pilots/{id}/delay-excuse/` and `delay-review/`
- `POST /api/documents/expiry-scan/`

Authorisation is enforced on the server. A startup cannot read another startup’s documents, cannot see a field evaluator’s name, email, phone or employee id, and cannot verify its own evidence.

## Contract signing

The procurement officer sends an unsigned PDF. On acceptance the startup uploads the signed file. The unsigned object is deleted, the signed object is stored, and the replacement is written to the contract audit log. If extraction was selected, KPIs are proposed for officer review and are not locked until confirmed. Manual KPIs are never re-read from the contract.

## Frontend routes

Public: `/`, `/login`, `/register`, `/problem-statements`, `/problem-statements/:id`

Government, evaluator, procurement, field and startup routes match the brief, including contract, KPI, complaint, report and final-report paths.

## Design

Navy `#06101c` / `#0b1f3a` / `#123055`, gold `#c9a227`, saffron `#ff9933`, India green `#138808`. Serif headings, IBM Plex Sans body, tricolor bar, government cards and tables, green match ring, purple “AI assisted” label. The seal is an original flow mark. The Ashoka Lion Capital is not used.
