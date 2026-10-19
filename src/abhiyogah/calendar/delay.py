"""Customer reporting delay in working days, as RBC-CB para 71 counts it (report Table B, B5).

Per the research report's summary of para 71, the working days in the customer-liability tiers are
counted on the working schedule of the customer's home branch, excluding the day of receipt of the
bank's communication.
"""

from datetime import date, datetime

from abhiyogah.calendar.protocol import BankCalendar
from abhiyogah.domain.tz import ist_date

__all__ = ["delay_working_days"]


def delay_working_days(
    alert_received: date | datetime,
    reported: date | datetime,
    state: str,
    *,
    calendar: BankCalendar,
) -> int:
    """Working days from the customer receiving the bank's alert to reporting it (para 71).

    The receipt day is excluded and the reporting day counts if it is a working day, so a report
    on the next working day is a delay of 1 and a same-day report is 0. ``state`` is the home
    branch's state. Datetimes must be timezone-aware and are converted to IST dates first.
    """
    return calendar.working_days_between(
        _as_ist_date(alert_received), _as_ist_date(reported), state
    )


def _as_ist_date(value: date | datetime) -> date:
    """Return the IST calendar date of an aware datetime, or the date unchanged."""
    if isinstance(value, datetime):
        return ist_date(value)
    return value
