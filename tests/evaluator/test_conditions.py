"""Condition grammar."""

from datetime import date, timedelta

import pytest
from pydantic import JsonValue

from abhiyogah.domain.complaint import ComplaintFacts, fold_events
from abhiyogah.domain.events import EventType
from abhiyogah.evaluator import ConditionSyntaxError
from abhiyogah.evaluator.conditions import evaluate_condition
from tests.domain.factories import event, utc


def facts(payload: dict[str, JsonValue]) -> ComplaintFacts:
    """Facts from one FACTS_RECORDED event."""
    return fold_events("CMP-TEST-1", [event(1, EventType.FACTS_RECORDED, utc(2026, 8, 3), payload)])


F = facts({"outcome": "WHOLLY_REJECTED", "external_tat_days": 25, "channel": "UPI_P2P"})


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (None, True),
        ("outcome in [PARTIALLY_RESOLVED, WHOLLY_REJECTED]", True),
        ("outcome in ['FULLY_RESOLVED']", False),
        ("outcome not in [FULLY_RESOLVED]", True),
        ("channel == UPI_P2P", True),
        ("channel != UPI_P2P", False),
        ("external_tat_days >= 25", True),
        ("external_tat_days > 25", False),
        ("external_tat_days < 30 and channel == UPI_P2P", True),
        ("external_tat_days is known", True),
        ("amount_paise is unknown", True),
        ("amount_paise is known", False),
        ("amount_paise > 5", None),
        ("amount_paise > 5 and channel == ATM", False),
    ],
)
def test_conditions(condition: str | None, expected: bool | None) -> None:
    """Each supported clause form evaluates as documented; unknown facts are undecided."""
    assert evaluate_condition(condition, F).result is expected


def test_missing_fact_is_reported() -> None:
    """Undecided conditions name the fact that is missing."""
    out = evaluate_condition("amount_paise > 5", F)
    assert out.missing == ("amount_paise",)


def test_dates_compare_by_iso_spelling() -> None:
    """Date facts compare by their ISO spelling."""
    f = fold_events(
        "CMP-TEST-1",
        [event(1, EventType.BANK_RECEIVED, utc(2026, 8, 3) - timedelta(hours=1))],
    )
    assert f.bank_receipt_date is not None
    assert f.bank_receipt_date.value == date(2026, 8, 3)
    assert evaluate_condition("bank_receipt_date == 2026-08-03", f).result is True


@pytest.mark.parametrize(
    "condition",
    [
        "outcome ~ X",
        "no_such_field is known",
        "channel > 3",
        "external_tat_days > abc",
        "import os",
    ],
)
def test_bad_syntax_raises(condition: str) -> None:
    """Anything outside the grammar is a rule-pack error."""
    with pytest.raises(ConditionSyntaxError):
        evaluate_condition(condition, F)
