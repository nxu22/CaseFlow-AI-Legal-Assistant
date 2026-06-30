"""
Cross-tenant isolation tests for the /clients HTTP endpoints.

Attack model: Bob (Jones Law) tries to read, modify, or delete Demo Firm clients.
"""


def test_list_only_own_firm(api, alice_headers, bob_headers, demo_client_id, jones_client_id):
    """
    Alice's client list must contain only Demo Firm clients.
    Bob's client list must contain only Jones Law clients.
    """
    alice_clients = api.get("/clients", headers=alice_headers)
    bob_clients   = api.get("/clients", headers=bob_headers)
    assert alice_clients.status_code == 200
    assert bob_clients.status_code == 200

    alice_ids = {c["id"] for c in alice_clients.json()}
    bob_ids   = {c["id"] for c in bob_clients.json()}

    assert jones_client_id not in alice_ids, "Jones Law client leaked into Alice's list"
    assert demo_client_id  not in bob_ids,   "Demo Firm client leaked into Bob's list"
    assert alice_ids.isdisjoint(bob_ids),    "Firms share client UUIDs — isolation broken"


def test_read_cross_tenant_blocked(api, bob_headers, demo_client_id):
    """Bob cannot read a Demo Firm client by UUID — must get 404."""
    r = api.get(f"/clients/{demo_client_id}", headers=bob_headers)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_update_cross_tenant_blocked(api, bob_headers, demo_client_id):
    """Bob cannot PATCH a Demo Firm client — must get 404."""
    r = api.patch(
        f"/clients/{demo_client_id}",
        headers=bob_headers,
        json={"full_name": "HACKED"},
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_delete_cross_tenant_blocked(api, bob_headers, demo_client_id):
    """
    Bob cannot DELETE a Demo Firm client — must get 404.
    Note: even if the client has cases, the 404 fires before the FK check.
    """
    r = api.delete(f"/clients/{demo_client_id}", headers=bob_headers)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
