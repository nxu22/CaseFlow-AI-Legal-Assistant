# backend/seed.py
import uuid
from datetime import date, timedelta
from decimal import Decimal
import random

from sqlalchemy import select

from database import SessionLocal
from models.firm import Firm
from models.user import User, UserRole
from models.client import Client
from models.case import Case, CaseStatus
from security import hash_password

# Stable UUIDs — shared with Alembic migrations so both code paths
# (fresh install vs. migrating an existing DB) land on the same firms.
DEMO_FIRM_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
JONES_LAW_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb")

# ── HTA offence types (Manitoba Brown Book 2026-01) ──────────────
HTA_OFFENCES = [
    {"violation_type": "s.95(1) Speeding",                                "fine": Decimal("203.00")},
    {"violation_type": "s.95(1)(b.1) Speeding in construction zone",      "fine": Decimal("406.00")},
    {"violation_type": "s.95(2) Speed not reasonable/prudent",            "fine": Decimal("174.00")},
    {"violation_type": "s.88(7) Fail to stop for red light",              "fine": Decimal("298.00")},
    {"violation_type": "s.134(1)(b) Fail to stop at railway crossing",    "fine": Decimal("486.00")},
    {"violation_type": "s.188(1) Careless driving",                       "fine": Decimal("672.00")},
]

# ── Demo Firm clients ─────────────────────────────────────────────
DEMO_CLIENTS = [
    {"full_name": "James Kowalski",  "email": "j.kowalski@email.com",  "phone": "204-555-0101", "drivers_license": "KOW123456"},
    {"full_name": "Maria Tremblay",  "email": "m.tremblay@email.com",  "phone": "204-555-0102", "drivers_license": "TRE234567"},
    {"full_name": "David Nguyen",    "email": "d.nguyen@email.com",    "phone": "204-555-0103", "drivers_license": "NGU345678"},
    {"full_name": "Sarah Oleksiak",  "email": "s.oleksiak@email.com",  "phone": "204-555-0104", "drivers_license": "OLE456789"},
    {"full_name": "Michael Friesen", "email": "m.friesen@email.com",   "phone": "204-555-0105", "drivers_license": "FRI567890"},
    {"full_name": "Linda Chartrand", "email": "l.chartrand@email.com", "phone": "204-555-0106", "drivers_license": "CHA678901"},
    {"full_name": "Kevin Reimer",    "email": "k.reimer@email.com",    "phone": "204-555-0107", "drivers_license": "REI789012"},
    {"full_name": "Anna Szymanski",  "email": "a.szymanski@email.com", "phone": "204-555-0108", "drivers_license": "SZY890123"},
]

# ── Jones Law clients ─────────────────────────────────────────────
JONES_CLIENTS = [
    {"full_name": "Ryan Tokarchuk",  "email": "r.tokarchuk@email.com",  "phone": "204-555-0201", "drivers_license": "TOK111222"},
    {"full_name": "Chloe Bergmann",  "email": "c.bergmann@email.com",   "phone": "204-555-0202", "drivers_license": "BER222333"},
    {"full_name": "Tyler Martens",   "email": "t.martens@email.com",    "phone": "204-555-0203", "drivers_license": "MAR333444"},
    {"full_name": "Priya Sethi",     "email": "p.sethi@email.com",      "phone": "204-555-0204", "drivers_license": "SET444555"},
    {"full_name": "Derek Klassen",   "email": "d.klassen@email.com",    "phone": "204-555-0205", "drivers_license": "KLA555666"},
]

STATUS_WEIGHTS = [
    CaseStatus.OPEN, CaseStatus.OPEN, CaseStatus.OPEN,
    CaseStatus.IN_PROGRESS, CaseStatus.IN_PROGRESS, CaseStatus.IN_PROGRESS,
    CaseStatus.CLOSED_WON, CaseStatus.CLOSED_WON,
    CaseStatus.CLOSED_LOST,
    CaseStatus.CLOSED_DISMISSED,
]


def seed():
    db = SessionLocal()
    try:

        # ══════════════════════════════════════════════════════════
        # Block 1: Demo Firm
        # Independent idempotency check — skipped if user already exists.
        # Re-running seed never touches existing Demo Firm data.
        # ══════════════════════════════════════════════════════════
        if db.execute(
            select(User).where(User.email == "lawyer@caseflow.mb")
        ).scalar_one_or_none():
            print("[SKIP] Demo Firm already exists, skipping.")
        else:
            firm_a = Firm(
                id=DEMO_FIRM_ID,
                name="CaseFlow Demo Firm",
                slug="demo-firm",
                is_active=True,
                api_key="demo-firm-api-key-2026",
            )
            db.add(firm_a)
            db.flush()
            print(f"[OK] Created firm: {firm_a.name}")

            lawyer_a = User(
                email="lawyer@caseflow.mb",
                hashed_password=hash_password("Demo1234!"),
                full_name="Alexandra Reid",
                role=UserRole.LAWYER,
                is_active=True,
                firm_id=DEMO_FIRM_ID,
            )
            db.add(lawyer_a)
            db.flush()
            print(f"[OK] Created lawyer: {lawyer_a.email}")

            client_objs_a = []
            for c in DEMO_CLIENTS:
                client = Client(
                    full_name=c["full_name"],
                    email=c["email"],
                    phone=c["phone"],
                    drivers_license=c["drivers_license"],
                    firm_id=DEMO_FIRM_ID,
                )
                db.add(client)
                client_objs_a.append(client)
            db.flush()
            print(f"[OK] Created {len(client_objs_a)} Demo Firm clients")

            base_date = date(2025, 1, 1)
            for i in range(20):
                offence = HTA_OFFENCES[i % len(HTA_OFFENCES)]
                client = client_objs_a[i % len(client_objs_a)]
                violation_date = base_date + timedelta(days=i * 12)
                court_date = violation_date + timedelta(days=random.randint(45, 90))
                db.add(Case(
                    case_number=f"CFM-2025-{i + 1:04d}",
                    client_id=client.id,
                    assigned_lawyer_id=lawyer_a.id,
                    status=random.choice(STATUS_WEIGHTS),
                    violation_type=offence["violation_type"],
                    violation_date=violation_date,
                    fine_amount=offence["fine"],
                    court_date=court_date,
                    firm_id=DEMO_FIRM_ID,
                    description=(
                        f"Client cited under {offence['violation_type']}. "
                        f"Fine: ${offence['fine']}. Defense intake complete."
                    ),
                ))
            db.commit()
            print("[DONE] Demo Firm seeded: 1 firm + 1 lawyer + 8 clients + 20 cases")

        # ══════════════════════════════════════════════════════════
        # Block 2: Jones Law
        # Completely independent check — runs regardless of Block 1 outcome.
        # Re-running seed never touches existing Jones Law data.
        # ══════════════════════════════════════════════════════════
        if db.execute(
            select(User).where(User.email == "bob@jones.law")
        ).scalar_one_or_none():
            print("[SKIP] Jones Law already exists, skipping.")
        else:
            firm_b = Firm(
                id=JONES_LAW_ID,
                name="Jones Law",
                slug="jones-law",
                is_active=True,
                api_key="jones-law-api-key-2026",
            )
            db.add(firm_b)
            db.flush()
            print(f"[OK] Created firm: {firm_b.name}")

            lawyer_b = User(
                email="bob@jones.law",
                hashed_password=hash_password("Jones1234!"),
                full_name="Bob Jones",
                role=UserRole.LAWYER,
                is_active=True,
                firm_id=JONES_LAW_ID,
            )
            db.add(lawyer_b)
            db.flush()
            print(f"[OK] Created lawyer: {lawyer_b.email}")

            client_objs_b = []
            for c in JONES_CLIENTS:
                client = Client(
                    full_name=c["full_name"],
                    email=c["email"],
                    phone=c["phone"],
                    drivers_license=c["drivers_license"],
                    firm_id=JONES_LAW_ID,
                )
                db.add(client)
                client_objs_b.append(client)
            db.flush()
            print(f"[OK] Created {len(client_objs_b)} Jones Law clients")

            base_date = date(2026, 1, 1)
            for i in range(10):
                offence = HTA_OFFENCES[i % len(HTA_OFFENCES)]
                client = client_objs_b[i % len(client_objs_b)]
                violation_date = base_date + timedelta(days=i * 15)
                court_date = violation_date + timedelta(days=random.randint(45, 90))
                db.add(Case(
                    case_number=f"JNS-2026-{i + 1:04d}",
                    client_id=client.id,
                    assigned_lawyer_id=lawyer_b.id,
                    status=random.choice(STATUS_WEIGHTS),
                    violation_type=offence["violation_type"],
                    violation_date=violation_date,
                    fine_amount=offence["fine"],
                    court_date=court_date,
                    firm_id=JONES_LAW_ID,
                    description=(
                        f"Client cited under {offence['violation_type']}. "
                        f"Fine: ${offence['fine']}. Defense intake pending."
                    ),
                ))
            db.commit()
            print("[DONE] Jones Law seeded: 1 firm + 1 lawyer + 5 clients + 10 cases")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
