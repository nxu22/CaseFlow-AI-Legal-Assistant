"""
Cross-tenant isolation tests for the MCP server subprocess.

mcp_server.py is imported directly (not via HTTP) with FIRM_API_KEY set.
Startup rejection tests use subprocess to avoid Python's module-import cache.
"""
import os
import subprocess
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_KEY   = "demo-firm-api-key-2026"
JONES_KEY  = "jones-law-api-key-2026"


# ── Startup auth ──────────────────────────────────────────────────────────────

def test_startup_missing_key_refused():
    """mcp_server refuses to start when FIRM_API_KEY is not set."""
    env = {**os.environ, "FIRM_API_KEY": ""}
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); import mcp_server"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "FIRM_API_KEY environment variable is not set" in result.stderr


def test_startup_invalid_key_refused():
    """mcp_server refuses to start when FIRM_API_KEY doesn't match any firm."""
    env = {**os.environ, "FIRM_API_KEY": "totally-wrong-key"}
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); import mcp_server"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "No firm found" in result.stderr


# ── Module-level import with Demo Firm key ────────────────────────────────────
# Importing mcp_server runs _resolve_firm_id() once.  The module fixture below
# ensures the env var is set before the import, and uses module scope so the
# import happens once for all tests in this file.

@pytest.fixture(scope="module")
def mcp(ensure_test_data):
    os.environ["FIRM_API_KEY"] = DEMO_KEY
    # Re-import in case a previous test already imported with a different key
    if "mcp_server" in sys.modules:
        del sys.modules["mcp_server"]
    import mcp_server as _mcp
    yield _mcp


# ── Isolation tests ───────────────────────────────────────────────────────────

def test_search_cases_only_demo_firm(mcp, demo_case_id, jones_case_id):
    """search_cases() returns only Demo Firm cases — Jones Law cases not visible."""
    cases = mcp.search_cases()
    ids = {c["case_id"] for c in cases}
    assert jones_case_id not in ids, "Jones Law case leaked into MCP search results"
    assert demo_case_id  in ids,     "Demo Firm case missing from own MCP results"


def test_get_case_cross_tenant_blocked(mcp, jones_case_id):
    """get_case() with a Jones Law UUID returns 'not found' — not the actual case."""
    result = mcp.get_case(jones_case_id)
    assert "error" in result
    assert "not found" in result["error"].lower()


def test_list_documents_cross_tenant_blocked(mcp, jones_doc):
    """
    list_documents() with a Jones Law case_id must return an empty list.
    RLS filters out the case, so no documents are visible — not an error,
    just an empty result (the case itself doesn't exist under Demo Firm's view).
    """
    docs = mcp.list_documents(jones_doc["case_id"])
    assert docs == [], f"Expected [], got {docs}"


def test_update_status_cross_tenant_write_blocked(mcp, jones_case_id, ensure_test_data):
    """
    update_case_status() with a Jones Law case_id must return 'not found'
    AND must leave the DB record unchanged.
    """
    from database import SessionLocal
    from models.case import Case
    import uuid

    # Record pre-attack status directly from DB (bypasses RLS via admin ORM)
    db = SessionLocal()
    try:
        jones_case = db.query(Case).filter(Case.id == uuid.UUID(jones_case_id)).first()
        status_before = jones_case.status.value
    finally:
        db.close()

    # Attack
    result = mcp.update_case_status(jones_case_id, "closed_lost")
    assert "error" in result
    assert "not found" in result["error"].lower()

    # Verify DB unchanged
    db = SessionLocal()
    try:
        jones_case = db.query(Case).filter(Case.id == uuid.UUID(jones_case_id)).first()
        assert jones_case.status.value == status_before, (
            f"Write leaked! Status changed from {status_before} to {jones_case.status.value}"
        )
    finally:
        db.close()
