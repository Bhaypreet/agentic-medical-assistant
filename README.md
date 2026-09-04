# Agentic Medical Assistant

A medical assistant that reads laboratory reports, triages described symptoms,
answers general health questions, and finds nearby clinics. A LangGraph
supervisor routes each message to the agent that should handle it.

> **This is not a medical device.** Every response is AI-generated,
> informational, and no substitute for a qualified clinician. Reports uploaded
> here are personal health information — read [Handling patient data](#handling-patient-data)
> before deploying it anywhere real.

---

## What it does

| Capability | How it works |
|---|---|
| **Accounts** | Username and password sign-in; scrypt-hashed passwords, revocable bearer tokens, per-user data isolation |
| **Report analysis** | PDF text extraction or OCR → per-page model extraction → reference-range interpretation → physician-style summary |
| **Symptom triage** | One clarifying question, then a 1–5 severity assessment; severity 4–5 leads with emergency instructions |
| **Report chat** | Questions about an uploaded report, answered from the structured values plus a per-report vector index |
| **General questions** | Retrieval over a curated knowledge base in `data/`, with the model's own knowledge as fallback |
| **Diet plans** | Nutrition advice built around the patient's own abnormal values when a report is present |
| **Clinic lookup** | OpenStreetMap (Nominatim + Overpass), never model-invented names |

Answers are returned in whatever language the question was written in.

---

## Architecture

```
Streamlit UI  ──HTTP──▶  FastAPI
                            │
                            ├─ auth (X-API-Key) → owner
                            ├─ rate limiting, CORS, request ids
                            │
                            ▼
                     LangGraph supervisor
        ┌──────────┬─────────┼──────────┬───────────┐
        ▼          ▼         ▼          ▼           ▼
    triage      report    report     diet       clinic
                upload     chat                 lookup
                   │         │
                   │         └─ per-report FAISS index
                   └─ background job (poll for status)
                            │
                            ▼
                    SQLite / Postgres
                  (sessions, messages, jobs)
```

Key modules:

| Path | Responsibility |
|---|---|
| `app/config.py` | Every setting, validated once at startup |
| `app/api/` | Routes, schemas, authentication, rate limiting |
| `app/agents/graph.py` | The routing graph and its nodes |
| `app/supervisor/` | Intent classification |
| `app/report/` | Parsing, extraction and range interpretation |
| `app/rag/`, `app/report_rag/` | Knowledge base and per-report retrieval |
| `app/session/` | Session and message persistence |
| `app/jobs/` | Off-request report processing |
| `app/storage/` | Upload handling and data retention |
| `app/safety.py` | Disclaimers and emergency escalation |

---

## Running it locally

**Prerequisites:** Python 3.11+, Tesseract OCR (`apt install tesseract-ocr`),
and a [Groq API key](https://console.groq.com).

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pip install -r requirements-frontend.txt

cp .env.example .env      # then fill in GROQ_API_KEY
```

Build the knowledge base once — the API warns and degrades without it:

```bash
python -m app.rag.ingest
```

Run the two processes:

```bash
uvicorn app.api.main:app --reload            # API on :8000
streamlit run frontendv2/main.py             # UI  on :8501
```

Interactive API docs are at http://127.0.0.1:8000/docs.

### With Docker

```bash
docker build -t medical-assistant .
docker run -p 8000:8000 --env-file .env medical-assistant
```

The image builds the knowledge base at build time and runs gunicorn with
uvicorn workers as a non-root user.

---

## Configuration

Everything is read through `app/config.py`. See `.env.example` for the full
list; these are the ones that matter most:

| Variable | Default | Notes |
|---|---|---|
| `GROQ_API_KEY` | — | **Required.** Startup aborts without it. |
| `SECRET_KEY` | — | **Required in production**, min 32 chars. Pepper for password hashes and tokens. |
| `ENVIRONMENT` | `development` | `production` enforces the rules below. |
| `API_KEYS` | *(empty)* | Optional machine keys for `X-API-Key`. People use accounts instead. |
| `ALLOW_REGISTRATION` | `true` | Set `false` to close sign-ups after creating your accounts. |
| `DATABASE_URL` | `sqlite:///./sessions.db` | Point at Postgres for any real deploy. |
| `ALLOWED_ORIGINS` | localhost:8501 | CORS allowlist. |
| `MAX_UPLOAD_BYTES` | 15 MB | Enforced while streaming to disk. |
| `MAX_REPORT_PAGES` | 25 | Caps model calls per upload. |
| `REPORT_RETENTION_HOURS` | 24 | Uploads, report indexes and job rows are swept after this. |
| `DEBUG_LOG_REPORT_CONTENT` | `false` | Logs patient data. Refused in production. |

Two settings are enforced by validators rather than documentation:
`ENVIRONMENT=production` will not start without a 32-character `SECRET_KEY`,
and will not start with `DEBUG_LOG_REPORT_CONTENT=true`.

---

## API

**Every data endpoint requires a credential** — a bearer token from signing in,
or an `X-API-Key` for service callers. There is no anonymous access in any
environment. A `session_id` is a conversation key inside the caller's own
namespace; it never grants access to another account's data.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/register` | Create an account, returns a token. |
| `POST` | `/auth/login` | Exchange username and password for a token. |
| `POST` | `/auth/logout` | Revoke the presented token. |
| `GET` | `/auth/me` | The signed-in account. |
| `POST` | `/auth/change-password` | Change password; revokes all other sessions. |
| `GET` | `/health` | Liveness. |
| `GET` | `/ready` | Readiness: database, credentials, knowledge base. 503 when unable to serve. |
| `POST` | `/chat` | One turn. Returns the answer and follow-up suggestions. |
| `POST` | `/chat/stream` | The same turn as server-sent events, with progress. |
| `GET` | `/history` | The conversation, server-side. |
| `GET` | `/sessions` | The caller's chats. |
| `DELETE`| `/sessions/{id}` | Delete a chat and its report index. |
| `POST` | `/upload-report` | Accepts a report, returns `202` with a job id. |
| `GET` | `/report-status/{job_id}` | Poll a report job. |
| `GET` | `/download-report` | PDF of the analysed report. |
| `POST` | `/transcribe` | Speech to text. |

Reports are processed off the request path — upload returns immediately and the
client polls `/report-status`.

---

## Handling patient data

Uploaded reports are personal health information. What the service does:

- **Scopes every read to the account.** Session data is namespaced by the
  signed-in user; a session id alone reads nothing, and two people using the
  same deployment cannot see each other's reports.
- **Never stores a password.** Passwords are scrypt hashes with a per-user salt
  and a server-side pepper. Sign-in tokens are stored only as hashes, and are
  revocable — logging out or changing a password invalidates them immediately.
- **Never trusts an uploaded filename.** Files are written to
  server-generated UUID paths, with type, magic bytes and size checked.
- **Deletes the source file** once processing finishes, and sweeps uploads,
  report indexes and job rows after `REPORT_RETENTION_HOURS`.
- **Keeps report content out of logs.** Only identifiers and counts are logged
  unless `DEBUG_LOG_REPORT_CONTENT` is explicitly enabled, which production
  refuses.
- **Marks what it could not read.** A value the analyser cannot interpret is
  reported as `Unknown`, never as `Normal`.

What it does **not** do, and what you must add before handling real patients:

- No encryption at rest for uploads or vector indexes.
- No audit log of who read which record.
- No email verification, password reset, or multi-factor authentication.
- No role separation — every account has the same access to its own data.
- No formal HIPAA/GDPR assessment, data-processing agreement, or retention policy
  beyond the sweep above.

---

## Development

```bash
pytest                      # 182 tests
pytest --cov=app            # with coverage
ruff check . && ruff format --check .
```

CI runs the linter, the tests with a coverage floor, and a Docker build on
every pull request.

### Deploying

The API needs `GROQ_API_KEY` and, in production, `SECRET_KEY`. Point
`DATABASE_URL` at Postgres unless losing accounts on every restart is
acceptable — most hosts give containers an ephemeral filesystem.

The Streamlit frontend is deployed separately. Set `FASTAPI_URL` in its secrets
to the API's public URL, and make sure its dependency file is
`frontendv2/requirements.txt` rather than the repository-root one, which is the
API's much heavier dependency set.

The test suite mocks every network call, so it needs neither a Groq key nor the
vector store. `tests/conftest.py` supplies dummy settings and an in-memory
database.

---

## Known limitations

- **Report jobs run in-process.** State is in the database so any worker can
  answer a poll, but the work itself is on the machine that accepted the
  upload. A dedicated queue (arq, RQ, Celery) is the next step.
- **Streaming reports progress, not tokens.** `/chat/stream` emits which node
  is running and then the finished answer; true token streaming needs the graph
  nodes to stream from the model.
- **Rate limiting is per process.** Point slowapi at Redis to share limits
  across instances.
- **Intent routing is keyword-first.** English, Hindi, Hinglish and Punjabi
  terms are covered directly; other languages fall back to a model call.
- **Clinic data is OpenStreetMap.** Coverage varies by area, and listings can
  be out of date.
