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

Run locally:
  python mcp_server.py

Then configure Claude Desktop to point at this file (see README).
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Absolute path to the backend directory (where this file lives).
BACKEND_DIR = Path(__file__).resolve().parent

# Make sure Python can find our backend modules (database, models, config, etc.)
# when this file is run directly from the terminal.
sys.path.insert(0, str(BACKEND_DIR))

# Explicitly load .env from the backend directory.
# Claude Desktop runs this as a subprocess from an unknown working directory,
# so we must use an absolute path — relative .env loading won't work.
load_dotenv(BACKEND_DIR / ".env")

# MCP uses stdio — SQLAlchemy echo would corrupt the JSON-RPC stream.
os.environ["ENVIRONMENT"] = "production"

from fastmcp import FastMCP
from sqlalchemy.orm import Session

from database import SessionLocal
from models.case import Case, CaseStatus
from models.client import Client
from models.document import Document
from services.hta_reference import lookup_hta

# ── Create the MCP server ─────────────────────────────────────────────────────
# "CaseFlow" is the server name Claude sees when it connects.
mcp = FastMCP("CaseFlow")


# ── Helper ────────────────────────────────────────────────────────────────────
def _case_to_dict(case: Case) -> dict:
    """Convert a Case ORM object to a plain dict Claude can read."""
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
    db: Session = SessionLocal()
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
    db: Session = SessionLocal()
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
    db: Session = SessionLocal()
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
        "section": match.section,
        "description": match.description,
        "fine_category": match.fine_category,
        "fine_amount": match.fine_amount,
        "notes": match.notes,
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
    db: Session = SessionLocal()
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
    # mcp.run() starts the server using stdio transport by default.
    # Claude Desktop launches this as a subprocess and communicates via stdin/stdout.
    mcp.run()
