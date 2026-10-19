"""Tests for delay_working_days: receipt day excluded, IST dates, home-branch state (para 71)."""

from datetime import UTC, date, datetime

import pytest

from abhiyogah.calendar import HolidaysBankCalendar, delay_working_days
from abhiyogah.domain.errors import NaiveDatetimeError

CAL = HolidaysBankCalendar({}, version="test")


def test_same_day_report_is_zero() -> None:
    assert delay_working_days(date(2026, 6, 9), date(2026, 6, 9), "MH", calendar=CAL) == 0


def test_next_working_day_is_one() -> None:
    assert delay_working_days(date(2026, 6, 9), date(2026, 6, 10), "MH", calendar=CAL) == 1


def test_receipt_on_friday_before_second_saturday() -> None:
    # Fri 12 Jun 2026 receipt; Sat 13 (2nd Saturday) and Sun 14 closed; report Mon 15 is day 1.
    assert delay_working_days(date(2026, 6, 12), date(2026, 6, 15), "MH", calendar=CAL) == 1


def test_datetimes_use_ist_dates() -> None:
    # 19:00 UTC on 8 Jun is 00:30 IST on 9 Jun; 18:00 UTC on 9 Jun is 23:30 IST on 9 Jun.
    received = datetime(2026, 6, 8, 19, 0, tzinfo=UTC)
    reported = datetime(2026, 6, 9, 18, 0, tzinfo=UTC)
    assert delay_working_days(received, reported, "MH", calendar=CAL) == 0


def test_naive_datetime_rejected() -> None:
    with pytest.raises(NaiveDatetimeError):
        delay_working_days(datetime(2026, 6, 9), date(2026, 6, 10), "MH", calendar=CAL)  # noqa: DTZ001


def test_report_before_receipt_rejected() -> None:
    with pytest.raises(ValueError, match="before start"):
        delay_working_days(date(2026, 6, 10), date(2026, 6, 9), "MH", calendar=CAL)
