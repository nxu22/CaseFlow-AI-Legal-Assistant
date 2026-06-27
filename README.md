# CaseFlow MB

[![Deploy to EC2](https://github.com/nxu22/CaseFlow-MB/actions/workflows/deploy.yml/badge.svg)](https://github.com/nxu22/CaseFlow-MB/actions/workflows/deploy.yml)

A full-stack case management system for Manitoba traffic defense law firms. Built to manage HTA (Highway Traffic Act) violation cases, clients, and documents — with Claude AI document summarization, an AI-powered intake agent with human-in-the-loop review, an MCP server for Claude Desktop integration, and a public AI demo.

**Live demo:** https://caseflowmb.site
**Login:** `lawyer@caseflow.mb` / `Demo1234!`
**Public AI demo:** https://caseflowmb.site/demo *(no login required)*
**Interactive AI decision map:** https://nxu22.github.io/CaseFlow-AI-Legal-Assistant/

---

## What it does

- **JWT Authentication** — secure login for law firm staff
- **Case Management** — track 20+ HTA violation cases (speeding, careless driving, red light, etc.) with statuses: Open, In Progress, Won, Lost, Dismissed
- **Client Management** — store client profiles with driver's license info
- **Document Upload** — upload PDFs, images, and court notices directly to AWS S3
- **AI Summarization** — one-click Claude AI summary of any uploaded document (reads the file, extracts offence details, dates, fines, and defense notes)
- **Presigned Downloads** — secure time-limited download links from private S3 bucket
- **AI Intake Agent** — LangGraph 4-node pipeline that reads a ticket, matches the HTA section, finds similar cases, and drafts a full intake memo — pauses for lawyer review before writing to the database (human-in-the-loop)
- **MCP Server** — FastMCP server exposing case data as agent tools; connect Claude Desktop to query and manage cases via conversation
- **Public AI Demo** — rate-limited chat interface at `/demo` where anyone can ask about cases and HTA sections; backend proxy keeps the API key server-side only

---

## Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| Python 3.12 | Language |
| FastAPI | REST API framework |
| SQLAlchemy 2.0 | ORM |
| Alembic | Database migrations |
| PostgreSQL 16 | Database |
| Pydantic v2 | Request/response validation |
| python-jose | JWT token signing |
| bcrypt | Password hashing |
| boto3 | AWS S3 integration |
| Anthropic SDK | Claude AI integration |
| LangGraph | AI agent orchestration (intake pipeline) |
| langgraph-checkpoint-postgres | PostgreSQL-backed agent state persistence |
| psycopg v3 | PostgreSQL driver for LangGraph checkpointer |
| FastMCP | MCP server framework (Claude Desktop integration) |
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
└── caseflow_db_prod        (PostgreSQL, internal)
        │
        ▼
   AWS RDS PostgreSQL
   AWS S3 (documents)
   Anthropic API (Claude AI)
   LangGraph (intake agent — state stored in RDS via PostgresSaver)

Claude Desktop ──► mcp_server.py (local) ──► same PostgreSQL
```

---

## AI Intake Agent

The intake pipeline is a 4-node LangGraph `StateGraph` with human-in-the-loop, backed by `PostgresSaver` so state survives server restarts and multi-worker deployments.

```
document text
     │
     ▼
[extract_info]        Claude extracts: accused, offence, speed, date, location, officer
     │
     ▼
[lookup_hta]          Static Manitoba HTA table lookup — prevents AI from fabricating law sections
     │
     ▼
[find_similar]        Searches existing firm cases for similar HTA violations
     │
     ▼
[draft_intake]        Claude drafts a full intake memo
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

---

## MCP Server (Claude Desktop)

`backend/mcp_server.py` exposes CaseFlow as a set of agent tools using FastMCP (stdio transport). Connect Claude Desktop and manage cases via natural language conversation.

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
      "args": ["path/to/backend/mcp_server.py"]
    }
  }
}
```

---

## Public Demo

`https://caseflowmb.site/demo` — no login required. Anyone can ask about cases and HTA sections in plain language.

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
│   ├── database.py          # SQLAlchemy engine + session
│   ├── dependencies.py      # JWT auth dependency
│   ├── security.py          # bcrypt + JWT utilities
│   ├── seed.py              # Demo data (1 lawyer, 8 clients, 20 cases)
│   ├── mcp_server.py        # FastMCP server — Claude Desktop integration
│   ├── models/
│   │   ├── user.py          # Law firm staff
│   │   ├── client.py        # Defendants/clients
│   │   ├── case.py          # HTA violation cases (+ hta_section field)
│   │   └── document.py      # Case documents (metadata only)
│   ├── routers/
│   │   ├── auth.py          # Login, register, /me
│   │   ├── clients.py       # Client CRUD
│   │   ├── cases.py         # Case CRUD + filtering
│   │   ├── documents.py     # Upload, download, AI summarize
│   │   ├── intake.py        # AI intake: run + decision endpoints
│   │   └── demo.py          # Public demo: rate-limited chat proxy
│   ├── schemas/             # Pydantic request/response models
│   ├── services/
│   │   ├── s3.py            # S3 upload/download/presigned URLs
│   │   ├── ai.py            # Claude document summarization
│   │   ├── intake_agent.py  # LangGraph 4-node intake pipeline
│   │   └── hta_reference.py # Static Manitoba HTA section lookup table
│   ├── alembic/             # Database migrations
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
git clone https://github.com/nxu22/CaseFlow-MB.git
cd CaseFlow-MB
```

Create `backend/.env`:
```
DATABASE_URL=postgresql://caseflow:caseflow_dev@localhost:5432/caseflow_mb
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=ca-central-1
AWS_S3_BUCKET=your_bucket
ANTHROPIC_API_KEY=your_key
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
| GET | `/auth/me` | Current user |
| GET | `/clients` | List clients (search + pagination) |
| POST | `/clients` | Create client |
| GET | `/cases` | List cases (filter by status/client) |
| POST | `/cases` | Create case (auto-generates case number) |
| GET | `/cases/{id}` | Case detail |
| PATCH | `/cases/{id}` | Update case |
| POST | `/cases/{id}/documents` | Upload document to S3 |
| GET | `/cases/{id}/documents` | List documents |
| GET | `/cases/{id}/documents/{doc_id}/download` | Get presigned download URL |
| POST | `/cases/{id}/documents/{doc_id}/summarize` | Generate Claude AI summary |
| POST | `/cases/{id}/intake` | Run AI intake agent (Phase 1 — returns draft + thread_id) |
| POST | `/cases/{id}/intake/{thread_id}/decision` | Submit lawyer decision (Phase 2 — approve/reject) |
| POST | `/demo/chat` | Public demo chat (rate-limited, no auth required) |

---

## Key Design Decisions

- **S3 for documents, DB for metadata** — files stored in private S3 bucket, presigned URLs generated on demand (never stored in DB)
- **JWT stateless auth** — no server-side sessions; token carries user identity
- **Separate AI summarize endpoint** — upload is always fast; AI failure doesn't affect upload
- **LangGraph human-in-the-loop** — graph pauses after `draft_intake` with `interrupt_after`; the lawyer reviews the memo in the UI before any DB write happens
- **PostgresSaver for agent state** — checkpoint stored in the same RDS instance; `thread_id` is the key that reconnects Phase 1 and Phase 2 across separate HTTP requests, survives gunicorn worker restarts
- **Static HTA lookup table** — `hta_reference.py` maps keywords to real Manitoba HTA sections; prevents the LLM from fabricating section numbers
- **MCP server as a separate process** — `mcp_server.py` runs as a Claude Desktop subprocess via stdio; reuses the same DB models without touching FastAPI
- **Backend demo proxy** — `/demo/chat` keeps the Anthropic API key server-side; frontend never sees it; per-IP rate limiting prevents abuse
- **Alembic reads DATABASE_URL from env** — works both locally (localhost) and in Docker (service name `db`)
- **Multi-stage frontend build** — builder stage compiles Next.js, runner stage is minimal (smaller image)
- **Elastic IP on EC2** — fixed public IP so DNS doesn't break on instance restart
