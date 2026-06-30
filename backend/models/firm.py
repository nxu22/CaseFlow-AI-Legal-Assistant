import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Firm(Base):
    __tablename__ = "firms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False)

    # URL-safe identifier for future subdomain routing (firm-a.caseflowmb.site).
    slug = Column(String(100), unique=True, nullable=False, index=True)

    # Opaque token used to authenticate the MCP server subprocess for this firm.
    # Each firm's MCP instance reads FIRM_API_KEY at startup and resolves its tenant.
    api_key = Column(String(64), unique=True, nullable=True, index=True)

    is_active = Column(Boolean, nullable=False, default=True)

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
        return f"<Firm {self.slug}>"
