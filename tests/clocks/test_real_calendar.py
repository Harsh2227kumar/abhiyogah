"""The clock engine runs on the real bank calendar from stream 01."""

from datetime import date

from abhiyogah.calendar import load_bank_calendar
from abhiyogah.clocks import BankCalendar, Clock, ClockState
from abhiyogah.domain.enums import BasisStatus, DayBasis
from tests.clocks.fakes import FakeCalendar


def test_real_and_fake_calendars_satisfy_the_protocol() -> None:
    """Both the bank calendar and the test double are BankCalendars."""
    assert isinstance(load_bank_calendar(), BankCalendar)
    assert isinstance(FakeCalendar(), BankCalendar)


def test_working_day_clock_on_bank_calendar() -> None:
    """A working-day clock's due date is a bank working day exactly n working days after start."""
    cal = load_bank_calendar()
    start = date(2026, 8, 7)
    clock = Clock(
        start_date=start,
        duration_days=10,
        basis=DayBasis.WORKING,
        basis_status=BasisStatus.EXPLICIT,
        calendar=cal,
        home_state="MH",
    )
    due = clock.due_date()
    assert cal.is_working_day(due, "MH")
    assert cal.working_days_between(start, due, "MH") == 10
    assert clock.state(due) is ClockState.RUNNING
    assert clock.days_remaining(due) == 0
