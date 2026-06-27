# CaseFlow MB

[![Deploy to EC2](https://github.com/nxu22/CaseFlow-AI-Legal-Assistant/actions/workflows/deploy.yml/badge.svg)](https://github.com/nxu22/CaseFlow-AI-Legal-Assistant/actions/workflows/deploy.yml)

A **multi-tenant document-to-decision agent platform** for Manitoba traffic defense law firms. Each firm's users, cases, and documents are fully isolated at both the application layer and the database layer (PostgreSQL RLS). Built to demonstrate how AI automation — document summarization, LangGraph intake agents, and MCP tool exposure — can be safely operated in a B2B SaaS context where tenant isolation is non-negotiable.

**Live demo:** https://caseflowmb.site
**Login:** `lawyer@caseflow.mb` / `Demo1234!`
**Public AI demo:** https://caseflowmb.site/demo *(no login required)*
**Interactive AI decision map:** https://nxu22.github.io/CaseFlow-AI-Legal-Assistant/

---

## What it does

- **Multi-Tenant Isolation** — every query is scoped to the authenticated user's firm; PostgreSQL RLS acts as a second enforcement layer at the database level
- **JWT Authentication** — secure login for law firm staff; token carries only user ID (firm context resolved server-side on every request)
- **Case Management** — track HTA violation cases (speeding, careless driving, red light, etc.) with statuses: Open, In Progress, Won, Lost, Dismissed
- **Client Management** — store client profiles with driver's license info, isolated per firm
- **Document Upload** — upload PDFs, images, and court notices directly to AWS S3
- **AI Summarization** — one-click Claude AI summary of any uploaded document (reads the file, extracts offence details, dates, fines, and defense notes)
- **Presigned Downloads** — secure time-limited download links from private S3 bucket
- **AI Intake Agent** — LangGraph 4-node pipeline that reads a ticket, matches the HTA section, finds similar cases, and drafts a full intake memo — pauses for lawyer review before writing to the database (human-in-the-loop); tenant-isolated via IntakeSession sidecar table
- **MCP Server** — FastMCP server exposing case data as agent tools; authenticated by per-firm API key; connect Claude Desktop to query and manage cases via conversation
- **Public AI Demo** — rate-limited chat interface at `/demo` where anyone can ask about cases and HTA sections; backend proxy keeps the API key server-side only

---

## Multi-Tenancy & Isolation

This is the most recent and largest engineering addition. The system enforces tenant isolation at two independent layers — so a missing `firm_id` filter in one query does not leak data.

### Architecture: dual-layer defense

```
Request → app layer (firm_id filter on every query)
                ↓
         PostgreSQL RLS (SET LOCAL app.current_tenant per transaction)
                ↓
         caseflow_app role (non-superuser → RLS always applies)
```

**Application layer** (`dependencies.py`): `get_db_with_rls` sets `SET LOCAL app.current_tenant = <firm_id>` at the start of every authenticated request, and every router query filters by `firm_id` explicitly.

**Database layer** (migrations `e9a3d1f8c2b7` → `f2b8c4d6e0a1` → `b7d3e1a9f5c2`): RLS policies on `cases`, `clients`, `documents`, and `intake_sessions` use `CASE WHEN nullif(current_setting('app.current_tenant', true), '') IS NULL THEN true ELSE firm_id = current_setting(...)::uuid END`. The `ELSE` branch catches any request where the app layer forgot to filter.

**Why not FORCE ROW SECURITY?** `caseflow_app` is a non-superuser, non-owner role — RLS applies automatically. `FORCE` is only needed for table owners.

**Why SET LOCAL instead of SET?** `SET LOCAL` is transaction-scoped. After `COMMIT`, the GUC reverts to `''`, preventing stale tenant context from leaking across pooled connections on the next request.

### Agent & MCP isolation

- **LangGraph intake agent**: `IntakeSession` sidecar table links each LangGraph `thread_id` to a `firm_id`. Phase 2 (`/intake/{thread_id}/decision`) checks `firm_id == current_user.firm_id` before resuming — 404 (not 403) to avoid confirming existence of another firm's threads.
- **MCP server**: `_resolve_firm_id()` runs at module import time, exits with code 1 if the `FIRM_API_KEY` is missing or invalid. Every tool call opens a DB session with `SET LOCAL app.current_tenant` scoped to the authenticated firm.

### Regression test suite

36 cross-tenant isolation tests across 7 test files:

| File | What it tests |
|---|---|
| `test_rls_depth.py` | psycopg2 direct (bypasses FastAPI) — RLS must block cross-tenant reads even without app-layer filter |
| `test_cases_isolation.py` | HTTP: Bob cannot read/write Demo Firm cases |
| `test_clients_isolation.py` | HTTP: cross-firm client lookup returns 404 |
| `test_documents_isolation.py` | HTTP: upload/download/delete blocked bidirectionally |
| `test_intake_isolation.py` | HTTP: Phase 1 case check + Phase 2 thread ownership check |
| `test_demo_isolation.py` | Demo router: `_run_tool` is scoped to Demo Firm only |
| `test_mcp_isolation.py` | MCP: cross-tenant read + write both blocked; DB verified unchanged after write attempt |

---

## Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| Python 3.12 | Language |
| FastAPI | REST API framework |
| SQLAlchemy 2.0 | ORM |
| Alembic | Database migrations |
| PostgreSQL 16 | Database (with Row-Level Security) |
| Pydantic v2 | Request/response validation |
| python-jose | JWT token signing |
| bcrypt | Password hashing |
| boto3 | AWS S3 integration |
| Anthropic SDK | Claude AI integration |
| LangGraph | AI agent orchestration (intake pipeline) |
| langgraph-checkpoint-postgres | PostgreSQL-backed agent state persistence |
| psycopg v3 | PostgreSQL driver for LangGraph checkpointer |
| FastMCP | MCP server framework (Claude Desktop integration) |
| Langfuse | LLM observability — traces, token counts, environment tagging |
| Gunicorn + Uvicorn | Production WSGI/ASGI server |

### Frontend
| Technology | Purpose |
|---|---|
| Next.js 16 (App Router) | React framework |
| React 19 | UI library |
| TypeScript | Type safety |
| Tailwind CSS v4 | Styling |
| Axios | HTTP client with JWT interceptor |
| React Hook Form + Zod | Form validation |
| Lucide React | Icons |

### Infrastructure
| Service | Purpose |
|---|---|
| AWS EC2 (t3.micro) | Application server |
| AWS RDS PostgreSQL | Production database |
| AWS S3 | Document storage |
| AWS Elastic IP | Fixed public IP (no change on EC2 restart) |
| Docker + Docker Compose | Containerization |
| GitHub | Version control |
| GitHub Actions | CI/CD — auto-deploy to EC2 on every push to main |

---

## Architecture

```
Browser
   │
   ▼
EC2 (Ubuntu 24.04)
├── caseflow_frontend_prod  (Next.js, port 80)
├── caseflow_backend_prod   (Gunicorn + FastAPI, port 8000)
│       │
│       ├── JWT auth → resolve firm_id from user
│       ├── SET LOCAL app.current_tenant = <firm_id>   (per transaction)
│       └── RLS policies enforce isolation at DB layer
│
└── caseflow_db_prod  ──►  AWS RDS PostgreSQL
                            ├── cases, clients, documents (RLS-protected)
                            ├── intake_sessions (firm_id ownership)
                            └── LangGraph checkpoint tables (PostgresSaver)

AWS S3  (documents — private bucket, presigned URLs)
Anthropic API  (Claude Sonnet for summarize/intake, Haiku for demo chat)
Langfuse  (trace every LLM call — token counts, latency, environment tag)

Claude Desktop ──► mcp_server.py (local, authenticated by FIRM_API_KEY)
                       └── SET LOCAL app.current_tenant per tool call
```

---

## AI Intake Agent

The intake pipeline is a 4-node LangGraph `StateGraph` with human-in-the-loop, backed by `PostgresSaver` so state survives server restarts and multi-worker deployments.

```
document text
     │
     ▼
[extract_info]        Claude Sonnet extracts: accused, offence, speed, date, location, officer
     │
     ▼
[lookup_hta]          Static Manitoba HTA table lookup — prevents AI from fabricating law sections
     │
     ▼
[find_similar]        Searches existing firm cases for similar HTA violations
     │
     ▼
[draft_intake]        Claude Sonnet drafts a full intake memo
     │
  ⏸ PAUSE — lawyer reviews memo in the UI
     │
  ✅ Approve / ❌ Reject
     │
     ▼
  Write hta_section + ai_summary to Case record (approve only)
```

**Two-phase REST API:**
- `POST /cases/{id}/intake` — runs Phase 1, returns `thread_id` + draft memo + HTA match
- `POST /cases/{id}/intake/{thread_id}/decision` — submits approve/reject, resumes the graph from the checkpoint

**Tenant isolation:** `IntakeSession` records `thread_id → firm_id`. Phase 2 verifies ownership before resuming — returns 404 (not 403) to avoid leaking thread existence.

---

## MCP Server (Claude Desktop)

`backend/mcp_server.py` exposes CaseFlow as a set of agent tools using FastMCP (stdio transport). Authenticated by `FIRM_API_KEY` at startup — invalid key causes immediate `sys.exit(1)`. Every tool call is scoped to the authenticated firm via `SET LOCAL app.current_tenant`.

**5 tools exposed:**

| Tool | What it does |
|---|---|
| `search_cases` | Filter cases by status or client name |
| `get_case` | Full case detail by ID |
| `list_documents` | Documents attached to a case |
| `get_hta_section` | Manitoba HTA section lookup |
| `update_case_status` | Update a case status |

**Claude Desktop config** (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "caseflow": {
      "command": "path/to/venv/Scripts/python.exe",
      "args": ["path/to/backend/mcp_server.py"],
      "env": { "FIRM_API_KEY": "your-firm-api-key" }
    }
  }
}
```

---

## Public Demo

`https://caseflowmb.site/demo` — no login required. Anyone can ask about cases and HTA sections in plain language. Scoped to Demo Firm data only via `SET LOCAL app.current_tenant`.

**Security measures:**
- API key lives only in backend environment variables — never sent to browser
- Per-IP rate limit: 10 requests / hour
- `max_tokens=1024`, Claude Haiku model (cost-controlled)
- Read-only tools — no writes exposed in demo
- System prompt constrains Claude to CaseFlow topics only
- Message length capped at 500 characters

---

## Project Structure

```
CaseFlow-MB/
├── backend/
│   ├── main.py              # FastAPI app + CORS + PostgresSaver lifespan
│   ├── config.py            # Pydantic settings (env vars)
│   ├── database.py          # SQLAlchemy engine + pool checkout RESET
│   ├── dependencies.py      # JWT auth + get_db_with_rls (SET LOCAL)
│   ├── security.py          # bcrypt + JWT utilities
│   ├── seed.py              # Demo data: 2 firms, 2 users, cases, clients
│   ├── mcp_server.py        # FastMCP server — per-firm API key auth
│   ├── models/
│   │   ├── firm.py          # Firm (tenant root)
│   │   ├── user.py          # Law firm staff (firm_id FK)
│   │   ├── client.py        # Defendants/clients (firm_id FK)
│   │   ├── case.py          # HTA violation cases (firm_id FK)
│   │   ├── document.py      # Case documents (metadata only)
│   │   └── intake_session.py # thread_id → firm_id ownership sidecar
│   ├── routers/
│   │   ├── auth.py          # Login, register, /me
│   │   ├── clients.py       # Client CRUD (firm-scoped)
│   │   ├── cases.py         # Case CRUD + filtering (firm-scoped)
│   │   ├── documents.py     # Upload, download, AI summarize
│   │   ├── intake.py        # AI intake: run + decision endpoints
│   │   └── demo.py          # Public demo: rate-limited chat proxy
│   ├── schemas/             # Pydantic request/response models
│   ├── services/
│   │   ├── s3.py            # S3 upload/download/presigned URLs
│   │   ├── ai.py            # Claude document summarization (Sonnet)
│   │   ├── intake_agent.py  # LangGraph 4-node intake pipeline
│   │   └── hta_reference.py # Static Manitoba HTA section lookup table
│   ├── alembic/             # Database migrations (incl. RLS policies)
│   ├── tests/               # 36 cross-tenant isolation tests
│   ├── Dockerfile           # Development image
│   └── Dockerfile.prod      # Production image (gunicorn)
├── frontend/
│   ├── app/
│   │   ├── demo/            # Public AI demo chat page (no auth)
│   │   ├── login/           # Login page
│   │   └── cases/
│   │       ├── layout.tsx   # Nav bar + auth guard
│   │       ├── page.tsx     # Cases list table
│   │       └── [id]/        # Case detail + documents + AI intake UI
│   ├── lib/
│   │   └── api.ts           # Axios client + all API functions
│   ├── Dockerfile           # Development image
│   └── Dockerfile.prod      # Production image (npm build + npm start)
├── docker-compose.yml       # Development stack
├── docker-compose.prod.yml  # Production stack
└── README.md
```

---

## Running Locally (Development)

**Prerequisites:** Docker Desktop, Git

```bash
git clone https://github.com/nxu22/CaseFlow-AI-Legal-Assistant.git
cd CaseFlow-AI-Legal-Assistant
```

Create `backend/.env`:
```
DATABASE_URL=postgresql://caseflow:caseflow_dev@localhost:5432/caseflow_mb
APP_DATABASE_URL=postgresql://caseflow_app:caseflow_app_dev@localhost:5432/caseflow_mb
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=ca-central-1
AWS_S3_BUCKET=your_bucket
ANTHROPIC_API_KEY=your_key
LANGFUSE_PUBLIC_KEY=your_key
LANGFUSE_SECRET_KEY=your_key
```

Start containers:
```bash
docker compose up -d
```

Run migrations + seed:
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python seed.py
```

Open http://localhost:3000 · Demo chat: http://localhost:3000/demo

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Login (returns JWT) |
| GET | `/auth/me` | Current user + firm |
| GET | `/clients` | List clients (firm-scoped, search + pagination) |
| POST | `/clients` | Create client |
| GET | `/cases` | List cases (firm-scoped, filter by status/client) |
| POST | `/cases` | Create case |
| GET | `/cases/{id}` | Case detail |
| PATCH | `/cases/{id}` | Update case |
| POST | `/cases/{id}/documents` | Upload document to S3 |
| GET | `/cases/{id}/documents` | List documents |
| GET | `/cases/{id}/documents/{doc_id}/download` | Get presigned download URL |
| POST | `/cases/{id}/documents/{doc_id}/summarize` | Generate Claude AI summary |
| POST | `/cases/{id}/intake` | Run AI intake agent (Phase 1) |
| POST | `/cases/{id}/intake/{thread_id}/decision` | Submit lawyer decision (Phase 2) |
| POST | `/demo/chat` | Public demo chat (rate-limited, Demo Firm scope) |

---

## Key Design Decisions

- **Dual-layer tenant isolation** — application-layer `firm_id` filter is the primary enforcement; PostgreSQL RLS is the defense-in-depth catch. A missing filter in one query does not leak data. 404 (not 403) for cross-tenant resources to avoid confirming existence.
- **SET LOCAL not SET** — GUC is transaction-scoped; after commit it reverts to `''`, preventing stale context on pooled connections. Pool checkout event fires `RESET app.current_tenant` to go from `''` to `NULL`, avoiding `''::uuid` cast errors in RLS policies.
- **nullif() in RLS ELSE branch** — `nullif(current_setting('app.current_tenant', true), '')::uuid` prevents plan-time UUID cast failure when GUC is empty string (migration `b7d3e1a9f5c2`).
- **S3 for documents, DB for metadata** — files stored in private S3 bucket, presigned URLs generated on demand (never stored in DB)
- **JWT payload: user ID only** — no firm_id in token; resolved from DB on every request. Prevents stale firm context if a user changes firm.
- **Separate AI summarize endpoint** — upload is always fast; AI failure doesn't affect upload
- **LangGraph human-in-the-loop** — graph pauses after `draft_intake` with `interrupt_after`; lawyer reviews before any DB write
- **PostgresSaver for agent state** — checkpoint in same RDS instance; `thread_id` reconnects Phase 1 and Phase 2 across HTTP requests, survives gunicorn worker restarts
- **IntakeSession sidecar** — LangGraph checkpoint tables cannot have `firm_id` added; `IntakeSession` maps `thread_id → firm_id` outside the graph for ownership verification
- **MCP startup auth** — `_resolve_firm_id()` at module import; `sys.exit(1)` on invalid key; `ENVIRONMENT=production` forced to prevent SQLAlchemy echo polluting the stdio JSON-RPC stream
- **Static HTA lookup table** — `hta_reference.py` maps keywords to real Manitoba HTA sections; prevents the LLM from fabricating section numbers
- **Sonnet for quality, Haiku for cost** — Claude Sonnet for lawyer-facing summarization and intake drafts; Claude Haiku for the interactive demo chat (latency + cost optimized)
- **Backend demo proxy** — `/demo/chat` keeps the Anthropic API key server-side; per-IP rate limiting prevents abuse
