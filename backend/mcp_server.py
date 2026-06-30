"""
CaseFlow MCP Server
-------------------
Exposes CaseFlow case data as tools that any MCP-compatible AI client
(Claude Desktop, Claude.ai, etc.) can call directly via conversation.

How it works:
  1. Claude Desktop starts this file as a subprocess (stdio transport).
  2. FastMCP reads the function signatures + docstrings and auto-generates
     the tool list that Claude sees.
  3. When you ask Claude "show me open cases", Claude calls search_cases().
  4. This file queries the SAME database as the FastAPI server and returns data.

Tenant isolation (Unit 6):
  Set FIRM_API_KEY in the environment before starting this server.
  The server resolves the firm at startup — if the key is missing or invalid
  it refuses to start.  Every DB tool call executes SET LOCAL app.current_tenant
  so the existing RLS policies on cases/documents/etc. automatically restrict
  results to that firm's data.

Run locally:
  FIRM_API_KEY=demo-firm-api-key-2026 python mcp_server.py

Then configure Claude Desktop to point at this file (see README).
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

# MCP uses stdio — SQLAlchemy echo would corrupt the JSON-RPC stream.
os.environ["ENVIRONMENT"] = "production"

from fastmcp import FastMCP
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from models.case import Case, CaseStatus
from models.client import Client
from models.document import Document
from models.firm import Firm
from services.hta_reference import lookup_hta

# ── Tenant resolution at startup ──────────────────────────────────────────────

def _resolve_firm_id() -> str:
    """
    Authenticate this MCP server instance using FIRM_API_KEY.
    Exits the process immediately if the key is missing or does not match any firm.
    Called once at module import time; result stored as CURRENT_FIRM_ID.
    """
    api_key = os.environ.get("FIRM_API_KEY", "").strip()
    if not api_key:
        print(
            "ERROR: FIRM_API_KEY environment variable is not set. "
            "Set it to your firm's API key before starting the MCP server.",
            file=sys.stderr,
        )
        sys.exit(1)

    db: Session = SessionLocal()
    try:
        firm = db.query(Firm).filter(Firm.api_key == api_key).first()
        if not firm:
            print(
                f"ERROR: No firm found for FIRM_API_KEY '{api_key}'. "
                "Check the key matches what is stored in the firms table.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            f"MCP server authenticated as: {firm.name} (id={firm.id})",
            file=sys.stderr,
        )
        return str(firm.id)
    finally:
        db.close()


CURRENT_FIRM_ID: str = _resolve_firm_id()

# ── Create the MCP server ─────────────────────────────────────────────────────
mcp = FastMCP("CaseFlow")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scoped_db() -> Session:
    """Open a session and immediately scope it to the firm resolved at startup."""
    db: Session = SessionLocal()
    db.execute(text("SET LOCAL app.current_tenant = :fid"), {"fid": CURRENT_FIRM_ID})
    return db


def _case_to_dict(case: Case) -> dict:
    return {
        "case_id": str(case.id),
        "case_number": case.case_number,
        "client": case.client.full_name if case.client else None,
        "status": case.status.value,
        "violation_type": case.violation_type,
        "hta_section": case.hta_section,
        "violation_date": str(case.violation_date) if case.violation_date else None,
        "fine_amount": float(case.fine_amount) if case.fine_amount else None,
        "court_date": str(case.court_date) if case.court_date else None,
        "ai_summary": case.ai_summary,
    }


# ── Tool 1: Search cases ──────────────────────────────────────────────────────
@mcp.tool()
def search_cases(status: str = "", client_name: str = "") -> list[dict]:
    """
    Search CaseFlow cases by status and/or client name.

    Use this when the user asks things like:
    - "show me all open cases"
    - "find cases for Smith"
    - "list in-progress speeding cases"

    Args:
        status: Filter by case status. One of: open, in_progress,
                closed_won, closed_lost, closed_dismissed. Leave blank for all.
        client_name: Partial name match against the client's full name.
                     Leave blank to return all clients.

    Returns a list of matching cases with their key details.
    """
    db = _scoped_db()
    try:
        query = db.query(Case)

        if status:
            try:
                query = query.filter(Case.status == CaseStatus(status))
            except ValueError:
                return [{"error": f"Invalid status '{status}'. Valid values: open, in_progress, closed_won, closed_lost, closed_dismissed"}]

        if client_name:
            query = query.join(Client).filter(
                Client.full_name.ilike(f"%{client_name}%")
            )

        cases = query.order_by(Case.created_at.desc()).limit(20).all()
        return [_case_to_dict(c) for c in cases]
    finally:
        db.close()


# ── Tool 2: Get one case ──────────────────────────────────────────────────────
@mcp.tool()
def get_case(case_id: str) -> dict:
    """
    Get the full details of a single case by its ID.

    Use this when the user asks things like:
    - "tell me more about case CFM-2026-0001"
    - "what's the status of case [id]?"
    - "show me Kowalski's case details"

    Args:
        case_id: The UUID of the case (from search_cases results).

    Returns all case fields including client info, dates, fines, and AI summary.
    """
    db = _scoped_db()
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return {"error": f"Case {case_id} not found"}
        return _case_to_dict(case)
    finally:
        db.close()


# ── Tool 3: List documents for a case ────────────────────────────────────────
@mcp.tool()
def list_documents(case_id: str) -> list[dict]:
    """
    List all documents uploaded to a case.

    Use this when the user asks things like:
    - "what files are attached to this case?"
    - "does case [id] have a ticket uploaded?"

    Args:
        case_id: The UUID of the case.

    Returns filename, document type, size, and AI summary for each document.
    """
    db = _scoped_db()
    try:
        docs = db.query(Document).filter(Document.case_id == case_id).all()
        return [
            {
                "document_id": str(d.id),
                "filename": d.filename,
                "document_type": d.document_type,
                "file_size_kb": round(d.file_size / 1024, 1),
                "ai_summary": d.ai_summary,
                "uploaded_at": str(d.created_at),
            }
            for d in docs
        ]
    finally:
        db.close()


# ── Tool 4: Look up an HTA section ───────────────────────────────────────────
@mcp.tool()
def get_hta_section(text: str) -> dict:
    """
    Look up a Manitoba Highway Traffic Act section by keyword or section number.

    Use this when the user asks things like:
    - "what does s.95(1) cover?"
    - "what's the fine for careless driving?"
    - "look up the HTA section for speeding"

    Args:
        text: A keyword (e.g. "speeding") or section reference (e.g. "s.95(1)").

    Returns the section number, description, fine category, and fine amount.
    """
    match = lookup_hta(text)
    if not match:
        return {"error": f"No HTA section found matching '{text}'"}
    return {
        "section": match["section"],
        "description": match["description"],
        "fine_category": match["fine_category"],
        "fine_amount": match["fine_amount"],
        "notes": match["notes"],
    }


# ── Tool 5: Update case status ────────────────────────────────────────────────
@mcp.tool()
def update_case_status(case_id: str, new_status: str) -> dict:
    """
    Update the status of a case.

    Use this when the user asks things like:
    - "mark case [id] as closed won"
    - "set the Kowalski case to in_progress"

    Valid statuses: open, in_progress, closed_won, closed_lost, closed_dismissed

    Args:
        case_id: The UUID of the case to update.
        new_status: The new status value (see valid statuses above).

    Returns the updated case summary.
    """
    db = _scoped_db()
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return {"error": f"Case {case_id} not found"}
        try:
            case.status = CaseStatus(new_status)
        except ValueError:
            return {"error": f"Invalid status '{new_status}'. Valid: open, in_progress, closed_won, closed_lost, closed_dismissed"}
        db.commit()
        db.refresh(case)
        return {"success": True, "case": _case_to_dict(case)}
    finally:
        db.close()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
