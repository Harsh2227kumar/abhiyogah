"""The calendar interface the clock engine needs.

This is a structural ``Protocol``: the bank calendar from ``abhiyogah.calendar`` (stream 01)
satisfies it without importing anything from here, and tests can pass a small double. The method set
follows the calendar task (``tasks/01-calendar.md``). Working-day arithmetic excludes the start day,
as RBC-CB para 71 requires for the day a communication was received.
"""

from datetime import date
from typing import Protocol

__all__ = ["BankCalendar"]


class BankCalendar(Protocol):
    """Bank working-day calendar for one home-branch state at a time."""

    @property
    def version(self) -> str:
        """Identifier of the calendar data, written into every decision record."""
        ...

    def is_working_day(self, d: date, state: str) -> bool:
        """True if ``d`` is a bank working day in ``state``."""
        ...

    def add_working_days(self, d: date, n: int, state: str) -> date:
        """The ``n``-th working day after ``d`` in ``state`` (``d`` itself is not counted)."""
        ...

    def working_days_between(self, start_exclusive: date, end_inclusive: date, state: str) -> int:
        """Working days in ``(start_exclusive, end_inclusive]`` in ``state``."""
        ...

    def add_calendar_days(self, d: date, n: int) -> date:
        """``d`` plus ``n`` calendar days."""
        ...
