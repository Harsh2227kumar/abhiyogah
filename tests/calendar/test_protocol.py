"""The BankCalendar protocol is importable from the package root and runtime-checkable."""

from datetime import date, timedelta

from abhiyogah.calendar import BankCalendar


class _EveryDayOpen:
    """Minimal stand-in that treats every day as a working day."""

    version = "test"

    def is_working_day(self, d: date, state: str) -> bool:
        return True

    def add_working_days(self, d: date, n: int, state: str) -> date:
        return d + timedelta(days=n)

    def working_days_between(self, start_exclusive: date, end_inclusive: date, state: str) -> int:
        return (end_inclusive - start_exclusive).days

    def add_calendar_days(self, d: date, n: int) -> date:
        return d + timedelta(days=n)


def test_structural_implementation_satisfies_protocol() -> None:
    assert isinstance(_EveryDayOpen(), BankCalendar)


def test_object_missing_methods_does_not_satisfy_protocol() -> None:
    assert not isinstance(object(), BankCalendar)
