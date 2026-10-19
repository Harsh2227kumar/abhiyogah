"""Breach forecasting over a horizon."""

from datetime import date

import pytest

from abhiyogah.domain.events import EventType
from abhiyogah.evaluator import EvaluationError, evaluate, forecast, forecast_records
from tests.evaluator.builders import obligation
from tests.evaluator.test_evaluate import CAL, PROFILE, RECEIVED, REJECTED, at, ev


def test_deadline_within_horizon_is_listed() -> None:
    """Due 23 Aug; on 18 Aug a 5-day horizon includes it, a 4-day horizon does not."""
    events = [RECEIVED, REJECTED]
    (item,) = forecast(events, [obligation()], CAL, at(date(2026, 8, 18)), 5, profile=PROFILE)
    assert item.due_date == date(2026, 8, 23)
    assert item.calendar_days_left == 5
    assert [a.action for a in item.required_actions] == ["REFER_TO_IO"]
    assert forecast(events, [obligation()], CAL, at(date(2026, 8, 18)), 4, profile=PROFILE) == []


def test_due_today_is_listed_with_zero_horizon() -> None:
    """A deadline due today is still running and in a zero-day horizon."""
    (item,) = forecast(
        [RECEIVED, REJECTED], [obligation()], CAL, at(date(2026, 8, 23)), 0, profile=PROFILE
    )
    assert item.calendar_days_left == 0


def test_breached_and_stopped_are_not_forecast() -> None:
    """Only running clocks are forecast."""
    late = forecast(
        [RECEIVED, REJECTED], [obligation()], CAL, at(date(2026, 8, 25)), 30, profile=PROFILE
    )
    assert late == []
    referred = ev(3, EventType.IO_REFERRED, date(2026, 8, 12))
    done = forecast(
        [RECEIVED, REJECTED, referred],
        [obligation()],
        CAL,
        at(date(2026, 8, 18)),
        30,
        profile=PROFILE,
    )
    assert done == []


def test_items_sorted_soonest_first_across_complaints() -> None:
    """Records from several complaints sort by due date."""
    as_of = at(date(2026, 8, 11))
    first = evaluate([RECEIVED, REJECTED], [obligation()], CAL, as_of, profile=PROFILE)
    later = obligation(
        parameters={
            "max_days": {
                "2026-01-14": {"value": 10, "reference": "x", "verification": "UNVERIFIED"}
            }
        }
    )
    second = evaluate([RECEIVED, REJECTED], [later], CAL, as_of, profile=PROFILE)
    items = forecast_records([*first, *second], as_of, 30)
    assert [i.due_date for i in items] == [date(2026, 8, 13), date(2026, 8, 23)]


def test_negative_horizon_rejected() -> None:
    """A negative horizon is an error."""
    with pytest.raises(EvaluationError):
        forecast_records([], at(date(2026, 8, 5)), -1)
