"""
Cross-tenant isolation tests for the /cases HTTP endpoints.

Attack model: Bob (Jones Law) tries to read, modify, or delete Demo Firm cases.
Expected: every cross-tenant operation returns 404 (not 403 — we don't confirm
the record exists to the attacker).
"""


def test_list_only_own_firm(api, alice_headers, bob_headers, demo_case_id, jones_case_id):
    """
    Alice's case list must not contain any Jones Law cases.
    Bob's case list must not contain any Demo Firm cases.
    """
    alice_cases = api.get("/cases", headers=alice_headers)
    bob_cases   = api.get("/cases", headers=bob_headers)
    assert alice_cases.status_code == 200
    assert bob_cases.status_code == 200

    alice_ids = {c["id"] for c in alice_cases.json()}
    bob_ids   = {c["id"] for c in bob_cases.json()}

    assert jones_case_id not in alice_ids, "Jones Law case leaked into Alice's list"
    assert demo_case_id  not in bob_ids,   "Demo Firm case leaked into Bob's list"
    assert alice_ids.isdisjoint(bob_ids),  "Firms share case UUIDs — isolation broken"


def test_read_cross_tenant_blocked(api, bob_headers, demo_case_id):
    """Bob cannot read a Demo Firm case by UUID — must get 404."""
    r = api.get(f"/cases/{demo_case_id}", headers=bob_headers)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_update_cross_tenant_blocked(api, bob_headers, demo_case_id):
    """Bob cannot PATCH a Demo Firm case — must get 404, no mutation."""
    r = api.patch(
        f"/cases/{demo_case_id}",
        headers=bob_headers,
        json={"status": "closed_won"},
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_delete_cross_tenant_blocked(api, bob_headers, demo_case_id):
    """Bob cannot DELETE a Demo Firm case — must get 404."""
    r = api.delete(f"/cases/{demo_case_id}", headers=bob_headers)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
