"""
Cross-tenant isolation tests for the demo router (_run_tool is called directly
rather than via HTTP, which is how verify_unit6.py tested it).
"""
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BACKEND_DIR, "routers"))


def test_search_cases_only_demo_firm(ensure_test_data, demo_case_id, jones_case_id):
    """
    Demo search_cases returns only Demo Firm cases.
    Jones Law cases are invisible through the demo entry point.
    """
    from demo import _run_tool
    cases = _run_tool("search_cases", {})
    ids = {c["case_id"] for c in cases}
    assert jones_case_id not in ids, "Jones Law case leaked into demo search results"
    assert demo_case_id  in ids,     "Demo Firm case missing from demo results"


def test_get_case_cross_tenant_blocked(ensure_test_data, jones_case_id):
    """Demo get_case with a Jones Law UUID must return error/not-found."""
    from demo import _run_tool
    result = _run_tool("get_case", {"case_id": jones_case_id})
    assert "error" in result, f"Expected error dict, got: {result}"
    assert "not found" in result["error"].lower()


def test_list_documents_cross_tenant_blocked(ensure_test_data, jones_doc):
    """
    Demo list_documents with a Jones Law case_id must return empty list.
    The case is invisible under DEMO_FIRM_ID RLS scope.
    """
    from demo import _run_tool
    docs = _run_tool("list_documents", {"case_id": jones_doc["case_id"]})
    assert docs == [], f"Expected [], got {docs}"
