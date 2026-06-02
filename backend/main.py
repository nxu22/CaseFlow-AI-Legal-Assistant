from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, clients, cases, documents

app = FastAPI(
    title="CaseFlow MB API",
    description="Case management system for Manitoba traffic defense law firms",
    version="0.1.0",
)

# CORS — 开发阶段放开，生产再收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://15.156.94.248"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(cases.router)
app.include_router(documents.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "CaseFlow MB API"}
