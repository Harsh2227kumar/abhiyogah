"""Unit tests for HolidaysBankCalendar: weekly closures, package holidays and the overlay.

Overlay dates here are synthetic test inputs, not real bank holidays.
"""

from datetime import date

import pytest

from abhiyogah.calendar import (
    BankCalendar,
    CalendarRangeError,
    HolidaysBankCalendar,
    UnknownStateError,
    is_bank_weekend,
)

SYNTHETIC_CLOSURE = date(2026, 6, 10)  # a Wednesday, used only as a test overlay entry


@pytest.fixture
def cal() -> HolidaysBankCalendar:
    return HolidaysBankCalendar({("MH", 2026): {SYNTHETIC_CLOSURE}}, version="test")


def test_satisfies_protocol(cal: HolidaysBankCalendar) -> None:
    assert isinstance(cal, BankCalendar)
    assert cal.version == "test"


@pytest.mark.parametrize(
    ("d", "closed"),
    [
        (date(2026, 6, 6), False),  # 1st Saturday
        (date(2026, 6, 13), True),  # 2nd Saturday
        (date(2026, 6, 20), False),  # 3rd Saturday
        (date(2026, 6, 27), True),  # 4th Saturday
        (date(2026, 5, 30), False),  # 5th Saturday
        (date(2026, 6, 7), True),  # Sunday
        (date(2026, 6, 8), False),  # Monday
    ],
)
def test_bank_weekend(d: date, closed: bool) -> None:
    assert is_bank_weekend(d) is closed


def test_package_public_holiday_is_closed(cal: HolidaysBankCalendar) -> None:
    # Republic Day, 26 Jan 2026 (a Monday), is a national holiday in the holidays package.
    assert not cal.is_working_day(date(2026, 1, 26), "MH")


def test_overlay_applies_only_to_its_state(cal: HolidaysBankCalendar) -> None:
    assert not cal.is_working_day(SYNTHETIC_CLOSURE, "MH")
    assert cal.is_working_day(SYNTHETIC_CLOSURE, "KA")


def test_unknown_state_rejected(cal: HolidaysBankCalendar) -> None:
    with pytest.raises(UnknownStateError):
        cal.is_working_day(date(2026, 6, 8), "XX")
    with pytest.raises(UnknownStateError):
        HolidaysBankCalendar({("XX", 2026): set()}, version="test")


def test_year_without_package_data_is_an_error(cal: HolidaysBankCalendar) -> None:
    with pytest.raises(CalendarRangeError):
        cal.is_working_day(date(2040, 6, 6), "MH")


def test_add_zero_working_days_is_identity(cal: HolidaysBankCalendar) -> None:
    assert cal.add_working_days(date(2026, 6, 7), 0, "MH") == date(2026, 6, 7)


def test_negative_working_days_rejected(cal: HolidaysBankCalendar) -> None:
    with pytest.raises(ValueError, match="n must be"):
        cal.add_working_days(date(2026, 6, 8), -1, "MH")


def test_add_working_days_skips_overlay_and_weekend(cal: HolidaysBankCalendar) -> None:
    # Tue 9 Jun -> Wed 10 closed (overlay), Thu 11, Fri 12, Sat 13 closed (2nd), Sun 14, Mon 15.
    assert cal.add_working_days(date(2026, 6, 9), 3, "MH") == date(2026, 6, 15)
    assert cal.working_days_between(date(2026, 6, 9), date(2026, 6, 15), "MH") == 3


def test_working_days_between_rejects_reversed_range(cal: HolidaysBankCalendar) -> None:
    assert cal.working_days_between(date(2026, 6, 9), date(2026, 6, 9), "MH") == 0
    with pytest.raises(ValueError, match="before start"):
        cal.working_days_between(date(2026, 6, 9), date(2026, 6, 8), "MH")


def test_add_calendar_days(cal: HolidaysBankCalendar) -> None:
    assert cal.add_calendar_days(date(2026, 6, 13), 30) == date(2026, 7, 13)
