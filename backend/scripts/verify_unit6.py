"""
Unit 6 cross-tenant attack tests.

MCP server started with Demo Firm's API key tries to read/write Jones Law data.
Demo chat endpoint tries to reach non-demo firm data.

PASS = other firm's data blocked
FAIL = data leaked or write succeeded
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models.case import Case
from models.firm import Firm
from seed import DEMO_FIRM_ID

JONES_LAW_ID = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []


def record(name: str, passed: bool, detail: str):
    tag = PASS if passed else FAIL
    print(f"  [{tag}] {name}")
    print(f"         {detail}")
    results.append((name, passed))
    if not passed:
        print(f"\n  !! STOP: leak detected in '{name}'. Aborting remaining tests.")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Setup: fetch a real Jones Law case ID from the DB (direct admin connection)
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("SETUP: fetching Jones Law target case IDs")
print("=" * 60)

db = SessionLocal()
try:
    jones_cases = db.query(Case).filter(Case.firm_id == JONES_LAW_ID).all()
    if not jones_cases:
        print("ERROR: No Jones Law cases found. Run setup_tenant_test.py first.")
        sys.exit(1)

    jones_case_1 = jones_cases[0]
    jones_case_2 = jones_cases[1] if len(jones_cases) > 1 else jones_cases[0]

    JONES_CASE_ID    = str(jones_case_1.id)
    JONES_CASE_NUM   = jones_case_1.case_number
    JONES_STATUS_PRE = jones_case_1.status.value

    demo_cases = db.query(Case).filter(Case.firm_id == DEMO_FIRM_ID).all()
    DEMO_CASE_IDS = {str(c.id) for c in demo_cases}

    print(f"  Jones Law target:  {JONES_CASE_NUM}  id={JONES_CASE_ID[:8]}...")
    print(f"  Jones Law status (pre-attack): {JONES_STATUS_PRE}")
    print(f"  Demo Firm case count: {len(demo_cases)}")
finally:
    db.close()

# ─────────────────────────────────────────────────────────────────────────────
# MCP ATTACKS — server authenticated as Demo Firm
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("MCP ATTACKS (FIRM_API_KEY = demo-firm-api-key-2026)")
print("=" * 60)

os.environ["FIRM_API_KEY"] = "demo-firm-api-key-2026"
import mcp_server  # triggers _resolve_firm_id() at import

# ── MCP Attack 1: search_cases — must return ONLY Demo Firm cases ──────────
print("\nMCP-1: search_cases() — no Jones Law cases should appear")
mcp_cases = mcp_server.search_cases()
jones_in_results = [c for c in mcp_cases if c["case_id"] not in DEMO_CASE_IDS]
only_demo = len(jones_in_results) == 0 and len(mcp_cases) == len(demo_cases)

record(
    "MCP-1: search_cases isolation",
    only_demo,
    f"returned {len(mcp_cases)} cases, all Demo Firm ({len(jones_in_results)} Jones Law leaked)",
)

# ── MCP Attack 2: get_case(jones_law_case_id) — must return "not found" ───
print(f"\nMCP-2: get_case(jones_case_id={JONES_CASE_ID[:8]}...) — must be blocked")
result = mcp_server.get_case(JONES_CASE_ID)
blocked = "error" in result and "not found" in result["error"].lower()

record(
    "MCP-2: get_case cross-tenant read blocked",
    blocked,
    f"result = {result}",
)

# ── MCP Attack 3: update_case_status — must affect 0 rows, no DB change ───
# Pick a target status different from current so a leak would be visible
ATTACK_STATUS = "closed_lost" if JONES_STATUS_PRE != "closed_lost" else "open"

print(f"\nMCP-3: update_case_status({JONES_CASE_ID[:8]}..., '{ATTACK_STATUS}') — must be blocked")
print(f"       Jones Law pre-attack status: {JONES_STATUS_PRE}")

write_result = mcp_server.update_case_status(JONES_CASE_ID, ATTACK_STATUS)
write_blocked = "error" in write_result and "not found" in write_result["error"].lower()

# Verify the DB is unchanged (direct admin read, bypasses RLS)
db = SessionLocal()
try:
    jones_case_after = db.query(Case).filter(Case.id == JONES_CASE_ID).first()
    status_after = jones_case_after.status.value
finally:
    db.close()

db_unchanged = status_after == JONES_STATUS_PRE
attack_fully_blocked = write_blocked and db_unchanged

record(
    "MCP-3: update_case_status cross-tenant WRITE blocked",
    attack_fully_blocked,
    (
        f"tool returned: {write_result}  |  "
        f"DB status before={JONES_STATUS_PRE}, after={status_after}  |  "
        f"{'DB UNCHANGED (correct)' if db_unchanged else '!! DB WAS MODIFIED — WRITE LEAKED !!'}"
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# DEMO ATTACKS — public endpoint, no token
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("DEMO ATTACKS (public /demo/chat endpoint, no JWT)")
print("=" * 60)

from routers.demo import _run_tool

# ── Demo Attack 1: search_cases — must return ONLY Demo Firm cases ─────────
print("\nDEMO-1: search_cases() — no Jones Law cases should appear")
demo_search = _run_tool("search_cases", {})
jones_in_demo = [c for c in demo_search if c["case_id"] not in DEMO_CASE_IDS]
demo_only = len(jones_in_demo) == 0 and len(demo_search) > 0

record(
    "DEMO-1: search_cases isolation",
    demo_only,
    f"returned {len(demo_search)} cases ({len(jones_in_demo)} Jones Law leaked)",
)

# ── Demo Attack 2: get_case(jones_law_case_id) — must return "not found" ──
print(f"\nDEMO-2: get_case(jones_case_id={JONES_CASE_ID[:8]}...) — must be blocked")
demo_get = _run_tool("get_case", {"case_id": JONES_CASE_ID})
demo_blocked = "error" in demo_get and "not found" in demo_get["error"].lower()

record(
    "DEMO-2: get_case cross-tenant read blocked",
    demo_blocked,
    f"result = {demo_get}",
)

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)
total = len(results)
passed = sum(1 for _, ok in results if ok)
for name, ok in results:
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}")
print()
print(f"  {passed}/{total} tests passed")
if passed == total:
    print("  All cross-tenant attacks blocked. Unit 6 COMPLETE.")
else:
    print("  !! ISOLATION FAILURE — investigate immediately.")
