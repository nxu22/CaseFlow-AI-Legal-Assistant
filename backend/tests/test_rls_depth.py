"""
RLS defense-in-depth tests — psycopg2 direct to the app user (caseflow_app).

These tests bypass the FastAPI application layer entirely.  They simulate a
developer who forgot the firm_id filter in a query but still called SET LOCAL
via get_db_with_rls.  RLS must catch the leak at the database level.

Nine tests cover all four tables that have RLS policies:
  cases            (direct column comparison in ELSE branch)
  clients          (direct column comparison in ELSE branch)
  documents        (subquery in ELSE branch — fixed by migration b7d3e1a9f5c2)
  intake_sessions  (direct column comparison in ELSE branch)

The documents test specifically guards against regression of the b7d3e1a9f5c2
fix: with GUC = '' (post-commit reset), SELECT documents must not raise
  "invalid input syntax for type uuid: ''"
"""
import os

import pytest
import psycopg2

APP_DB_URL = os.environ.get(
    "APP_DATABASE_URL",
    "postgresql://caseflow_app:caseflow_app_dev@localhost:5432/caseflow_mb",
)
DEMO_FIRM_STR   = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
JONES_FIRM_STR  = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"


def _conn(guc_value: str | None = None):
    """Open a psycopg2 connection as the app user and optionally SET the GUC."""
    c = psycopg2.connect(APP_DB_URL)
    if guc_value is not None:
        with c.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", (guc_value,))
    return c


# ── Cases ─────────────────────────────────────────────────────────────────────

def test_cases_rls_filters_to_guc_tenant(ensure_test_data):
    """
    SET LOCAL → Jones Law.  SELECT * FROM cases (no firm filter).
    RLS must return only Jones Law rows — no Demo Firm rows visible.
    Simulates: developer forgot `Case.firm_id == current_user.firm_id` filter.
    """
    conn = _conn(JONES_FIRM_STR)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT firm_id::text FROM cases")
            firm_ids = {row[0] for row in cur.fetchall()}
        assert firm_ids == {JONES_FIRM_STR}, (
            f"RLS leak: expected only Jones Law, got {firm_ids}"
        )
    finally:
        conn.close()


def test_cases_rls_blocks_cross_tenant_by_id(ensure_test_data, demo_case_id):
    """
    SET LOCAL → Jones Law.  SELECT case by Demo Firm UUID.
    RLS must return 0 rows — the record exists but is invisible to this tenant.
    """
    conn = _conn(JONES_FIRM_STR)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM cases WHERE id = %s::uuid", (demo_case_id,))
            assert cur.fetchone() is None, "Demo Firm case visible under Jones Law GUC"
    finally:
        conn.close()


def test_cases_guc_resets_after_set_local_commit(ensure_test_data):
    """
    SET LOCAL is transaction-scoped: after COMMIT the GUC reverts to ''.
    This is the mechanism that prevents pooled connections from carrying
    stale tenant context between requests.
    """
    conn = psycopg2.connect(APP_DB_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL app.current_tenant = %s", (DEMO_FIRM_STR,))
            cur.execute("SELECT current_setting('app.current_tenant', true)")
            during = cur.fetchone()[0]
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('app.current_tenant', true)")
            after = cur.fetchone()[0]
        assert during == DEMO_FIRM_STR, "GUC not set during transaction"
        assert after  == "",            f"GUC not reset after commit: got '{after}'"
    finally:
        conn.close()


# ── Clients ───────────────────────────────────────────────────────────────────

def test_clients_rls_filters_to_guc_tenant(ensure_test_data):
    """
    SET LOCAL → Jones Law.  SELECT * FROM clients (no firm filter).
    RLS must return only Jones Law clients.
    """
    conn = _conn(JONES_FIRM_STR)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT firm_id::text FROM clients")
            firm_ids = {row[0] for row in cur.fetchall()}
        assert firm_ids == {JONES_FIRM_STR}, (
            f"Clients RLS leak: expected only Jones Law, got {firm_ids}"
        )
    finally:
        conn.close()


def test_clients_rls_blocks_cross_tenant_by_id(ensure_test_data, demo_client_id):
    """
    SET LOCAL → Jones Law.  SELECT Demo Firm client by UUID — must return 0 rows.
    """
    conn = _conn(JONES_FIRM_STR)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM clients WHERE id = %s::uuid", (demo_client_id,))
            assert cur.fetchone() is None, "Demo Firm client visible under Jones Law GUC"
    finally:
        conn.close()


# ── Documents ─────────────────────────────────────────────────────────────────

def test_documents_rls_empty_string_guc_no_error(ensure_test_data):
    """
    Regression guard for migration b7d3e1a9f5c2.

    With GUC = '' (the post-commit/post-RESET state that pooled connections have),
    SELECT * FROM documents must NOT raise:
        "invalid input syntax for type uuid: \"\""

    Before the fix, the documents policy ELSE branch contained a subquery whose
    cast current_setting(...)::uuid failed at PLAN TIME even when the CASE WHEN
    correctly short-circuits at runtime.  The fix wraps the cast in nullif().
    """
    conn = _conn("")   # explicitly set GUC to '' (empty string)
    try:
        with conn.cursor() as cur:
            # This SELECT would raise InvalidTextRepresentation before the fix.
            cur.execute("SELECT COUNT(*) FROM documents")
            count = cur.fetchone()[0]
        assert isinstance(count, int), "documents SELECT returned unexpected result"
    except psycopg2.errors.InvalidTextRepresentation as e:
        pytest.fail(
            f"b7d3e1a9f5c2 regression: documents SELECT raised uuid cast error: {e}\n"
            "Check that the nullif() guard is present in the documents RLS policy."
        )
    finally:
        conn.close()


def test_documents_rls_filters_to_guc_tenant(ensure_test_data):
    """
    SET LOCAL → Jones Law.  SELECT * FROM documents (no case filter).
    RLS must return only documents belonging to Jones Law cases.
    """
    conn = _conn(JONES_FIRM_STR)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT c.firm_id::text
                FROM documents d
                JOIN cases c ON c.id = d.case_id
            """)
            firm_ids = {row[0] for row in cur.fetchall()}
        # May be empty if Jones Law has no documents yet — that's fine (no Demo Firm data)
        assert DEMO_FIRM_STR not in firm_ids, (
            "Demo Firm documents visible under Jones Law GUC"
        )
    finally:
        conn.close()


# ── Intake sessions ───────────────────────────────────────────────────────────

def test_intake_sessions_rls_filters_to_guc_tenant(ensure_test_data, cross_tenant_thread_id):
    """
    SET LOCAL → Jones Law.  SELECT * FROM intake_sessions.
    The cross_tenant_thread_id belongs to Demo Firm — must be invisible here.
    """
    conn = _conn(JONES_FIRM_STR)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT thread_id FROM intake_sessions")
            visible_threads = {row[0] for row in cur.fetchall()}
        assert cross_tenant_thread_id not in visible_threads, (
            "Demo Firm intake_session visible under Jones Law GUC — "
            "intake_sessions RLS policy is not working"
        )
    finally:
        conn.close()


def test_intake_sessions_rls_blocks_cross_tenant_lookup(ensure_test_data, cross_tenant_thread_id):
    """
    SET LOCAL → Jones Law.  Look up the Demo Firm thread by ID — must return 0 rows.
    This is the DB-layer equivalent of the Phase 2 ownership check.
    """
    conn = _conn(JONES_FIRM_STR)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT thread_id FROM intake_sessions WHERE thread_id = %s",
                (cross_tenant_thread_id,),
            )
            assert cur.fetchone() is None, (
                "Demo Firm intake_session visible to Jones Law by thread_id lookup"
            )
    finally:
        conn.close()
