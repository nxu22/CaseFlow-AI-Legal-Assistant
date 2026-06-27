"""
Shared fixtures for the cross-tenant isolation regression suite.

Two firms are used throughout:
  Demo Firm  (aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa)  user: lawyer@caseflow.mb
  Jones Law  (bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb)  user: bob@jones.law

All fixtures are session-scoped — the DB setup runs once per pytest session.
"""
import os
import sys
import uuid

import pytest

# Make backend modules importable from tests/
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.join(BACKEND_DIR, "scripts"))

# Suppress SQLAlchemy query echo during tests
os.environ.setdefault("ENVIRONMENT", "test")

from fastapi.testclient import TestClient

from database import SessionLocal

DEMO_FIRM_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
JONES_LAW_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb")

# psycopg2 URL for the app user (subject to RLS) — used in test_rls_depth.py
APP_DB_URL = "postgresql://caseflow_app:caseflow_app_dev@localhost:5432/caseflow_mb"


# ── Data setup ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def ensure_test_data():
    """
    Guarantee both firms exist with users, cases, clients, and ≥1 document each.
    Idempotent — safe to run against an already-seeded database.
    """
    from seed import seed
    from setup_tenant_test import setup as setup_jones

    db = SessionLocal()
    try:
        from models.user import User
        from models.firm import Firm
        from models.case import Case
        from models.document import Document, DocumentType

        if not db.query(User).filter(User.email == "lawyer@caseflow.mb").first():
            db.close()
            seed()
            db = SessionLocal()

        if not db.query(Firm).filter(Firm.id == JONES_LAW_ID).first():
            db.close()
            setup_jones()
            db = SessionLocal()

        # setup_jones() creates a document on a Demo Firm case (for Bob to attack).
        # If it hasn't been called yet (or the document is missing), call it now.
        demo_case_ids = [
            c.id for c in db.query(Case).filter(Case.firm_id == DEMO_FIRM_ID).all()
        ]
        if not db.query(Document).filter(Document.case_id.in_(demo_case_ids)).first():
            db.close()
            setup_jones()
            db = SessionLocal()

        # Create a Jones Law document if none exists (needed for bidirectional doc tests).
        jones_case = db.query(Case).filter(Case.firm_id == JONES_LAW_ID).first()
        if jones_case and not db.query(Document).filter(Document.case_id == jones_case.id).first():
            jones_user = db.query(User).filter(User.firm_id == JONES_LAW_ID).first()
            db.add(Document(
                case_id=jones_case.id,
                filename="jones-ticket.txt",
                s3_key=f"cases/{jones_case.id}/jones-ticket.txt",
                file_size=512,
                mime_type="text/plain",
                document_type=DocumentType.TICKET,
                uploaded_by_id=jones_user.id,
            ))
            db.commit()
    finally:
        db.close()


# ── HTTP client + auth ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def api(ensure_test_data):
    """FastAPI TestClient — no server process needed, real DB, real RLS."""
    from main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def alice_headers(api):
    """JWT Bearer headers for Alice (Demo Firm lawyer)."""
    r = api.post("/auth/login", data={"username": "lawyer@caseflow.mb", "password": "Demo1234!"})
    assert r.status_code == 200, f"Alice login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def bob_headers(api):
    """JWT Bearer headers for Bob (Jones Law lawyer)."""
    r = api.post("/auth/login", data={"username": "bob@jones.law", "password": "Jones1234!"})
    assert r.status_code == 200, f"Bob login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── Known IDs: cases, clients ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
def demo_case_id(ensure_test_data):
    """UUID string for a Demo Firm case (Bob will try to attack this)."""
    db = SessionLocal()
    try:
        from models.case import Case
        case = db.query(Case).filter(Case.firm_id == DEMO_FIRM_ID).first()
        assert case is not None
        return str(case.id)
    finally:
        db.close()


@pytest.fixture(scope="session")
def jones_case_id(ensure_test_data):
    """UUID string for a Jones Law case (Alice will try to attack this)."""
    db = SessionLocal()
    try:
        from models.case import Case
        case = db.query(Case).filter(Case.firm_id == JONES_LAW_ID).first()
        assert case is not None
        return str(case.id)
    finally:
        db.close()


@pytest.fixture(scope="session")
def demo_client_id(ensure_test_data):
    """UUID string for a Demo Firm client."""
    db = SessionLocal()
    try:
        from models.client import Client
        obj = db.query(Client).filter(Client.firm_id == DEMO_FIRM_ID).first()
        assert obj is not None
        return str(obj.id)
    finally:
        db.close()


@pytest.fixture(scope="session")
def jones_client_id(ensure_test_data):
    """UUID string for a Jones Law client."""
    db = SessionLocal()
    try:
        from models.client import Client
        obj = db.query(Client).filter(Client.firm_id == JONES_LAW_ID).first()
        assert obj is not None
        return str(obj.id)
    finally:
        db.close()


# ── Document fixtures (bidirectional) ─────────────────────────────────────────

@pytest.fixture(scope="session")
def demo_doc(ensure_test_data):
    """
    Dict with 'id' and 'case_id' for a Demo Firm document.
    Bob (Jones Law) uses this as an attack target.
    """
    db = SessionLocal()
    try:
        from models.case import Case
        from models.document import Document
        case_ids = [c.id for c in db.query(Case).filter(Case.firm_id == DEMO_FIRM_ID).all()]
        doc = db.query(Document).filter(Document.case_id.in_(case_ids)).first()
        assert doc is not None, "No Demo Firm document — run setup_tenant_test.py first"
        return {"id": str(doc.id), "case_id": str(doc.case_id)}
    finally:
        db.close()


@pytest.fixture(scope="session")
def jones_doc(ensure_test_data):
    """
    Dict with 'id' and 'case_id' for a Jones Law document.
    Alice (Demo Firm) uses this for bidirectional attack tests.
    Created by ensure_test_data if it doesn't exist.
    """
    db = SessionLocal()
    try:
        from models.case import Case
        from models.document import Document
        jones_case = db.query(Case).filter(Case.firm_id == JONES_LAW_ID).first()
        assert jones_case is not None
        doc = db.query(Document).filter(Document.case_id == jones_case.id).first()
        assert doc is not None, "No Jones Law document — ensure_test_data should have created one"
        return {"id": str(doc.id), "case_id": str(jones_case.id)}
    finally:
        db.close()


# ── Intake thread fixture ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def cross_tenant_thread_id(ensure_test_data, demo_case_id):
    """
    A real intake_sessions row owned by Demo Firm.
    Bob (Jones Law) will try to resume it — the ownership check should 404.
    Uses a direct DB insert so no LangGraph checkpoint is needed for this test.
    """
    thread_id = f"test-isolation-{uuid.uuid4().hex[:12]}"
    db = SessionLocal()
    try:
        from models.intake_session import IntakeSession
        from models.user import User
        alice = db.query(User).filter(User.email == "lawyer@caseflow.mb").first()
        db.add(IntakeSession(
            thread_id=thread_id,
            case_id=uuid.UUID(demo_case_id),
            firm_id=DEMO_FIRM_ID,
            created_by_id=alice.id,
        ))
        db.commit()
    finally:
        db.close()

    yield thread_id

    # Cleanup: remove the test row after the session ends
    db = SessionLocal()
    try:
        from models.intake_session import IntakeSession
        db.query(IntakeSession).filter(IntakeSession.thread_id == thread_id).delete()
        db.commit()
    finally:
        db.close()
