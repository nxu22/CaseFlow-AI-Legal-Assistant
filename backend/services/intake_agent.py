"""
LangGraph intake agent — Step 3: PostgresSaver checkpointing.

Graph: START -> extract_info -> lookup_hta -> find_similar -> draft_intake -> END

Pauses after draft_intake (interrupt_after). Thread state is persisted in
PostgreSQL, so it survives server restarts. The graph is compiled once at
app startup via init_graph(checkpointer) and reused for every request.

Public interface:
    init_graph(checkpointer)                           — called once at startup
    run_intake(document_text, db_session, thread_id)   — Phase 1
    resume_intake(thread_id, decision, db_session)     — Phase 2
"""
from __future__ import annotations

import json
import uuid
from typing import Any, TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph
from langgraph.types import RunnableConfig
from sqlalchemy.orm import Session

from observability import create_trace, langfuse
from services.ai import _client, MODEL  # noqa: WPS436
from services.hta_reference import lookup_hta


class IntakeAgentError(Exception):
    """Raised when a Claude API call inside the graph fails."""
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable

# Active Langfuse traces keyed by thread_id.
# Nodes look up their trace here using the thread_id from LangGraph config.
_active_traces: dict[str, Any] = {}


# ── State schema ──────────────────────────────────────────────────────────────

class IntakeState(TypedDict):
    document_text: str
    extracted: dict[str, Any]
    hta_match: dict[str, Any] | None
    similar_cases: list[dict[str, Any]]
    draft: str


# ── Node 1: extract_info ──────────────────────────────────────────────────────

_EXTRACT_SYSTEM = (
    "You are a paralegal assistant at a Manitoba traffic-defense law firm. "
    "Extract structured facts from a traffic ticket or court document. "
    "Only extract information that is explicitly stated in the document. "
    "Use null for any field not present — never guess or infer."
)

_EXTRACT_USER_TMPL = "Extract the facts from this traffic document:\n\n{document_text}"

# Tool schema forces Claude into a fixed structure — it cannot add extra fields
# or return free-form text. Fields not found in the document must be null.
_EXTRACT_TOOL = {
    "name": "record_ticket_facts",
    "description": (
        "Record the structured facts extracted from a traffic ticket or court document. "
        "Only populate fields that are explicitly present in the document text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "violation_type":   {"type": ["string", "null"], "description": "e.g. 'Speeding' or 'Careless driving'"},
            "hta_section":      {"type": ["string", "null"], "description": "e.g. 's.95(1)' — copy verbatim from document"},
            "violation_date":   {"type": ["string", "null"], "description": "ISO-8601 date or null if not stated"},
            "court_date":       {"type": ["string", "null"], "description": "ISO-8601 date or null if not stated"},
            "fine_amount":      {"type": ["number", "null"], "description": "Numeric dollar amount or null"},
            "accused_name":     {"type": ["string", "null"]},
            "issuing_officer":  {"type": ["string", "null"]},
            "location":         {"type": ["string", "null"]},
            "speed_recorded":   {"type": ["string", "null"], "description": "e.g. '87 km/h in 60 zone'"},
            "additional_notes": {"type": ["string", "null"]},
        },
        "required": [
            "violation_type", "hta_section", "violation_date", "court_date",
            "fine_amount", "accused_name", "issuing_officer", "location",
            "speed_recorded", "additional_notes",
        ],
    },
}


def extract_info(state: IntakeState, config: RunnableConfig) -> dict[str, Any]:
    thread_id = config["configurable"]["thread_id"]
    trace = _active_traces.get(thread_id)
    span = trace.span(name="extract_info") if trace else None

    user_content = _EXTRACT_USER_TMPL.format(document_text=state["document_text"])
    generation = trace.generation(
        name="claude-extract",
        model=MODEL,
        input=user_content,
    ) if trace else None

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=_EXTRACT_SYSTEM,
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "record_ticket_facts"},
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.RateLimitError as e:
        raise IntakeAgentError("AI 服务繁忙，请稍后重试", retryable=True) from e
    except anthropic.APIConnectionError as e:
        raise IntakeAgentError("无法连接到 AI 服务，请检查网络", retryable=True) from e
    except anthropic.APIError as e:
        raise IntakeAgentError(f"AI 服务错误: {e}", retryable=False) from e

    # tool_use blocks contain the structured input — no JSON parsing needed.
    tool_block = next(
        (b for b in response.content if b.type == "tool_use"),
        None,
    )
    extracted = tool_block.input if tool_block else {}

    if generation:
        generation.end(
            output=extracted,
            usage={"input": response.usage.input_tokens, "output": response.usage.output_tokens},
        )
    if span:
        span.end(output=extracted)
    return {"extracted": extracted}


# ── Node 2: lookup_hta ────────────────────────────────────────────────────────

def lookup_hta_node(state: IntakeState, config: RunnableConfig) -> dict[str, Any]:
    thread_id = config["configurable"]["thread_id"]
    trace = _active_traces.get(thread_id)
    span = trace.span(name="lookup_hta") if trace else None

    extracted = state.get("extracted", {})
    search_text = " ".join(filter(None, [
        extracted.get("hta_section") or "",
        extracted.get("violation_type") or "",
    ]))
    match = lookup_hta(search_text)
    result = dict(match) if match else None

    if span:
        span.end(input=search_text, output=result)
    return {"hta_match": result}


# ── Node 3: find_similar ──────────────────────────────────────────────────────

def find_similar(state: IntakeState, config: RunnableConfig) -> dict[str, Any]:
    thread_id = config["configurable"]["thread_id"]
    trace = _active_traces.get(thread_id)
    span = trace.span(name="find_similar") if trace else None
    if span:
        span.end(output={"similar_cases": 0})
    return {"similar_cases": []}


# ── Node 4: draft_intake ──────────────────────────────────────────────────────

_DRAFT_SYSTEM = (
    "You are a paralegal assistant at a Manitoba traffic-defense law firm. "
    "Write a concise case intake memo for the supervising lawyer. "
    "Be factual. Use plain language. Do not invent information."
)

_DRAFT_USER_TMPL = """\
Produce a brief case intake memo based on the following information.

EXTRACTED FACTS:
{extracted}

MATCHING HTA SECTION:
{hta_match}

SIMILAR CASES ON FILE:
{similar_cases}

The memo should cover:
1. Summary of the alleged offence (who, what, where, when)
2. The applicable HTA section and standard fine
3. Relevant precedent from similar cases if any exist
4. Suggested next steps for the defense lawyer (e.g. disclosure request,
   radar/laser calibration records, officer notes)
"""


def draft_intake(state: IntakeState, config: RunnableConfig) -> dict[str, Any]:
    thread_id = config["configurable"]["thread_id"]
    trace = _active_traces.get(thread_id)
    span = trace.span(name="draft_intake") if trace else None

    extracted_str = json.dumps(state.get("extracted") or {}, indent=2)
    hta_str = json.dumps(state.get("hta_match") or "No match found", indent=2)
    similar_str = json.dumps(state.get("similar_cases") or [], indent=2)
    prompt = _DRAFT_USER_TMPL.format(extracted=extracted_str, hta_match=hta_str, similar_cases=similar_str)

    generation = trace.generation(
        name="claude-draft",
        model=MODEL,
        input=prompt,
    ) if trace else None

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=_DRAFT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError as e:
        raise IntakeAgentError("AI 服务繁忙，请稍后重试", retryable=True) from e
    except anthropic.APIConnectionError as e:
        raise IntakeAgentError("无法连接到 AI 服务，请检查网络", retryable=True) from e
    except anthropic.APIError as e:
        raise IntakeAgentError(f"AI 服务错误: {e}", retryable=False) from e

    draft = "".join(b.text for b in response.content if b.type == "text").strip()

    if generation:
        generation.end(
            output=draft,
            usage={"input": response.usage.input_tokens, "output": response.usage.output_tokens},
        )
    if span:
        span.end(output={"draft_length": len(draft)})
    return {"draft": draft}


# ── Graph assembly ────────────────────────────────────────────────────────────

_graph = StateGraph(IntakeState)
_graph.add_node("extract_info", extract_info)
_graph.add_node("lookup_hta", lookup_hta_node)
_graph.add_node("find_similar", find_similar)
_graph.add_node("draft_intake", draft_intake)

_graph.add_edge(START, "extract_info")
_graph.add_edge("extract_info", "lookup_hta")
_graph.add_edge("extract_info", "find_similar")
_graph.add_edge(["lookup_hta", "find_similar"], "draft_intake")
_graph.add_edge("draft_intake", END)

# Compiled app — None until init_graph() is called at startup.
_app: Any = None


def init_graph(checkpointer: Any) -> None:
    """
    Compile the graph with the provided checkpointer. Called once at app
    startup (main.py lifespan). Not thread-safe to call concurrently, but
    startup is single-threaded so this is fine.
    """
    global _app
    _app = _graph.compile(
        checkpointer=checkpointer,
        interrupt_after=["draft_intake"],
    )


# ── Public interface ──────────────────────────────────────────────────────────

def _require_app() -> Any:
    if _app is None:
        raise RuntimeError(
            "Intake graph is not initialized. "
            "Ensure init_graph() is called during app startup."
        )
    return _app


def run_intake(
    document_text: str,
    db_session: Session | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """
    Phase 1: run all four nodes, pause after draft_intake.
    Returns thread_id + status='awaiting_approval' + draft.
    Nothing is written to the database.
    """
    app = _require_app()

    if thread_id is None:
        thread_id = str(uuid.uuid4())

    # Start a Langfuse trace for this intake run.
    # All node spans and generations will be nested under this trace.
    trace = create_trace(
        name="intake-agent",
        input={"document_length": len(document_text)},
        metadata={"thread_id": thread_id},
    )
    _active_traces[thread_id] = trace

    config = {"configurable": {"thread_id": thread_id}}

    initial_state: IntakeState = {
        "document_text": document_text,
        "extracted": {},
        "hta_match": None,
        "similar_cases": [],
        "draft": "",
    }

    try:
        state = app.invoke(initial_state, config=config)
    finally:
        trace.update(output={"status": "awaiting_approval"})
        langfuse.flush()
        _active_traces.pop(thread_id, None)

    return {
        "thread_id": thread_id,
        "status": "awaiting_approval",
        "draft": state.get("draft", ""),
        "extracted": state.get("extracted", {}),
        "hta_match": state.get("hta_match"),
        "similar_cases": state.get("similar_cases", []),
    }


def resume_intake(
    thread_id: str,
    decision: str,
    db_session: Session | None = None,
) -> dict[str, Any]:
    """
    Phase 2: resume from the checkpoint after the human decides.
    Passing None resumes from the interrupt point without re-running nodes.
    """
    app = _require_app()
    config = {"configurable": {"thread_id": thread_id}}
    final_state = app.invoke(None, config=config)

    return {
        "thread_id": thread_id,
        "decision": decision,
        "status": "approved" if decision == "approve" else decision,
        "draft": final_state.get("draft", ""),
        "extracted": final_state.get("extracted", {}),
        "hta_match": final_state.get("hta_match"),
        "similar_cases": final_state.get("similar_cases", []),
    }
