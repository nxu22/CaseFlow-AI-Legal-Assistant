"""
Case model: a legal matter handled by the firm.

A case represents one client's traffic violation incident, from intake
through court hearing to resolution. Cases are the central entity—
documents, notes, and billing all hang off them.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class CaseStatus(str, enum.Enum):
    """
    Lifecycle states of a traffic defense case.

    Granular closure states (won/lost/dismissed) let the firm track
    win rates and dismissal rates as business KPIs.
    """
    OPEN = "open"                       # intake complete, awaiting work
    IN_PROGRESS = "in_progress"          # actively being defended
    CLOSED_WON = "closed_won"            # ticket overturned at trial
    CLOSED_LOST = "closed_lost"          # original ruling upheld
    CLOSED_DISMISSED = "closed_dismissed"  # dismissed on procedural grounds


class Case(Base):
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    firm_id = Column(
        UUID(as_uuid=True),
        ForeignKey("firms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Firm-internal case number, e.g. "CFM-2026-0042".
    # Unique + indexed: staff search by this number constantly.
    case_number = Column(String(50), unique=True, nullable=False, index=True)

    # FK to clients. RESTRICT prevents accidental client deletion when
    # cases still reference them—forces explicit cleanup.
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # FK to users. SET NULL on delete: if a lawyer leaves and is hard-deleted,
    # cases become "unassigned" rather than orphaned.
    # Indexed because "my cases" view filters on this column.
    assigned_lawyer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status = Column(
        Enum(CaseStatus, name="case_status_enum"),
        nullable=False,
        default=CaseStatus.OPEN,
        index=True,  # filtering by status is a common query
    )

    # Violation type from Winnipeg Open Data taxonomy
    # (e.g. "Speeding - 10 to 20 km/h over limit").
    violation_type = Column(String(255), nullable=True)

    # HTA section matched by the intake agent, e.g. "s.95(1)".
    hta_section = Column(String(50), nullable=True)

    violation_date = Column(Date, nullable=True)

    # Money column: Numeric, never Float. Float arithmetic is binary and
    # loses precision (0.1 + 0.2 != 0.3). Numeric(10, 2) = up to 99,999,999.99.
    fine_amount = Column(Numeric(10, 2), nullable=True)

    court_date = Column(Date, nullable=True)

    description = Column(Text, nullable=True)

    # Claude-generated summary of attached documents. Populated by Day 2 feature.
    ai_summary = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ORM relationships: enables case.client and case.documents in Python
    # without manual JOINs. lazy='selectin' loads related objects in a single
    # extra query (avoids N+1) when accessed.
    client = relationship("Client", backref="cases", lazy="selectin")
    assigned_lawyer = relationship("User", backref="assigned_cases", lazy="selectin")
    documents = relationship(
        "Document",
        back_populates="case",
        cascade="all, delete-orphan",  # deleting a case removes its documents
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Case {self.case_number} ({self.status.value})>"
