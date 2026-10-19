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
        """Return True if banks in ``state`` are open on ``d``; defines the WORKING day basis.

        Bank closures follow the report's gap-analysis row 19: Sundays, 2nd/4th Saturdays and the
        state's Negotiable Instruments Act holidays. Para 71 counts on the home branch's schedule,
        so ``state`` is the home branch's state.
        """
        ...

    def add_working_days(self, d: date, n: int, state: str) -> date:
        """Return the date ``n`` working days after ``d``, not counting ``d`` itself.

        The WORKING-basis deadline rule: the start day is excluded, as RBC-CB para 71 excludes the
        day of receipt (report Table B, B5). Used for B6, C4-C6, C15 and A24 deadlines.
        """
        ...

    def working_days_between(self, start_exclusive: date, end_inclusive: date, state: str) -> int:
        """Count working days in the half-open range ``(start_exclusive, end_inclusive]``.

        This is the para 71 count (report Table B, B5): the day of receipt is excluded and the end
        day counts if it is a working day. It inverts :meth:`add_working_days`.
        """
        ...

    def add_calendar_days(self, d: date, n: int) -> date:
        """Return the date ``n`` calendar days after ``d``; the CALENDAR day basis.

        Holidays never move a CALENDAR deadline (CLAUDE.md "Day basis is explicit"); the start day
        is excluded the same way, so ``n == 0`` returns ``d``.
        """
        ...
