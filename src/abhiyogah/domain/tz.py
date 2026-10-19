"""Time-zone helpers: store UTC, do day arithmetic on IST calendar dates."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from abhiyogah.domain.errors import NaiveDatetimeError

__all__ = ["IST", "ist_date"]

IST = ZoneInfo("Asia/Kolkata")
"""The zone every regulatory day count uses."""


def ist_date(dt: datetime) -> date:
    """Return the Asia/Kolkata calendar date of an aware datetime."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise NaiveDatetimeError("naive datetime; every datetime must be timezone-aware")
    return dt.astimezone(IST).date()
