"""Time travel: one complaint evaluated at days 5, 19, 20 and 21 of the IO clock."""

from datetime import date, timedelta

import pytest

from abhiyogah.domain.decision import DecisionResult
from abhiyogah.domain.events import EventType
from abhiyogah.evaluator import evaluate
from tests.evaluator.builders import obligation
from tests.evaluator.test_evaluate import CAL, PROFILE, at, ev

RECEIPT = date(2026, 8, 3)
EVENTS = [
    ev(1, EventType.BANK_RECEIVED, RECEIPT),
    ev(2, EventType.OUTCOME_SET, RECEIPT + timedelta(days=2), {"outcome": "PARTIALLY_RESOLVED"}),
]


@pytest.mark.parametrize(
    ("day", "expected", "days_late"),
    [
        (5, DecisionResult.RUNNING, None),
        (19, DecisionResult.RUNNING, None),
        (20, DecisionResult.RUNNING, None),  # due date: receipt + 20 days (A13, cl. 14(1)(b))
        (21, DecisionResult.BREACHED, 1),
    ],
)
def test_io_clock_running_then_breached(
    day: int, expected: DecisionResult, days_late: int | None
) -> None:
    """The IO clock runs through day 20 and is breached on day 21."""
    as_of = at(RECEIPT + timedelta(days=day), 23)
    (rec,) = evaluate(EVENTS, [obligation()], CAL, as_of, profile=PROFILE)
    assert rec.result is expected
    assert rec.deadline is not None
    assert rec.deadline.due_date == RECEIPT + timedelta(days=20)
    assert (rec.breach.days_late if rec.breach else None) == days_late
    assert [a.action for a in rec.required_actions] == ["REFER_TO_IO"]


def test_midnight_boundary_is_ist() -> None:
    """23:59 IST on day 20 is still on time; 00:01 IST on day 21 is breached."""
    due = RECEIPT + timedelta(days=20)
    last = at(due, 23).replace(minute=59)
    first = at(due + timedelta(days=1), 0).replace(minute=1)
    (on_time,) = evaluate(EVENTS, [obligation()], CAL, last, profile=PROFILE)
    (late,) = evaluate(EVENTS, [obligation()], CAL, first, profile=PROFILE)
    assert on_time.result is DecisionResult.RUNNING
    assert late.result is DecisionResult.BREACHED
