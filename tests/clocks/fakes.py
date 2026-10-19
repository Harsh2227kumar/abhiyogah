"""A small ``BankCalendar`` test double used until the real bank calendar (stream 01) is merged.

Sundays and an explicit set of synthetic holidays are closed, in every state. The holidays are test
data, not real bank holidays.
"""

from collections.abc import Iterable
from datetime import date, timedelta


class FakeCalendar:
    """Closed on Sundays and on ``holidays``; the same in every state."""

    def __init__(self, holidays: Iterable[date] = (), version: str = "fake-calendar-1") -> None:
        self._holidays = frozenset(holidays)
        self._version = version

    @property
    def version(self) -> str:
        """Identifier written into decision records."""
        return self._version

    def is_working_day(self, d: date, state: str) -> bool:
        """Not a Sunday and not a listed holiday."""
        return d.weekday() != 6 and d not in self._holidays

    def add_working_days(self, d: date, n: int, state: str) -> date:
        """The n-th working day after d (d excluded)."""
        if n < 0:
            raise ValueError("n must be >= 0")
        while n > 0:
            d += timedelta(days=1)
            if self.is_working_day(d, state):
                n -= 1
        return d

    def working_days_between(self, start_exclusive: date, end_inclusive: date, state: str) -> int:
        """Working days in (start_exclusive, end_inclusive]."""
        count = 0
        d = start_exclusive
        while d < end_inclusive:
            d += timedelta(days=1)
            if self.is_working_day(d, state):
                count += 1
        return count

    def add_calendar_days(self, d: date, n: int) -> date:
        """d plus n calendar days."""
        return d + timedelta(days=n)
