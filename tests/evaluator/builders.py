"""Test obligations shaped like the README example (A13, IO Directions 2026 cl. 14(1)).

Values are the report's (Table A row A13: 20 days; 10 days for IO review within an external TAT).
These are test fixtures, not rule-pack files; the rule pack lives in rules/obligations/.
"""

from typing import Any

from abhiyogah.registry.schema import Obligation

SOURCE = "https://example.org/io-directions-2026.pdf"


def obligation(**overrides: Any) -> Obligation:
    """The A13 ordinary limb (20 days), with any fields replaced."""
    base: dict[str, Any] = {
        "obligation_id": "IO-CB-2026-14-1-b",
        "deontic": "OBLIGATION",
        "subject": "bank",
        "instrument": "RBI (Commercial Banks – Internal Ombudsman) Directions, 2026",
        "clause": "14(1)(b)",
        "source_url": SOURCE,
        "applies_to": {
            "entity_type": "COMMERCIAL_BANK",
            "min_outlets": 10,
            "outlets_as_on": "2025-03-31",
        },
        "trigger": {
            "event": "OUTCOME_SET",
            "condition": "outcome in [PARTIALLY_RESOLVED, WHOLLY_REJECTED]",
        },
        "clock": {
            "start": "BANK_RECEIVED",
            "stop": "IO_REFERRED",
            "basis": "CALENDAR",
            "basis_status": "INFERRED",
        },
        "parameters": {
            "max_days": {
                "2026-01-14": {
                    "value": 20,
                    "reference": "cl. 14(1)(b)",
                    "verification": "PRIMARY_TEXT_READ",
                    "open_question": "Q4",
                }
            }
        },
        "overridden_by": [],
        "valid_from": "2026-01-14",
        "status": "DRAFT",
        "verification": "PRIMARY_TEXT_READ",
    }
    base.update(overrides)
    return Obligation.model_validate(base)


def tat_limb() -> Obligation:
    """The A13 external-TAT limb: due = external TAT - 10 days."""
    return obligation(
        obligation_id="IO-CB-2026-14-1-a",
        clause="14(1)(a)",
        parameters={
            "io_review_days": {
                "2026-01-14": {
                    "value": 10,
                    "reference": "cl. 14(1)(a)",
                    "verification": "PRIMARY_TEXT_READ",
                    "open_question": "Q4",
                }
            }
        },
    )


def ordinary_limb() -> Obligation:
    """The A13 ordinary limb, overridden by the TAT limb."""
    return obligation(overridden_by=["IO-CB-2026-14-1-a"])
