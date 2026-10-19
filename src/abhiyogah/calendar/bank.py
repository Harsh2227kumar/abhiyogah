"""Bank working-day calendar built on the MIT ``holidays`` package plus a bank overlay.

A day is a bank holiday in a state when any of these holds (research report, gap-analysis row 19):

- it is a Sunday;
- it is the 2nd or 4th Saturday of its month;
- the ``holidays`` package lists it as a public holiday for India in that subdivision;
- the state overlay (``data/calendars/<year>/<state>.yaml``) lists it as a Negotiable Instruments
  Act holiday.

Day counts exclude the starting day. That is how RBC-CB para 71 counts working days, as summarised
in the research report (Table B, row B5): on the home branch's schedule, excluding the receipt day.
"""

import warnings
from collections.abc import Mapping, Set
from datetime import date, timedelta
from functools import cache

from holidays.countries.india import India

from abhiyogah.calendar.errors import CalendarRangeError, UnknownStateError

__all__ = ["MAX_SEARCH_DAYS", "STATES", "HolidaysBankCalendar", "is_bank_weekend"]

STATES: frozenset[str] = frozenset(India.subdivisions)
"""Accepted state and union territory codes (the ``holidays`` package's India subdivisions)."""

MAX_SEARCH_DAYS = 3660
"""Upper bound on days scanned in one call, so corrupt data cannot cause an endless loop."""

_SUNDAY = 6
_SATURDAY = 5


def is_bank_weekend(d: date) -> bool:
    """Return True for a Sunday or a 2nd/4th Saturday, the weekly bank closures (report row 19)."""
    if d.weekday() == _SUNDAY:
        return True
    if d.weekday() == _SATURDAY:
        nth = (d.day - 1) // 7 + 1
        return nth in (2, 4)
    return False


@cache
def _package_holidays(state: str, year: int) -> frozenset[date]:
    """Public holidays the ``holidays`` package lists for ``state`` in ``year``.

    The package warns when it lacks lunar-calendar data for a year; that would silently drop
    holidays, so it becomes a ``CalendarRangeError`` instead.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        days = India(subdiv=state, years=year)
    if caught:
        raise CalendarRangeError(f"holiday data incomplete for {year}: {caught[0].message}")
    return frozenset(days.keys())


class HolidaysBankCalendar:
    """``BankCalendar`` on the ``holidays`` package plus a per-state, per-year overlay."""

    def __init__(self, overlay: Mapping[tuple[str, int], Set[date]], version: str) -> None:
        """Build a calendar from overlay holidays keyed by ``(state, year)`` and a version stamp."""
        for state, _year in overlay:
            _check_state(state)
        self._overlay = {key: frozenset(days) for key, days in overlay.items()}
        self._version = version

    @property
    def version(self) -> str:
        """Identifier of the overlay data and ``holidays`` package version this calendar uses."""
        return self._version

    def is_working_day(self, d: date, state: str) -> bool:
        """Return True if banks in ``state`` are open on ``d`` (see the module docstring)."""
        _check_state(state)
        if is_bank_weekend(d):
            return False
        if d in _package_holidays(state, d.year):
            return False
        return d not in self._overlay.get((state, d.year), frozenset())

    def add_working_days(self, d: date, n: int, state: str) -> date:
        """Return the ``n``-th working day after ``d``; ``d`` itself is never counted (para 71).

        ``n == 0`` returns ``d`` unchanged. ``n`` must not be negative.
        """
        if n < 0:
            raise ValueError(f"n must be >= 0, got {n}")
        current = d
        remaining = n
        for _ in range(MAX_SEARCH_DAYS):
            if remaining == 0:
                return current
            current += timedelta(days=1)
            if self.is_working_day(current, state):
                remaining -= 1
        raise CalendarRangeError(f"no {n} working days found within {MAX_SEARCH_DAYS} days of {d}")

    def working_days_between(self, start_exclusive: date, end_inclusive: date, state: str) -> int:
        """Count working days in ``(start_exclusive, end_inclusive]``; the start day is excluded.

        This is the para 71 count: the day of receipt is excluded and the day of reporting counts.
        """
        if end_inclusive < start_exclusive:
            raise ValueError(f"end {end_inclusive} is before start {start_exclusive}")
        span = (end_inclusive - start_exclusive).days
        if span > MAX_SEARCH_DAYS:
            raise CalendarRangeError(f"range of {span} days exceeds {MAX_SEARCH_DAYS}")
        return sum(
            1
            for offset in range(1, span + 1)
            if self.is_working_day(start_exclusive + timedelta(days=offset), state)
        )

    def add_calendar_days(self, d: date, n: int) -> date:
        """Return ``d`` plus ``n`` calendar days, the CALENDAR day basis (no holiday adjustment)."""
        return d + timedelta(days=n)


def _check_state(state: str) -> None:
    """Raise ``UnknownStateError`` unless ``state`` is a known India subdivision code."""
    if state not in STATES:
        raise UnknownStateError(f"unknown state code {state!r}")
