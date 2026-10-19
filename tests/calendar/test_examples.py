"""Hand-checked working-day examples on the default calendar.

Each expected date was worked out by hand from a printed 2026 calendar, the weekly bank closures
(Sundays, 2nd/4th Saturdays) and the public holidays the ``holidays`` package lists for the state.
State overlays are unsourced, so these examples only rely on package holidays.
"""

from datetime import date

import pytest

from abhiyogah.calendar import delay_working_days, load_bank_calendar

CAL = load_bank_calendar()


def test_report_on_friday_before_second_saturday() -> None:
    # Receipt Fri 12 Jun 2026. Sat 13 Jun is the 2nd Saturday, Sun 14 closed.
    # Mon 15 = 1, Tue 16 = 2, Wed 17 = 3 working days.
    assert CAL.add_working_days(date(2026, 6, 12), 1, "MH") == date(2026, 6, 15)
    assert delay_working_days(date(2026, 6, 12), date(2026, 6, 17), "MH", calendar=CAL) == 3
    assert delay_working_days(date(2026, 6, 12), date(2026, 6, 14), "MH", calendar=CAL) == 0


def test_first_saturday_is_a_working_day() -> None:
    # Diwali week in Maharashtra: receipt Fri 6 Nov 2026. Sat 7 Nov (1st Saturday) = 1,
    # Sun 8 Nov (Diwali) closed, Mon 9 = 2, Tue 10 Nov (Bali Pratipada) closed, Wed 11 = 3.
    assert CAL.is_working_day(date(2026, 11, 7), "MH")
    assert not CAL.is_working_day(date(2026, 11, 10), "MH")
    assert CAL.add_working_days(date(2026, 11, 6), 3, "MH") == date(2026, 11, 11)


def test_fourth_saturday_and_republic_day() -> None:
    # Receipt Fri 23 Jan 2026. Sat 24 Jan is the 4th Saturday, Sun 25 closed,
    # Mon 26 Jan is Republic Day. The first working day is Tue 27 Jan.
    assert CAL.add_working_days(date(2026, 1, 23), 1, "DL") == date(2026, 1, 27)


def test_christmas_then_fourth_saturday() -> None:
    # Receipt Thu 24 Dec 2026. Fri 25 Christmas, Sat 26 the 4th Saturday, Sun 27 closed.
    assert CAL.add_working_days(date(2026, 12, 24), 1, "KA") == date(2026, 12, 28)


@pytest.mark.parametrize(("state", "open_"), [("MH", False), ("KA", True)])
def test_state_holiday_applies_only_in_its_state(state: str, open_: bool) -> None:
    # Thu 19 Feb 2026, Chhatrapati Shivaji Maharaj's Jayanti, is a Maharashtra holiday only.
    assert CAL.is_working_day(date(2026, 2, 19), state) is open_


def test_calendar_days_ignore_holidays() -> None:
    assert CAL.add_calendar_days(date(2026, 1, 31), 30) == date(2026, 3, 2)
    assert CAL.add_calendar_days(date(2026, 12, 24), 1) == date(2026, 12, 25)
