# CaseFlow MB

A full-stack case management system for Manitoba traffic defense law firms. Built to manage HTA (Highway Traffic Act) violation cases, clients, and documents — with Claude AI document summarization.

**Live demo:** http://15.156.94.248  
**Login:** `lawyer@caseflow.mb` / `Demo1234!`

---

## What it does

- **JWT Authentication** — secure login for law firm staff
- **Case Management** — track 20+ HTA violation cases (speeding, careless driving, red light, etc.) with statuses: Open, In Progress, Won, Lost, Dismissed
- **Client Management** — store client profiles with driver's license info
- **Document Upload** — upload PDFs, images, and court notices directly to AWS S3
- **AI Summarization** — one-click Claude AI summary of any uploaded document (reads the file, extracts offence details, dates, fines, and defense notes)
- **Presigned Downloads** — secure time-limited download links from private S3 bucket

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
| Docker + Docker Compose | Containerization |
| GitHub | Version control |

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
   Anthropic API (AI summaries)
```

---

## Project Structure

```
CaseFlow-MB/
├── backend/
│   ├── main.py              # FastAPI app + CORS
│   ├── config.py            # Pydantic settings (env vars)
│   ├── database.py          # SQLAlchemy engine + session
│   ├── dependencies.py      # JWT auth dependency
│   ├── security.py          # bcrypt + JWT utilities
│   ├── seed.py              # Demo data (1 lawyer, 8 clients, 20 cases)
│   ├── models/
│   │   ├── user.py          # Law firm staff
│   │   ├── client.py        # Defendants/clients
│   │   ├── case.py          # HTA violation cases
│   │   └── document.py      # Case documents (metadata only)
│   ├── routers/
│   │   ├── auth.py          # Login, register, /me
│   │   ├── clients.py       # Client CRUD
│   │   ├── cases.py         # Case CRUD + filtering
│   │   └── documents.py     # Upload, download, AI summarize
│   ├── schemas/             # Pydantic request/response models
│   ├── services/
│   │   ├── s3.py            # S3 upload/download/presigned URLs
│   │   └── ai.py            # Claude document summarization
│   ├── alembic/             # Database migrations
│   ├── Dockerfile           # Development image
│   └── Dockerfile.prod      # Production image (gunicorn)
├── frontend/
│   ├── app/
│   │   ├── login/           # Login page
│   │   └── cases/
│   │       ├── layout.tsx   # Nav bar + auth guard
│   │       ├── page.tsx     # Cases list table
│   │       └── [id]/        # Case detail + document upload + AI summary
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

Open http://localhost:3000

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

---

## Key Design Decisions

- **S3 for documents, DB for metadata** — files stored in private S3 bucket, presigned URLs generated on demand (never stored in DB)
- **JWT stateless auth** — no server-side sessions; token carries user identity
- **Separate AI summarize endpoint** — upload is always fast; AI failure doesn't affect upload
- **Alembic reads DATABASE_URL from env** — works both locally (localhost) and in Docker (service name `db`)
- **Multi-stage frontend build** — builder stage compiles Next.js, runner stage is minimal (smaller image)
