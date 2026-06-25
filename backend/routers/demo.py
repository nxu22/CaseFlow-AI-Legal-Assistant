"""
Public demo endpoint — safe, rate-limited, key-never-exposed-to-frontend.

Architecture:
  Browser → POST /demo/chat → this file → Anthropic API → response
  The Anthropic API key lives only in the backend environment variable.

Security measures built in:
  - API key never sent to frontend
  - Per-IP rate limit (10 requests / hour)
  - Max tokens cap per request
  - Read-only tools (no writes exposed in demo)
  - System prompt constrains Claude to CaseFlow topics only
  - Message length capped at 500 chars
"""

import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import anthropic
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models.case import Case, CaseStatus
from models.client import Client
from models.document import Document
from observability import create_trace, langfuse
from services.hta_reference import lookup_hta

router = APIRouter(prefix="/demo", tags=["demo"])

# ── Rate limiter (in-memory, per IP) ─────────────────────────────────────────
_ip_requests: dict[str, list[datetime]] = defaultdict(list)
_lock = threading.Lock()

RATE_LIMIT = 10           # requests per window
RATE_WINDOW = timedelta(hours=1)
MAX_MSG_LEN = 500         # characters


def _check_rate_limit(ip: str) -> bool:
    with _lock:
        now = datetime.utcnow()
        cutoff = now - RATE_WINDOW
        _ip_requests[ip] = [t for t in _ip_requests[ip] if t > cutoff]
        if len(_ip_requests[ip]) >= RATE_LIMIT:
            return False
        _ip_requests[ip].append(now)
        return True


# ── Tool definitions (Anthropic tool_use schema) ──────────────────────────────
TOOLS: list[dict] = [
    {
        "name": "search_cases",
        "description": "Search CaseFlow cases by status and/or client name. Returns up to 20 matching cases.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: open, in_progress, closed_won, closed_lost, closed_dismissed. Leave empty for all.",
                },
                "client_name": {
                    "type": "string",
                    "description": "Partial name match against client full name. Leave empty for all clients.",
                },
            },
        },
    },
    {
        "name": "get_case",
        "description": "Get full details of a single case by its UUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "The UUID of the case."},
            },
            "required": ["case_id"],
        },
    },
    {
        "name": "list_documents",
        "description": "List all documents attached to a case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "The UUID of the case."},
            },
            "required": ["case_id"],
        },
    },
    {
        "name": "get_hta_section",
        "description": "Look up a Manitoba Highway Traffic Act section by keyword or section number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Keyword (e.g. 'speeding') or section reference (e.g. 's.95(1)').",
                },
            },
            "required": ["text"],
        },
    },
]

SYSTEM_PROMPT = """You are a demo assistant for CaseFlow MB, a case management system for Manitoba traffic defense law firms.

You can help users explore the demo database of HTA (Highway Traffic Act) cases.

You have access to these tools:
- search_cases: find cases by status or client name
- get_case: get full details of a specific case
- list_documents: list documents attached to a case
- get_hta_section: look up Manitoba HTA sections

Stay focused on CaseFlow and Manitoba traffic law topics. Do not discuss unrelated subjects.
All data shown is demo/seed data — no real client information."""


# ── Tool execution ─────────────────────────────────────────────────────────────
def _run_tool(name: str, inputs: dict) -> Any:
    db: Session = SessionLocal()
    try:
        if name == "search_cases":
            query = db.query(Case)
            status = inputs.get("status", "").strip()
            client_name = inputs.get("client_name", "").strip()
            if status:
                try:
                    query = query.filter(Case.status == CaseStatus(status))
                except ValueError:
                    return {"error": f"Invalid status '{status}'"}
            if client_name:
                query = query.join(Client).filter(Client.full_name.ilike(f"%{client_name}%"))
            cases = query.order_by(Case.created_at.desc()).limit(20).all()
            return [_case_dict(c) for c in cases]

        if name == "get_case":
            case = db.query(Case).filter(Case.id == inputs["case_id"]).first()
            return _case_dict(case) if case else {"error": "Case not found"}

        if name == "list_documents":
            docs = db.query(Document).filter(Document.case_id == inputs["case_id"]).all()
            return [
                {
                    "document_id": str(d.id),
                    "filename": d.filename,
                    "document_type": d.document_type,
                    "file_size_kb": round(d.file_size / 1024, 1),
                    "ai_summary": d.ai_summary,
                }
                for d in docs
            ]

        if name == "get_hta_section":
            match = lookup_hta(inputs["text"])
            if not match:
                return {"error": f"No HTA section found for '{inputs['text']}'"}
            return {
                "section": match.section,
                "description": match.description,
                "fine_category": match.fine_category,
                "fine_amount": match.fine_amount,
                "notes": match.notes,
            }

        return {"error": f"Unknown tool: {name}"}
    finally:
        db.close()


def _case_dict(case: Case) -> dict:
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


# ── Endpoint ───────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    tool_calls_made: int


@router.post("/chat", response_model=ChatResponse)
def demo_chat(body: ChatRequest, request: Request):
    # 1. Message validation
    msg = body.message.strip()
    if not msg:
        raise HTTPException(400, "Message cannot be empty")
    if len(msg) > MAX_MSG_LEN:
        raise HTTPException(400, f"Message too long (max {MAX_MSG_LEN} characters)")

    # 2. Rate limit
    client_ip = request.client.host
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, f"Rate limit exceeded. Max {RATE_LIMIT} requests per hour.")

    # 3. Agentic loop — Claude + tools
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": msg}]
    tool_calls_made = 0
    demo_model = "claude-haiku-4-5-20251001"

    # One trace per user message — captures the full agentic conversation
    trace = create_trace(
        name="demo-chat",
        input={"message": msg},
        metadata={"ip": client_ip},
    )

    try:
        for round_num in range(5):
            round_span = trace.span(name=f"round-{round_num + 1}")

            generation = trace.generation(
                name="claude-haiku-call",
                model=demo_model,
                input=messages,
            )

            response = client.messages.create(
                model=demo_model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            generation.end(
                output={"stop_reason": response.stop_reason},
                usage={
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                },
            )

            if response.stop_reason == "end_turn":
                text = " ".join(b.text for b in response.content if hasattr(b, "text"))
                round_span.end(output={"stop_reason": "end_turn"})
                trace.update(output={"reply": text[:200], "tool_calls_made": tool_calls_made})
                langfuse.flush()
                return ChatResponse(reply=text, tool_calls_made=tool_calls_made)

            if response.stop_reason == "tool_use":
                tool_calls_made += len([b for b in response.content if b.type == "tool_use"])
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_span = trace.span(
                            name=f"tool:{block.name}",
                            input=block.input,
                        )
                        result = _run_tool(block.name, block.input)
                        tool_span.end(output=result if isinstance(result, dict) else {"result": str(result)[:300]})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        })
                messages.append({"role": "user", "content": tool_results})
                round_span.end(output={"tool_calls": tool_calls_made})
                continue

            round_span.end()
            break
    finally:
        langfuse.flush()

    raise HTTPException(500, "Demo agent did not produce a response")
