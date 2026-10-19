"""Typed exceptions raised by the bank calendar."""

from abhiyogah.domain.errors import DomainError

__all__ = [
    "CalendarError",
    "CalendarRangeError",
    "OverlayDataError",
    "UnknownStateError",
]


class CalendarError(DomainError):
    """Base class for every bank-calendar error."""


class UnknownStateError(CalendarError, ValueError):
    """A state or union territory code the calendar does not know."""


class CalendarRangeError(CalendarError, ValueError):
    """A date outside the years for which the calendar has complete holiday data."""


class OverlayDataError(CalendarError):
    """An overlay file under ``data/calendars/`` is malformed or inconsistent."""
