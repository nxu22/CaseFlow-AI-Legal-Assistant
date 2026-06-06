"""
HTA (Highway Traffic Act) reference data for Manitoba traffic offences.

Real sections sourced from the Manitoba Highway Traffic Act and Brown Book
(Provincial Offences Act fine schedule). Used by the intake agent to enrich
extracted violation data with authoritative legal references.
"""
from __future__ import annotations

from typing import TypedDict


class HTAEntry(TypedDict):
    section: str
    description: str
    fine_category: str | None
    fine_amount: float | None
    notes: str | None


# Real Manitoba HTA sections — do not invent others.
_HTA_TABLE: list[HTAEntry] = [
    {
        "section": "s.95(1)",
        "description": "Speeding — driving in excess of posted speed limit",
        "fine_category": "D",
        "fine_amount": 203.00,
        "notes": "Fine varies by km/h over limit; $203 is the base D-schedule amount.",
    },
    {
        "section": "s.95(1)(b.1)",
        "description": "Speeding in a designated construction zone",
        "fine_category": "D×2",
        "fine_amount": 406.00,
        "notes": "Fine is double the standard speeding fine under s.95(1) when workers present.",
    },
    {
        "section": "s.95(2)",
        "description": "Driving at a speed not reasonable and prudent for conditions",
        "fine_category": "C",
        "fine_amount": 174.00,
        "notes": (
            "Distinct from posted-limit speeding — covers adverse weather, visibility, "
            "road conditions. No speed threshold required."
        ),
    },
    {
        "section": "s.88(7)",
        "description": "Fail to stop for a red light",
        "fine_category": "F",
        "fine_amount": 298.00,
        "notes": "Includes stopping line and intersection violations.",
    },
    {
        "section": "s.88(9)",
        "description": "Disobey traffic control signal / traffic light",
        "fine_category": "F",
        "fine_amount": 298.00,
        "notes": "Broader than s.88(7); covers amber-light racing and signal disobedience.",
    },
    {
        "section": "s.134(1)(b)",
        "description": "Fail to stop at a railway crossing — approaching train",
        "fine_category": "G",
        "fine_amount": 486.00,
        "notes": "Applies when a train is approaching, passing, or stopped at crossing.",
    },
    {
        "section": "s.134(1)(c)",
        "description": "Fail to stop at a railway crossing — signal active",
        "fine_category": "G",
        "fine_amount": 486.00,
        "notes": "Applies when a crossing signal (light/bell/barrier) is active.",
    },
    {
        "section": "s.188",
        "description": "Careless driving — driving without due care and attention",
        "fine_category": "H",
        "fine_amount": 672.00,
        "notes": (
            "Most commonly litigated HTA offence; no mens rea required. "
            "Can arise from any inattentive driving regardless of speed."
        ),
    },
]

# Keyword index: maps lowercase keywords to HTA entries for fast lookup.
_KEYWORD_INDEX: list[tuple[list[str], HTAEntry]] = [
    (["construction zone", "construction", "work zone", "b.1"], _HTA_TABLE[1]),
    (["speeding", "speed", "km/h", "over limit", "95(1)"], _HTA_TABLE[0]),
    (["reasonable", "prudent", "conditions", "95(2)"], _HTA_TABLE[2]),
    (["red light", "stop for", "traffic signal", "88(7)"], _HTA_TABLE[3]),
    (["traffic light", "signal", "disobey", "amber", "88(9)"], _HTA_TABLE[4]),
    (["railway", "train", "crossing", "134(1)(b)"], _HTA_TABLE[5]),
    (["railway signal", "crossing signal", "134(1)(c)"], _HTA_TABLE[6]),
    (["careless", "without due care", "inattention", "188"], _HTA_TABLE[7]),
]


def lookup_hta(violation_text: str) -> HTAEntry | None:
    """
    Return the best-matching HTA entry for a violation string.

    Strategy: score each entry by counting how many of its keywords appear
    in the lowercased violation text; return the highest-scoring entry.
    Returns None if no keywords match at all.
    """
    if not violation_text:
        return None

    lower = violation_text.lower()
    best_score = 0
    best_entry: HTAEntry | None = None

    for keywords, entry in _KEYWORD_INDEX:
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score = score
            best_entry = entry

    return best_entry if best_score > 0 else None
