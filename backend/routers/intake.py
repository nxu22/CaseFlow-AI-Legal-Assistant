"""
Intake agent endpoints — human-in-the-loop workflow.

Separate from documents.py by design: documents.py handles file storage
(upload / download / delete), intake.py handles the AI intake workflow
(run → pause → human decision → persist). Single Responsibility Principle.

Endpoints:
  POST /cases/{case_id}/intake
      Phase 1: run the 4-node LangGraph pipeline, pause after draft is ready.
      Returns thread_id + draft for human review. Nothing written to DB.

  POST /cases/{case_id}/intake/{thread_id}/decision
      Phase 2: resume from checkpoint after human decides.
      On approve/edit: write hta_section + ai_summary to the Case record.
      On reject: no DB write.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dependencies import get_current_user, get_db_with_rls
from models.case import Case
from models.document import Document
from models.intake_session import IntakeSession, IntakeDecision, MAX_REDRAFT_COUNT
from models.user import User
from services.intake_agent import IntakeAgentError, resume_intake, run_intake
from services.s3 import S3ServiceError, download_bytes

router = APIRouter(prefix="/cases/{case_id}/intake", tags=["Intake"])


# ── Request / Response schemas ────────────────────────────────────────────────

class DecisionRequest(BaseModel):
    decision: str           # "approve" | "edit" | "reject"
    edited_draft: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_case_or_404(db: Session, case_id: uuid.UUID, firm_id: uuid.UUID) -> Case:
    case = db.query(Case).filter(
        Case.id == case_id,
        Case.firm_id == firm_id,
    ).first()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _bytes_to_text(file_bytes: bytes, mime_type: str) -> str:
    """
    Convert downloaded S3 bytes to a plain-text string for the intake agent.
    text/plain is decoded directly. Other types (PDF, image) are not yet
    supported for intake — upload a text version of the ticket instead.
    """
    if mime_type == "text/plain":
        return file_bytes.decode("utf-8", errors="replace")
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            f"Document type '{mime_type}' is not supported for intake. "
            "Upload the ticket as a plain-text (.txt) file."
        ),
    )


# ── Endpoint 1: POST /cases/{case_id}/intake ──────────────────────────────────

@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_intake(
    case_id: uuid.UUID,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """
    Phase 1: run the intake pipeline on the most recent document for this case.
    The graph pauses after draft_intake — nothing is written to the DB.
    Returns thread_id + draft for the paralegal to review.
    """
    case = _get_case_or_404(db, case_id, current_user.firm_id)

    # Most recent document for this case
    document = (
        db.query(Document)
        .filter(Document.case_id == case.id)
        .order_by(Document.created_at.desc())
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No documents found for this case. Upload a ticket first.",
        )

    # Download file bytes from S3
    try:
        file_bytes = download_bytes(document.s3_key)
    except S3ServiceError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve document from storage.",
        )

    document_text = _bytes_to_text(file_bytes, document.mime_type)

    # Run Phase 1 — pauses after draft, returns thread_id + draft
    try:
        result = run_intake(document_text, db_session=db)
    except IntakeAgentError as e:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE if e.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(e))

    # Record firm ownership of this thread so Phase 2 can verify it.
    db.add(IntakeSession(
        thread_id     = result["thread_id"],
        case_id       = case_id,
        firm_id       = current_user.firm_id,
        created_by_id = current_user.id,
    ))
    db.commit()

    return {
        "thread_id": result["thread_id"],
        "status": result["status"],
        "draft": result["draft"],
        "hta_match": result["hta_match"],
    }


# ── Endpoint 2: POST /cases/{case_id}/intake/{thread_id}/decision ─────────────

@router.post("/{thread_id}/decision", status_code=status.HTTP_200_OK)
def decide_intake(
    case_id: uuid.UUID,
    thread_id: str,
    body: DecisionRequest,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """
    Phase 2: resume from the checkpoint after the human makes a decision.

    approve / edit  → write hta_section + ai_summary to the Case record.
    reject          → no DB write, return status: rejected.
    """
    if body.decision not in ("approve", "edit", "reject", "redraft"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision must be one of: approve, edit, reject, redraft",
        )

    case = _get_case_or_404(db, case_id, current_user.firm_id)

    # Verify the thread belongs to the current firm before resuming.
    # Returns 404 (not 403) to avoid leaking that a foreign thread exists.
    intake_session = db.query(IntakeSession).filter(
        IntakeSession.thread_id == thread_id,
        IntakeSession.firm_id   == current_user.firm_id,
    ).first()
    if intake_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intake session not found",
        )

    # reject: record decision and return — keep the row for analytics
    if body.decision == "reject":
        intake_session.final_decision = IntakeDecision.rejected
        intake_session.decision_at    = datetime.now(timezone.utc)
        db.commit()
        return {"status": "rejected", "case_id": str(case_id)}

    # redraft: check limit before doing anything expensive
    if body.decision == "redraft":
        if intake_session.redraft_count >= MAX_REDRAFT_COUNT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"已达最大重新生成次数（{MAX_REDRAFT_COUNT} 次），请手动编辑或拒绝",
            )
        intake_session.redraft_count += 1
        db.commit()

    # Resume the graph from the saved checkpoint
    try:
        final = resume_intake(thread_id, decision=body.decision, db_session=db)
    except IntakeAgentError as e:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE if e.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(e))

    # approve or edit — persist to the Case record and record decision
    extracted = final.get("extracted") or {}
    hta_match = final.get("hta_match") or {}

    case.hta_section = hta_match.get("section") or extracted.get("hta_section")
    case.ai_summary  = body.edited_draft if body.edited_draft else final.get("draft")

    intake_session.final_decision = IntakeDecision.edited if body.edited_draft else IntakeDecision.approved
    intake_session.decision_at    = datetime.now(timezone.utc)

    db.commit()
    db.refresh(case)

    return {
        "status": final["status"],
        "case_id": str(case_id),
        "hta_section": case.hta_section,
    }
