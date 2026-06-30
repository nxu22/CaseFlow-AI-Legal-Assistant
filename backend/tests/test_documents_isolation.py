"""
Cross-tenant isolation tests for the /cases/{case_id}/documents endpoints.

The document router is nested: case ownership is verified first, so a wrong
case_id returns 404 before any document query fires.  Tests are bidirectional:
both Bob→Demo Firm and Alice→Jones Law directions are covered.
"""
import io


# ── Bob attacks Demo Firm documents ──────────────────────────────────────────

def test_list_via_cross_tenant_case_blocked(api, bob_headers, demo_doc):
    """Bob cannot list documents for a Demo Firm case — case 404 blocks first."""
    r = api.get(f"/cases/{demo_doc['case_id']}/documents", headers=bob_headers)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_download_cross_tenant_blocked(api, bob_headers, demo_doc):
    """Bob cannot get a presigned download URL for a Demo Firm document."""
    r = api.get(
        f"/cases/{demo_doc['case_id']}/documents/{demo_doc['id']}/download",
        headers=bob_headers,
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_upload_to_cross_tenant_case_blocked(api, bob_headers, demo_doc):
    """Bob cannot upload a file to a Demo Firm case."""
    r = api.post(
        f"/cases/{demo_doc['case_id']}/documents",
        headers=bob_headers,
        files={"file": ("evil.txt", io.BytesIO(b"exfiltrate"), "text/plain")},
        data={"document_type": "ticket"},
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_delete_cross_tenant_blocked(api, bob_headers, demo_doc):
    """Bob cannot DELETE a Demo Firm document."""
    r = api.delete(
        f"/cases/{demo_doc['case_id']}/documents/{demo_doc['id']}",
        headers=bob_headers,
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


# ── Bidirectional: Alice attacks Jones Law documents ──────────────────────────

def test_bidirectional_list_blocked(api, alice_headers, jones_doc):
    """Bidirectional: Alice cannot list documents for a Jones Law case."""
    r = api.get(f"/cases/{jones_doc['case_id']}/documents", headers=alice_headers)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_bidirectional_download_blocked(api, alice_headers, jones_doc):
    """Bidirectional: Alice cannot get a download URL for a Jones Law document."""
    r = api.get(
        f"/cases/{jones_doc['case_id']}/documents/{jones_doc['id']}/download",
        headers=alice_headers,
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
