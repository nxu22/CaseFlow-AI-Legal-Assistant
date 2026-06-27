"""
Cross-tenant attack test setup script.

Creates:
  - Firm B: Jones Law
  - Bob (bob@jones.law) belonging to Firm B
  - 2 clients and 2 cases for Firm B
  - 1 dummy document on a Firm A case (attack target for document tests)

Prints all UUIDs needed for the attack test.
Run once before running the attack tests.
"""
import sys, os, uuid
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models.firm import Firm
from models.user import User, UserRole
from models.client import Client
from models.case import Case, CaseStatus
from models.document import Document, DocumentType
from security import hash_password
from seed import DEMO_FIRM_ID

JONES_LAW_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb")

def setup():
    db = SessionLocal()
    try:
        # ── Idempotency check ─────────────────────────────────────
        if db.query(Firm).filter(Firm.id == JONES_LAW_ID).first():
            print("[SKIP] Jones Law already exists.")
        else:
            # ── Firm B ────────────────────────────────────────────
            firm_b = Firm(
                id=JONES_LAW_ID,
                name="Jones Law",
                slug="jones-law",
                is_active=True,
                api_key="jones-law-api-key-2026",
            )
            db.add(firm_b)
            db.flush()
            print(f"[OK] Created firm: Jones Law ({JONES_LAW_ID})")

            # ── Bob (Firm B user) ─────────────────────────────────
            bob = User(
                email="bob@jones.law",
                hashed_password=hash_password("Jones1234!"),
                full_name="Bob Jones",
                role=UserRole.LAWYER,
                is_active=True,
                firm_id=JONES_LAW_ID,
            )
            db.add(bob)
            db.flush()
            print(f"[OK] Created user: bob@jones.law (firm_id={JONES_LAW_ID})")

            # ── Firm B clients ────────────────────────────────────
            client_b1 = Client(
                full_name="Jones Client One",
                email="one@jones.law",
                firm_id=JONES_LAW_ID,
            )
            client_b2 = Client(
                full_name="Jones Client Two",
                email="two@jones.law",
                firm_id=JONES_LAW_ID,
            )
            db.add_all([client_b1, client_b2])
            db.flush()
            print(f"[OK] Created 2 clients for Jones Law")

            # ── Firm B cases ──────────────────────────────────────
            case_b1 = Case(
                case_number="JNS-2026-0001",
                client_id=client_b1.id,
                assigned_lawyer_id=bob.id,
                status=CaseStatus.OPEN,
                violation_type="s.95(1) Speeding",
                fine_amount=Decimal("203.00"),
                violation_date=date(2026, 1, 10),
                firm_id=JONES_LAW_ID,
            )
            case_b2 = Case(
                case_number="JNS-2026-0002",
                client_id=client_b2.id,
                assigned_lawyer_id=bob.id,
                status=CaseStatus.IN_PROGRESS,
                violation_type="s.188(1) Careless driving",
                fine_amount=Decimal("672.00"),
                violation_date=date(2026, 2, 5),
                firm_id=JONES_LAW_ID,
            )
            db.add_all([case_b1, case_b2])
            db.flush()
            print(f"[OK] Created 2 cases for Jones Law")
            db.commit()

        # ── Add a dummy document to a Firm A case (attack target) ─
        firm_a_case = db.query(Case).filter(Case.firm_id == DEMO_FIRM_ID).first()
        existing_doc = db.query(Document).filter(
            Document.case_id == firm_a_case.id
        ).first()

        if existing_doc:
            doc_id = existing_doc.id
            print(f"[SKIP] Firm A document already exists: {doc_id}")
        else:
            firm_a_user = db.query(User).filter(User.firm_id == DEMO_FIRM_ID).first()
            dummy_doc = Document(
                case_id=firm_a_case.id,
                filename="ticket.txt",
                s3_key=f"cases/{firm_a_case.id}/test-ticket.txt",
                file_size=1024,
                mime_type="text/plain",
                document_type=DocumentType.TICKET,
                uploaded_by_id=firm_a_user.id,
            )
            db.add(dummy_doc)
            db.commit()
            db.refresh(dummy_doc)
            doc_id = dummy_doc.id
            print(f"[OK] Created dummy document on Firm A case")

        # ── Print attack targets ───────────────────────────────────
        firm_a_case   = db.query(Case).filter(Case.firm_id == DEMO_FIRM_ID).first()
        firm_a_client = db.query(Client).filter(Client.firm_id == DEMO_FIRM_ID).first()
        firm_a_doc    = db.query(Document).filter(
            Document.case_id == firm_a_case.id
        ).first()
        firm_a_lawyer = db.query(User).filter(User.firm_id == DEMO_FIRM_ID).first()

        print("\n" + "="*55)
        print("ATTACK TARGETS (Firm A UUIDs Bob should NOT reach):")
        print("="*55)
        print(f"FIRM_A_CASE_ID    = {firm_a_case.id}")
        print(f"FIRM_A_CLIENT_ID  = {firm_a_client.id}")
        print(f"FIRM_A_DOC_ID     = {firm_a_doc.id}")
        print(f"FIRM_A_LAWYER_ID  = {firm_a_lawyer.id}")
        print(f"FIRM_A_CASE_NUM   = {firm_a_case.case_number}")
        print("="*55)

    finally:
        db.close()


if __name__ == "__main__":
    setup()
