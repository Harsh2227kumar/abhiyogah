"""The calendar interface the clock engine needs: the bank calendar's ``BankCalendar`` protocol.

Re-exported from ``abhiyogah.calendar.protocol`` (stream 01) so the engine and the calendar share
one definition. Working-day arithmetic excludes the start day, as RBC-CB para 71 requires for the
day a communication was received. Tests may still pass any structural double.
"""

from abhiyogah.calendar.protocol import BankCalendar

__all__ = ["BankCalendar"]
