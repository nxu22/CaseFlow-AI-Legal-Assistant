"""
RLS Independent Verification Tests — Unit 4.

All tests connect as caseflow_app (non-superuser, non-table-owner).
If any test accidentally connected as caseflow (superuser), RLS would be
bypassed and every test would give a false PASS. The role is verified
explicitly at the start of each test.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models.case import Case

JONES_LAW_ID  = 'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb'
DEMO_FIRM_ID  = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa'
APP_DB_URL    = "postgresql://caseflow_app:caseflow_app_dev@localhost:5432/caseflow_mb"

results = {}

SEP = "=" * 62
print(SEP)
print("RLS INDEPENDENT VERIFICATION -- all tests run as caseflow_app")
print(SEP)


def _check_role(cur):
    """Assert we are NOT a superuser. Aborts the test if we are."""
    cur.execute(
        "SELECT current_user, current_setting('is_superuser')"
    )
    user, is_su = cur.fetchone()
    if is_su == 'on':
        raise RuntimeError(f"Connected as superuser '{user}' — test would be meaningless!")
    return user


# ── Test 1: forgotten filter — RLS still blocks ───────────────────────────────
print("\n[Test 1] RLS catches a 'forgotten filter' raw query")
try:
    conn = psycopg2.connect(APP_DB_URL)
    cur  = conn.cursor()
    role = _check_role(cur)
    print(f"  Role: {role} (not superuser OK)")

    cur.execute("BEGIN")
    cur.execute("SET LOCAL app.current_tenant = %s", (JONES_LAW_ID,))

    # Deliberately NO WHERE on firm_id — simulating a programmer who forgot
    cur.execute("SELECT case_number, firm_id::text FROM cases")
    rows = cur.fetchall()
    conn.rollback()
    cur.close(); conn.close()

    jones = [r for r in rows if r[1] == JONES_LAW_ID]
    other = [r for r in rows if r[1] != JONES_LAW_ID]

    if len(jones) == 2 and len(other) == 0:
        print(f"  Jones Law cases visible : {len(jones)}  ({[r[0] for r in jones]})")
        print(f"  Demo Firm cases visible : {len(other)}  (expected 0 — all 20 blocked by RLS)")
        print("  PASS")
        results['test1'] = 'PASS'
    else:
        print(f"  FAIL — jones={len(jones)}, other={len(other)}")
        results['test1'] = 'FAIL'
except Exception as e:
    print(f"  ERROR: {e}")
    results['test1'] = 'ERROR'


# ── Test 2: by-ID attack — RLS blocks at DB layer ────────────────────────────
print("\n[Test 2] RLS blocks a by-ID attack at the DB layer")
try:
    # Get a real Demo Firm case UUID (no tenant set → IS NULL branch → all rows visible)
    conn = psycopg2.connect(APP_DB_URL)
    cur  = conn.cursor()
    cur.execute("SELECT id::text FROM cases WHERE firm_id = %s LIMIT 1", (DEMO_FIRM_ID,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if row is None:
        raise RuntimeError("No Demo Firm cases found — run seed.py first")
    demo_case_id = row[0]
    print(f"  Attack target (Demo Firm case): {demo_case_id}")

    conn = psycopg2.connect(APP_DB_URL)
    cur  = conn.cursor()
    role = _check_role(cur)
    print(f"  Role: {role} (not superuser OK)")

    cur.execute("BEGIN")
    cur.execute("SET LOCAL app.current_tenant = %s", (JONES_LAW_ID,))

    # Correct UUID, wrong firm — should return 0 rows
    cur.execute("SELECT case_number FROM cases WHERE id = %s", (demo_case_id,))
    rows = cur.fetchall()
    conn.rollback()
    cur.close(); conn.close()

    if len(rows) == 0:
        print(f"  Rows returned for Demo Firm case UUID: 0 (expected 0)")
        print("  PASS — RLS blocked it at DB layer with no app filter involved")
        results['test2'] = 'PASS'
    else:
        print(f"  FAIL — got {len(rows)} row(s): {rows}")
        results['test2'] = 'FAIL'
except Exception as e:
    print(f"  ERROR: {e}")
    results['test2'] = 'ERROR'


# ── Test 3: SET LOCAL transaction isolation ───────────────────────────────────
print("\n[Test 3] SET LOCAL transaction isolation (pooled connection stays clean)")
try:
    conn = psycopg2.connect(APP_DB_URL)
    cur  = conn.cursor()
    role = _check_role(cur)
    print(f"  Role: {role} (not superuser OK)")

    # Inside transaction: SET LOCAL
    cur.execute("BEGIN")
    cur.execute("SET LOCAL app.current_tenant = %s", (JONES_LAW_ID,))
    cur.execute("SELECT current_setting('app.current_tenant', true)")
    during = cur.fetchone()[0]

    conn.commit()  # transaction ends — SET LOCAL should revert

    # After commit on the SAME connection
    cur.execute("SELECT current_setting('app.current_tenant', true)")
    after = cur.fetchone()[0]

    cur.close(); conn.close()

    print(f"  During transaction : '{during}'")
    print(f"  After commit       : '{after}' (NULL or '' means the UUID is gone)")

    reverted = (after is None or after == '' or after != JONES_LAW_ID)
    if during == JONES_LAW_ID and reverted:
        print("  PASS — SET LOCAL reverted after commit; pooled connection won't carry stale tenant")
        results['test3'] = 'PASS'
    else:
        print(f"  FAIL — variable still '{after}' after transaction ended")
        results['test3'] = 'FAIL'
except Exception as e:
    print(f"  ERROR: {e}")
    results['test3'] = 'ERROR'


# ── Test 4: app-layer filter bypassed — RLS still holds ──────────────────────
print("\n[Test 4] App-layer filter bypassed -- RLS still holds  << THE KEY TEST")
try:
    # SQLAlchemy engine connecting as caseflow_app (same role the app uses)
    engine = create_engine(APP_DB_URL, echo=False)
    Session = sessionmaker(bind=engine)
    db = Session()

    role = db.execute(text("SELECT current_user")).scalar()
    is_su = db.execute(text("SELECT current_setting('is_superuser')")).scalar()
    if is_su == 'on':
        raise RuntimeError(f"Connected as superuser '{role}' — test meaningless!")
    print(f"  Role: {role} (not superuser OK)")

    # Set tenant to Bob's firm — same as get_db_with_rls would do
    db.execute(text("SET LOCAL app.current_tenant = :fid"), {"fid": JONES_LAW_ID})

    # THE SIMULATED BUG: a query with NO firm_id filter
    all_cases = db.query(Case).all()

    jones = [c for c in all_cases if str(c.firm_id) == JONES_LAW_ID]
    other = [c for c in all_cases if str(c.firm_id) != JONES_LAW_ID]

    db.close()
    engine.dispose()

    print(f"  db.query(Case).all()  — no WHERE clause, no firm filter")
    print(f"  Jones Law cases returned : {len(jones)}  ({[c.case_number for c in jones]})")
    print(f"  Other-firm cases returned: {len(other)}  (expected 0 — RLS should block them)")

    if len(jones) == 2 and len(other) == 0:
        print("  PASS — RLS held even when the app forgot the filter. Defense-in-depth confirmed.")
        results['test4'] = 'PASS'
    else:
        print(f"  FAIL — {len(other)} case(s) from other firms leaked through")
        results['test4'] = 'FAIL'
except Exception as e:
    print(f"  ERROR: {e}")
    results['test4'] = 'ERROR'


# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("SUMMARY")
print(SEP)
for k, v in results.items():
    icon = "[OK]" if v == 'PASS' else "[!!]"
    print(f"  {icon} {k.upper()}: {v}")

all_passed = all(v == 'PASS' for v in results.values())
msg = "ALL PASSED — database-layer isolation is real and independent." if all_passed else "SOME TESTS FAILED."
print(f"\n{msg}")
print(SEP)
