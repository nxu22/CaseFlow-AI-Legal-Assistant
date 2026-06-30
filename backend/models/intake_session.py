import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Enum
import enum


class IntakeDecision(str, enum.Enum):
    approved = "approved"
    edited   = "edited"
    rejected = "rejected"
from sqlalchemy.dialects.postgresql import UUID

from database import Base

MAX_REDRAFT_COUNT = 3


class IntakeSession(Base):
    """
    Maps a LangGraph thread_id to the firm that owns it.

    LangGraph's checkpoint tables are managed by PostgresSaver and cannot
    have a firm_id column added to them. This table is our authoritative
    record of which firm created each intake thread, enabling the same
    firm-ownership check pattern used everywhere else in the codebase.
    """
    __tablename__ = "intake_sessions"

    thread_id      = Column(String,                                       primary_key=True)
    case_id        = Column(UUID(as_uuid=True), ForeignKey("cases.id",    ondelete="CASCADE"), nullable=False)
    firm_id        = Column(UUID(as_uuid=True), ForeignKey("firms.id",    ondelete="RESTRICT"), nullable=False, index=True)
    created_by_id  = Column(UUID(as_uuid=True), ForeignKey("users.id",    ondelete="RESTRICT"), nullable=False)
    created_at     = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    redraft_count   = Column(Integer, nullable=False, default=0)
    final_decision  = Column(Enum(IntakeDecision), nullable=True)
    decision_at     = Column(DateTime(timezone=True), nullable=True)
