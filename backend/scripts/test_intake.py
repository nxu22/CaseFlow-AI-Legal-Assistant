"""
Standalone test for the intake agent — two-phase human-in-the-loop flow.
Run from backend/ directory:
    venv/Scripts/python.exe scripts/test_intake.py

Phase 1: run_intake() fires all four nodes then pauses (interrupt_after draft_intake).
Phase 2: resume_intake() resumes from the checkpoint, simulating an approval.

No DB session is passed. Requires ANTHROPIC_API_KEY in backend/.env.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_DOCUMENT = """
PROVINCIAL OFFENCES ACT
CERTIFICATE OF OFFENCE

Province of Manitoba
Winnipeg Police Service

OFFENCE NOTICE #: WPS-2025-847291
DATE ISSUED: September 15, 2025

ACCUSED INFORMATION
Name:        James Kowalski
Address:     142 Portage Ave, Winnipeg, MB  R3C 0A1
DOB:         1988-04-22
DL#:         KOW123456

OFFENCE DETAILS
Date of Offence:    September 15, 2025
Time:               14:32
Location:           Pembina Hwy & Jubilee Ave, Winnipeg, MB
Offence:            Speeding
HTA Section:        s.95(1) Highway Traffic Act
Speed Recorded:     87 km/h in a 60 km/h zone
Method:             Laser/Radar (certified unit #LR-4421)

SET FINE:           $203.00
Victim Surcharge:   $30.45
TOTAL OWING:        $233.45

Issuing Officer:    Const. R. Leblanc  Badge #4872

COURT INFORMATION
Court Date:         November 8, 2025  9:00 AM
Location:           Winnipeg Provincial Court
                    373 Broadway, Winnipeg, MB R3C 4W3
Courtroom:          4B
"""

if __name__ == "__main__":
    from services.intake_agent import resume_intake, run_intake

    # ------------------------------------------------------------------
    # PHASE 1: Run the pipeline — pauses after draft_intake
    # ------------------------------------------------------------------
    print("=" * 60)
    print("PHASE 1 — Running intake agent...")
    print("=" * 60)

    result = run_intake(SAMPLE_DOCUMENT, db_session=None)

    print("\n--- EXTRACTED FACTS -------------------------------------------")
    import json
    print(json.dumps(result["extracted"], indent=2))

    print("\n--- HTA MATCH -------------------------------------------------")
    print(json.dumps(result["hta_match"], indent=2))

    print("\n--- DRAFT INTAKE MEMO -----------------------------------------")
    print(result["draft"])

    print("\n--- CHECKPOINT ------------------------------------------------")
    print(f"thread_id : {result['thread_id']}")
    print(f"STATUS    : {result['status']}")
    print("\nGraph is PAUSED. Waiting for human decision...")

    # ------------------------------------------------------------------
    # PHASE 2: Simulate lawyer approval — resume from checkpoint
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 2 — Simulating approval, resuming from checkpoint...")
    print("=" * 60)

    final = resume_intake(result["thread_id"], decision="approve", db_session=None)

    print(f"\nthread_id : {final['thread_id']}")
    print(f"decision  : {final['decision']}")
    print(f"STATUS    : {final['status']}")
    print("\n[In production: extracted facts would now be written to the DB]")
    print("=" * 60)
