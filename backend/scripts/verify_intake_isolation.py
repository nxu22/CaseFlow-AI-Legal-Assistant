"""
Unit 5 cross-tenant attack test for intake session isolation.

Scenario:
  - Alice (Demo Firm) creates an intake session on a Demo Firm case.
    The session contains Demo Firm case content in the LangGraph checkpoint.
  - Bob (Jones Law) somehow obtains Alice's thread_id.
  - Bob tries to resume Alice's intake session via a Jones Law case.
  - Expected: 404 -- the intake_sessions ownership check blocks Bob.

Test 3 uses a REAL end-to-end flow:
  upload document -> Phase 1 (real LangGraph + Claude) -> Phase 2 reject -> assert 200.

Run with the API server already started on port 8001.
"""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE    = "http://localhost:8001"
SEP     = "=" * 60
TIMEOUT = 180   # Phase 1 runs 4 Claude calls; give it 3 minutes

# A realistic Manitoba traffic ticket for the intake agent to process.
TICKET_TEXT = b"""\
TRAFFIC VIOLATION NOTICE
Province of Manitoba - Highway Traffic Act

Notice Number: MAN-2026-UNIT5-001
Date of Offence: June 1, 2026
Location: Route 1 Westbound near Headingley, RM of Headingley

Accused: Jane Smith
Driver Licence: SMIJ-123-456789-MB

Alleged Offence:
Section 95(1) Highway Traffic Act -- Speeding
Speed Recorded: 112 km/h in a posted 90 km/h zone
Issuing Officer: Constable R. Thompson, Badge #4721
Vehicle: 2022 Honda Civic, MB Plate ABC 123

Fine Amount: $230.00
Court Appearance Required: No (pay or contest within 30 days)
"""


def login(email: str, password: str) -> str:
    r = requests.post(
        f"{BASE}/auth/login",
        data={"username": email, "password": password},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


results = {}

print(SEP)
print("Unit 5 -- Intake Session Isolation Attack Test")
print(SEP)

# ── Setup: log in and collect case IDs ────────────────────────────────────────
print("\n[Setup] Logging in as Alice (Demo Firm) and Bob (Jones Law)...")
try:
    alice_token = login("lawyer@caseflow.mb", "Demo1234!")
    bob_token   = login("bob@jones.law",      "BobPass1!")
    print("  Alice login: OK")
    print("  Bob login:   OK")
except Exception as e:
    print(f"  FATAL: login failed -- {e}")
    sys.exit(1)

alice_cases = requests.get(f"{BASE}/cases", headers=auth(alice_token), timeout=10).json()
bob_cases   = requests.get(f"{BASE}/cases", headers=auth(bob_token),   timeout=10).json()

if not alice_cases:
    print("  FATAL: Alice has no cases. Run seed.py first.")
    sys.exit(1)
if not bob_cases:
    print("  FATAL: Bob has no cases. Run setup_tenant_test.py first.")
    sys.exit(1)

alice_case = alice_cases[0]
bob_case   = bob_cases[0]
print(f"  Alice's case : {alice_case['case_number']} ({alice_case['id']})")
print(f"  Bob's case   : {bob_case['case_number']}   ({bob_case['id']})")


# ── Test 1: Bob with a completely made-up thread_id ──────────────────────────
print("\n[Test 1] Bob tries to resume a completely made-up thread_id")
try:
    fake_thread = "00000000-0000-4000-8000-000000000000"
    r = requests.post(
        f"{BASE}/cases/{bob_case['id']}/intake/{fake_thread}/decision",
        headers=auth(bob_token),
        json={"decision": "approve"},
        timeout=10,
    )
    if r.status_code == 404:
        print(f"  Status: {r.status_code} -- 404 as expected")
        print("  PASS")
        results["test1"] = "PASS"
    else:
        print(f"  FAIL -- got {r.status_code}: {r.text[:200]}")
        results["test1"] = "FAIL"
except Exception as e:
    print(f"  ERROR: {e}")
    results["test1"] = "ERROR"


# ── Test 2: Bob obtains Alice's real thread_id and tries to resume it ─────────
# Insert a fake IntakeSession row directly (simulates Alice having run Phase 1
# without needing real S3 + Claude for the attack-isolation test).
print("\n[Test 2] Bob tries to resume Alice's real thread_id")
print("  (Inserting a fake IntakeSession for Demo Firm to simulate Phase 1...)")
alice_thread_id = None
try:
    import uuid as _uuid
    from database import SessionLocal
    from models.intake_session import IntakeSession
    from models.user import User

    DEMO_FIRM_ID    = _uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
    alice_thread_id = str(_uuid.uuid4())

    db = SessionLocal()
    alice_user     = db.query(User).filter(User.firm_id == DEMO_FIRM_ID).first()
    alice_case_uuid = _uuid.UUID(alice_case["id"])

    db.add(IntakeSession(
        thread_id     = alice_thread_id,
        case_id       = alice_case_uuid,
        firm_id       = DEMO_FIRM_ID,
        created_by_id = alice_user.id,
    ))
    db.commit()
    db.close()
    print(f"  Fake session inserted: {alice_thread_id} (firm=Demo Firm)")

    r = requests.post(
        f"{BASE}/cases/{bob_case['id']}/intake/{alice_thread_id}/decision",
        headers=auth(bob_token),
        json={"decision": "approve"},
        timeout=10,
    )
    if r.status_code == 404:
        print(f"  Bob's attack status: {r.status_code} -- 404 as expected")
        print("  PASS -- intake_sessions ownership check blocked Bob")
        results["test2"] = "PASS"
    else:
        print(f"  FAIL -- got {r.status_code}: {r.text[:300]}")
        results["test2"] = "FAIL"
except Exception as e:
    print(f"  ERROR: {e}")
    results["test2"] = "ERROR"


# ── Test 3: Alice runs the full intake flow end-to-end ────────────────────────
# Step A: upload a real document to Alice's case (creates a real S3 object).
# Step B: Phase 1 -- LangGraph runs all 4 nodes, pauses, returns real thread_id.
# Step C: Phase 2 -- Alice resumes with "reject" (no case modification needed).
# Assert: 200 OK with {"status": "rejected"}.
print("\n[Test 3] Alice runs real Phase 1 then Phase 2 (full end-to-end)")
print("  Step A: uploading document to Alice's case...")
try:
    r = requests.post(
        f"{BASE}/cases/{alice_case['id']}/documents",
        headers=auth(alice_token),
        files={"file": ("unit5_ticket.txt", TICKET_TEXT, "text/plain")},
        data={"document_type": "ticket"},
        timeout=30,
    )
    if r.status_code != 201:
        raise RuntimeError(f"Upload failed {r.status_code}: {r.text[:200]}")
    doc_id = r.json()["id"]
    print(f"  Uploaded document: {doc_id}")

    print(f"  Step B: running Phase 1 (real LangGraph + Claude -- may take ~60s)...")
    r = requests.post(
        f"{BASE}/cases/{alice_case['id']}/intake",
        headers=auth(alice_token),
        timeout=TIMEOUT,
    )
    if r.status_code != 202:
        raise RuntimeError(f"Phase 1 failed {r.status_code}: {r.text[:300]}")

    phase1 = r.json()
    real_thread_id = phase1["thread_id"]
    print(f"  Phase 1 complete. thread_id: {real_thread_id}")
    print(f"  Draft preview: {str(phase1.get('draft', ''))[:80]}...")

    print(f"  Step C: Alice resumes with decision=reject...")
    r = requests.post(
        f"{BASE}/cases/{alice_case['id']}/intake/{real_thread_id}/decision",
        headers=auth(alice_token),
        json={"decision": "reject"},
        timeout=60,
    )
    if r.status_code == 200 and r.json().get("status") == "rejected":
        print(f"  Phase 2 status: {r.status_code} {r.json()}")
        print("  PASS -- Alice completed the full intake flow with her own session")
        results["test3"] = "PASS"
    else:
        print(f"  FAIL -- got {r.status_code}: {r.text[:300]}")
        results["test3"] = "FAIL"

except Exception as e:
    print(f"  ERROR: {e}")
    results["test3"] = "ERROR"


# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("SUMMARY")
print(SEP)
for k, v in results.items():
    icon = "[OK]" if v == "PASS" else "[!!]"
    print(f"  {icon} {k.upper()}: {v}")

all_passed = all(v == "PASS" for v in results.values())
print(f"\n{'ALL PASSED -- intake session isolation confirmed.' if all_passed else 'SOME TESTS FAILED.'}")
print(SEP)
