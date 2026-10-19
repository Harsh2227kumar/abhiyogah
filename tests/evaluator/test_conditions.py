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
        ("amount_paise > 5", False),
        ("external_tat_days is set", True),
        ("external_tat_days is not set", False),
        ("amount_paise is not set", True),
        ("outcome in [WHOLLY_REJECTED] and amount_paise is set", False),
        ("amount_paise > 5 and channel == ATM", False),
    ],
)
def test_conditions(condition: str | None, expected: bool) -> None:
    """Each supported clause form evaluates as documented; an unknown fact makes a clause false."""
    assert evaluate_condition(condition, F).result is expected


def test_missing_fact_is_reported() -> None:
    """A clause false for an unknown fact names it, in the result and the trace."""
    out = evaluate_condition("amount_paise > 5", F)
    assert out.missing == ("amount_paise",)
    assert out.trace[0].detail == "amount_paise is unknown"


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


G = facts({"outcome": "WHOLLY_REJECTED", "exclusion_category": "14_5_a"})


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (
            "outcome is set and (exclusion_category is not set or exclusion_category not in "
            "[14_5_c, 14_5_d, 14_5_e])",
            True,
        ),
        ("exclusion_category is not set or exclusion_category in [14_5_c]", False),
        ("outcome in [FULLY_RESOLVED] or channel is not set", True),
        ("outcome in [FULLY_RESOLVED] or channel is set and outcome is set", False),
        ("(outcome in [FULLY_RESOLVED] or channel is not set) and outcome is set", True),
        ("((outcome is set))", True),
    ],
)
def test_or_and_parentheses(condition: str, expected: bool) -> None:
    """`or` and grouping, with `and` binding tighter than `or`."""
    assert evaluate_condition(condition, G).result is expected


def test_a14_exemption_on_unknown_category() -> None:
    """An unknown exclusion category does not exempt the complaint, and the trace shows it."""
    f = facts({"outcome": "WHOLLY_REJECTED"})
    out = evaluate_condition(
        "exclusion_category is not set or exclusion_category not in [14_5_c, 14_5_d, 14_5_e]", f
    )
    assert out.result is True
    assert [t.result for t in out.trace] == [True, False]
    assert out.missing == ("exclusion_category",)
    excluded = facts({"exclusion_category": "14_5_d"})
    assert (
        evaluate_condition(
            "exclusion_category is not set or exclusion_category not in [14_5_c, 14_5_d, 14_5_e]",
            excluded,
        ).result
        is False
    )


@pytest.mark.parametrize(
    "condition",
    ["outcome is set and", "(outcome is set", "outcome is set)", "or outcome is set", "()", "a [b"],
)
def test_bad_grouping_raises(condition: str) -> None:
    """Unbalanced or dangling operators are rule-pack errors."""
    with pytest.raises(ConditionSyntaxError):
        evaluate_condition(condition, G)
