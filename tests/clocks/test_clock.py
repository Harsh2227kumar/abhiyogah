"""Clock engine: due dates, states, days remaining, pauses and building from facts."""

from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from abhiyogah.clocks import (
    BankCalendar,
    Clock,
    ClockError,
    ClockSpecError,
    ClockState,
    MissingFactError,
    Pause,
    build_clock,
    clock_date,
    pauses_from_events,
)
from abhiyogah.domain.complaint import fold_events
from abhiyogah.domain.enums import BasisStatus, DayBasis
from abhiyogah.domain.events import EventType
from abhiyogah.registry.schema import ClockPause, ClockSpec
from tests.clocks.fakes import FakeCalendar
from tests.domain.factories import event, utc

CAL = FakeCalendar(holidays=[date(2026, 8, 15)])


def cal_clock(start: date, n: int, stop: date | None = None, **kw: object) -> Clock:
    """A calendar-day clock on the fake calendar."""
    return Clock(
        start_date=start,
        duration_days=n,
        basis=DayBasis.CALENDAR,
        basis_status=BasisStatus.INFERRED,
        calendar=CAL,
        stop_date=stop,
        **kw,  # type: ignore[arg-type]
    )


def wd_clock(start: date, n: int, stop: date | None = None) -> Clock:
    """A working-day clock on the fake calendar, home state MH."""
    return Clock(
        start_date=start,
        duration_days=n,
        basis=DayBasis.WORKING,
        basis_status=BasisStatus.EXPLICIT,
        calendar=CAL,
        home_state="MH",
        stop_date=stop,
    )


def test_fake_calendar_satisfies_protocol() -> None:
    """The test double is a structural BankCalendar."""
    cal: BankCalendar = CAL
    assert cal.version == "fake-calendar-1"


def test_calendar_due_date_excludes_start_day() -> None:
    """3 Aug + 20 calendar days = 23 Aug (report A13 example)."""
    assert cal_clock(date(2026, 8, 3), 20).due_date() == date(2026, 8, 23)


def test_calendar_due_date_not_rolled_off_holiday() -> None:
    """A due date on a holiday stays put (rounding rule 3)."""
    assert cal_clock(date(2026, 8, 5), 10).due_date() == date(2026, 8, 15)


def test_working_due_date_skips_sundays_and_holidays() -> None:
    """Fri 14 Aug + 2 WD: Sat 15 holiday, Sun 16 closed -> Mon 17, Tue 18."""
    assert wd_clock(date(2026, 8, 14), 2).due_date() == date(2026, 8, 18)


def test_states_over_time() -> None:
    """RUNNING through the due date, BREACHED the day after."""
    clock = cal_clock(date(2026, 8, 3), 20)
    assert clock.state(date(2026, 8, 8)) is ClockState.RUNNING
    assert clock.state(date(2026, 8, 23)) is ClockState.RUNNING
    assert clock.state(date(2026, 8, 24)) is ClockState.BREACHED
    assert clock.days_late(date(2026, 8, 25)) == 2


def test_stop_on_due_date_is_on_time_and_late_after() -> None:
    """Stopping on the due date is on time; a day later is late by one."""
    assert (
        cal_clock(date(2026, 8, 3), 20, stop=date(2026, 8, 23)).state(date(2026, 9, 1))
        is ClockState.STOPPED_ON_TIME
    )
    late = cal_clock(date(2026, 8, 3), 20, stop=date(2026, 8, 24))
    assert late.state(date(2026, 9, 1)) is ClockState.STOPPED_LATE
    assert late.days_late(date(2026, 9, 1)) == 1


def test_future_stop_is_ignored_at_earlier_as_of() -> None:
    """A stop after as_of is not yet known: replay sees the clock still running or breached."""
    clock = cal_clock(date(2026, 8, 3), 20, stop=date(2026, 8, 26))
    assert clock.state(date(2026, 8, 10)) is ClockState.RUNNING
    assert clock.state(date(2026, 8, 25)) is ClockState.BREACHED
    assert clock.state(date(2026, 8, 26)) is ClockState.STOPPED_LATE


def test_ist_rounding_of_instants() -> None:
    """20:00 UTC on 22 Aug is 23 Aug in IST, still on the due date."""
    clock = cal_clock(date(2026, 8, 3), 20)
    late_evening = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    assert clock_date(late_evening) == date(2026, 8, 23)
    assert clock.state(late_evening) is ClockState.RUNNING
    assert clock.state(datetime(2026, 8, 23, 19, 0, tzinfo=UTC)) is ClockState.BREACHED


def test_days_remaining_working_basis() -> None:
    """Working days left exclude Sundays and holidays; negative when overdue."""
    clock = wd_clock(date(2026, 8, 10), 10)  # due Sat 22 Aug (15th holiday, 16th Sunday)
    assert clock.due_date() == date(2026, 8, 22)
    assert clock.days_remaining(date(2026, 8, 14)) == 6
    assert clock.days_remaining(date(2026, 8, 22)) == 0
    assert clock.days_remaining(date(2026, 8, 25)) == -2


def test_overdue_on_non_working_day_is_negative() -> None:
    """Due Sat 22 Aug; on Sun 23 Aug no working day has passed but the clock is overdue: -1."""
    clock = wd_clock(date(2026, 8, 10), 10)
    assert clock.state(date(2026, 8, 23)) is ClockState.BREACHED
    assert clock.days_remaining(date(2026, 8, 23)) == -1


def test_working_clock_needs_home_state() -> None:
    """No home-branch state means no working-day arithmetic, and nothing is assumed."""
    with pytest.raises(MissingFactError) as err:
        Clock(
            start_date=date(2026, 8, 3),
            duration_days=10,
            basis=DayBasis.WORKING,
            basis_status=BasisStatus.EXPLICIT,
            calendar=CAL,
        )
    assert err.value.fact == "home_branch_state"


def test_rejects_inconsistent_clocks() -> None:
    """Negative durations and stops before the start are errors."""
    with pytest.raises(ClockError):
        cal_clock(date(2026, 8, 3), -1)
    with pytest.raises(ClockError):
        cal_clock(date(2026, 8, 3), 5, stop=date(2026, 8, 2))
    with pytest.raises(ClockError):
        Pause(date(2026, 8, 5), date(2026, 8, 4))


def test_closed_pause_extends_due_date() -> None:
    """A pause from 5 to 9 Aug adds 4 days: due 27 Aug instead of 23 Aug."""
    clock = cal_clock(date(2026, 8, 3), 20, pauses=(Pause(date(2026, 8, 5), date(2026, 8, 9)),))
    assert clock.due_date() == date(2026, 8, 27)
    assert clock.state(date(2026, 8, 25)) is ClockState.RUNNING


def test_open_pause_needs_as_of_and_never_breaches() -> None:
    """While paused, the due date keeps moving with as_of."""
    clock = cal_clock(date(2026, 8, 3), 20, pauses=(Pause(date(2026, 8, 20)),))
    with pytest.raises(ClockError):
        clock.due_date()
    assert clock.state(date(2026, 9, 30)) is ClockState.RUNNING


def test_pause_after_due_date_is_ignored() -> None:
    """A clock that already ran out cannot be revived by a later pause."""
    clock = cal_clock(date(2026, 8, 3), 20, pauses=(Pause(date(2026, 8, 25), date(2026, 8, 30)),))
    assert clock.due_date() == date(2026, 8, 23)
    assert clock.state(date(2026, 8, 31)) is ClockState.BREACHED


SPEC = ClockSpec(
    start=EventType.BANK_RECEIVED,
    stop=[EventType.IO_REFERRED, EventType.FINAL_REPLY_SENT],
    basis=DayBasis.CALENDAR,
    basis_status=BasisStatus.INFERRED,
)


def test_build_clock_from_facts_uses_earliest_stop() -> None:
    """Start is the receipt date; the earliest known stop event stops the clock."""
    facts = fold_events(
        "CMP-TEST-1",
        [
            event(1, EventType.BANK_RECEIVED, utc(2026, 8, 3, 5)),
            event(2, EventType.FINAL_REPLY_SENT, utc(2026, 8, 20, 5)),
            event(3, EventType.IO_REFERRED, utc(2026, 8, 18, 5)),
        ],
    )
    clock = build_clock(SPEC, facts, 20, CAL)
    assert clock.start_date == date(2026, 8, 3)
    assert clock.stop_date == date(2026, 8, 18)
    assert clock.state(date(2026, 8, 30)) is ClockState.STOPPED_ON_TIME


def test_build_clock_missing_start_fact() -> None:
    """Without a start fact the clock is not built."""
    facts = fold_events("CMP-TEST-1", [event(1, EventType.ACKNOWLEDGED, utc(2026, 8, 3))])
    with pytest.raises(MissingFactError) as err:
        build_clock(SPEC, facts, 20, CAL)
    assert err.value.fact == "bank_receipt_date"


def test_build_clock_from_fact_start() -> None:
    """A clock can start from a fact (transaction date T) rather than an event."""
    spec = ClockSpec(
        start="transaction_date_t",
        stop=[EventType.REVERSAL_POSTED],
        basis=DayBasis.CALENDAR,
        basis_status=BasisStatus.EXPLICIT,
    )
    facts = fold_events(
        "CMP-TEST-1",
        [event(1, EventType.FACTS_RECORDED, utc(2026, 8, 3), {"transaction_date_t": "2026-08-01"})],
    )
    assert build_clock(spec, facts, 1, CAL).due_date() == date(2026, 8, 2)


def test_build_clock_refuses_pauses_without_rule() -> None:
    """Pauses only apply when the spec has a pause rule (none may, until Q3 is resolved)."""
    facts = fold_events("CMP-TEST-1", [event(1, EventType.BANK_RECEIVED, utc(2026, 8, 3))])
    with pytest.raises(ClockSpecError):
        build_clock(SPEC, facts, 20, CAL, pauses=[Pause(date(2026, 8, 5))])


def test_pauses_from_events_pairs_on_and_resume() -> None:
    """Pause/resume events pair up in business-time order; a trailing pause stays open."""
    rule = ClockPause(
        on=EventType.INFO_REQUESTED, resume=EventType.FACTS_RECORDED, open_question="Q3"
    )
    events = [
        event(1, EventType.INFO_REQUESTED, utc(2026, 8, 5, 5)),
        event(2, EventType.FACTS_RECORDED, utc(2026, 8, 9, 5)),
        event(3, EventType.INFO_REQUESTED, utc(2026, 8, 12, 5)),
    ]
    assert pauses_from_events(rule, events) == [
        Pause(date(2026, 8, 5), date(2026, 8, 9)),
        Pause(date(2026, 8, 12)),
    ]


starts = st.dates(min_value=date(2025, 1, 1), max_value=date(2028, 12, 31))
durations = st.integers(min_value=0, max_value=120)
offsets = st.integers(min_value=0, max_value=200)


@given(starts, durations)
def test_calendar_due_is_start_plus_n(start: date, n: int) -> None:
    """Calendar clocks without pauses are due exactly n days after the start."""
    assert cal_clock(start, n).due_date() == start + timedelta(days=n)


@given(starts, durations, offsets)
def test_state_without_stop_is_running_then_breached(start: date, n: int, k: int) -> None:
    """Without a stop the clock is RUNNING up to the due date and BREACHED after it."""
    for clock in (cal_clock(start, n), wd_clock(start, n)):
        day = start + timedelta(days=k)
        expected = ClockState.BREACHED if day > clock.due_date() else ClockState.RUNNING
        assert clock.state(day) is expected
        assert (clock.days_remaining(day) < 0) == (expected is ClockState.BREACHED)


@given(starts, durations, offsets)
def test_stop_state_matches_due_date(start: date, n: int, k: int) -> None:
    """A known stop is on time exactly when it is on or before the due date."""
    stop = start + timedelta(days=k)
    clock = wd_clock(start, n, stop=stop)
    on_time = stop <= clock.due_date()
    assert clock.state(stop) is (ClockState.STOPPED_ON_TIME if on_time else ClockState.STOPPED_LATE)
    assert (clock.days_late(stop) == 0) == on_time


@given(starts, durations)
def test_working_due_date_is_a_working_day(start: date, n: int) -> None:
    """n >= 1 working days always lands on a working day, n working days after the start."""
    clock = wd_clock(start, n)
    due = clock.due_date()
    if n >= 1:
        assert CAL.is_working_day(due, "MH")
    assert CAL.working_days_between(start, due, "MH") == n
