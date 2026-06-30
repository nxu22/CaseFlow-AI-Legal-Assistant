"""
Cross-tenant isolation tests for the intake (LangGraph) endpoints.

Three fast tests require no real LangGraph checkpoint:
  1. Bob tries Phase 1 on Alice's case           → 404 (case check fires first)
  2. Bob tries Phase 2 with a fake thread_id     → 404 (ownership check)
  3. Bob tries Phase 2 with Alice's real thread  → 404 (ownership check)

One slow test runs a real Claude call:
  4. Alice runs Phase 1 + Phase 2 end-to-end     → 200 (positive — her own session)

Run fast tests only:  pytest -m "not slow"
"""
import pytest


def test_phase1_cross_tenant_case_blocked(api, bob_headers, demo_case_id):
    """
    Bob tries to start intake on a Demo Firm case.
    _get_case_or_404 fires before any LangGraph or S3 call — fast 404.
    """
    r = api.post(f"/cases/{demo_case_id}/intake", headers=bob_headers)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_phase2_fake_thread_blocked(api, bob_headers, jones_case_id):
    """
    Bob supplies a completely invented thread_id.
    There's no intake_sessions row at all — ownership check returns 404.
    """
    r = api.post(
        f"/cases/{jones_case_id}/intake/totally-fake-thread-xyz/decision",
        headers=bob_headers,
        json={"decision": "reject"},
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_phase2_cross_tenant_thread_blocked(api, bob_headers, jones_case_id, cross_tenant_thread_id):
    """
    Bob obtains Alice's real thread_id (it exists in intake_sessions).
    He pairs it with his own valid case_id to pass the case check.
    The ownership check (firm_id == jones_law) still blocks him — 404.
    """
    r = api.post(
        f"/cases/{jones_case_id}/intake/{cross_tenant_thread_id}/decision",
        headers=bob_headers,
        json={"decision": "reject"},
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


@pytest.mark.slow
def test_phase2_own_thread_succeeds(api, alice_headers, demo_case_id, demo_doc):
    """
    Alice completes the full intake flow with her own session — must succeed.
    This is the positive test: proves isolation doesn't over-block legitimate users.
    Requires a real Claude call (~60s).
    """
    import io

    # Phase 1: upload a document first (needs a real S3-uploaded doc,
    # but we test against the existing demo_doc that setup already created).
    # Start Phase 1 directly using demo_doc's case (already has a document).
    r1 = api.post(
        f"/cases/{demo_doc['case_id']}/intake",
        headers=alice_headers,
        timeout=180,
    )
    assert r1.status_code == 202, f"Phase 1 failed {r1.status_code}: {r1.text[:300]}"
    thread_id = r1.json()["thread_id"]
    assert thread_id, "Phase 1 returned no thread_id"

    # Phase 2: Alice resumes her own thread
    r2 = api.post(
        f"/cases/{demo_doc['case_id']}/intake/{thread_id}/decision",
        headers=alice_headers,
        json={"decision": "reject"},
        timeout=60,
    )
    assert r2.status_code == 200, f"Phase 2 failed {r2.status_code}: {r2.text[:300]}"
    assert r2.json().get("status") == "rejected"
