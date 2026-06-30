"""
Client model: drivers/defendants represented by the law firm.

Clients do NOT log in. They are records managed by law firm staff.
A client may have multiple cases over time (multiple traffic tickets).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    firm_id = Column(
        UUID(as_uuid=True),
        ForeignKey("firms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    full_name = Column(String(255), nullable=False)

    # Email and phone may be missing (client only gave one contact method),
    # so they're nullable. Not unique: same person could be re-added
    # by mistake; we handle dedup at application layer.
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

    # Manitoba driver's license format: 9 chars (e.g., "ABC123456").
    # Indexed because lawyers often look up clients by license number.
    drivers_license = Column(String(50), nullable=True, index=True)

    # Free-form mailing address. Could be normalized into separate columns
    # (street/city/postal_code) later; for MVP, text is sufficient.
    address = Column(Text, nullable=True)

    # Staff notes about the client: communication preferences, history, etc.
    notes = Column(Text, nullable=True)

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

    def __repr__(self) -> str:
        return f"<Client {self.full_name}>"
