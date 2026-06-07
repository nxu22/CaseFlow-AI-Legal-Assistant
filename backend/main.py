from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres import PostgresSaver

from config import settings
from routers import auth, clients, cases, documents, intake, demo
from services.intake_agent import init_graph


def _pg_url(url: str) -> str:
    """
    Strip the SQLAlchemy driver specifier so psycopg v3 can parse the URL.
    SQLAlchemy uses postgresql+psycopg2:// — psycopg v3 needs postgresql://.
    """
    return (
        url.replace("postgresql+psycopg2://", "postgresql://")
           .replace("postgresql+psycopg://", "postgresql://")
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    App lifespan: create the PostgresSaver once, run setup() to create the
    checkpoint tables if they don't exist, then compile the intake graph.
    The checkpointer connection stays open for the entire app lifetime.
    """
    with PostgresSaver.from_conn_string(_pg_url(settings.DATABASE_URL)) as checkpointer:
        try:
            checkpointer.setup()
        except Exception:
            # Another gunicorn worker already created the checkpoint tables.
            # UniqueViolation on concurrent startup is harmless — tables exist.
            pass
        init_graph(checkpointer)
        yield


app = FastAPI(
    title="CaseFlow MB API",
    description="Case management system for Manitoba traffic defense law firms",
    version="0.1.0",
    lifespan=lifespan,
    root_path="/api",
)

# CORS — 开发阶段放开，生产再收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://15.156.94.248", "https://caseflowmb.site", "https://www.caseflowmb.site"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(cases.router)
app.include_router(documents.router)
app.include_router(intake.router)
app.include_router(demo.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "CaseFlow MB API"}
