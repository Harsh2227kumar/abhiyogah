"""The ``BankCalendar`` protocol: working-day questions and day arithmetic for regulatory clocks.

Every date here is an Asia/Kolkata calendar date (``datetime.date``). Callers convert aware
datetimes with :func:`abhiyogah.domain.tz.ist_date` first, so no answer depends on the time of day.
"""

from datetime import date
from typing import Protocol, runtime_checkable

__all__ = ["BankCalendar"]


@runtime_checkable
class BankCalendar(Protocol):
    """A versioned bank working-day calendar keyed by Indian state or union territory code."""

    @property
    def version(self) -> str:
        """Stable identifier of the exact calendar data, recorded in every decision record."""
        ...

    def is_working_day(self, d: date, state: str) -> bool:
        """Return True if banks in ``state`` are open for business on ``d``."""
        ...

    def add_working_days(self, d: date, n: int, state: str) -> date:
        """Return the date ``n`` working days after ``d``, not counting ``d`` itself."""
        ...

    def working_days_between(self, start_exclusive: date, end_inclusive: date, state: str) -> int:
        """Count working days in the half-open range ``(start_exclusive, end_inclusive]``."""
        ...

    def add_calendar_days(self, d: date, n: int) -> date:
        """Return the date ``n`` calendar days after ``d`` (the CALENDAR day basis)."""
        ...
