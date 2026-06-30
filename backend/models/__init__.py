"""
Models package.

Importing all models here serves two purposes:
1. Convenience: `from models import User, Case` works anywhere.
2. Alembic autogenerate sees all tables. Models not imported here
   will be invisible to migrations.
"""
from models.firm import Firm
from models.case import Case, CaseStatus
from models.client import Client
from models.document import Document, DocumentType
from models.intake_session import IntakeSession
from models.user import User, UserRole

__all__ = [
    "Firm",
    "User",
    "UserRole",
    "Client",
    "Case",
    "CaseStatus",
    "Document",
    "DocumentType",
    "IntakeSession",
]
