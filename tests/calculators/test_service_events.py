"""Service-event compensation formulas (report Table C and B12)."""

from datetime import date

import pytest

from abhiyogah.calculators import CalculatorError
from abhiyogah.calculators.service_events import (
    PaiseRounding,
    card_closure_compensation,
    credit_information_compensation,
    days_beyond,
    deceased_deposit_interest,
    deceased_locker_compensation,
    property_documents_compensation,
)
from abhiyogah.domain.enums import DayBasis
from tests.clocks.fakes import FakeCalendar

CAL = FakeCalendar(holidays=[date(2026, 8, 15)])
AS_OF = date(2026, 12, 31)


def test_property_documents_beyond_30_days() -> None:
    """C3: repaid 1 Aug, due 31 Aug, released 5 Sep: 5 days x ₹5,000 = ₹25,000."""
    comp = property_documents_compensation(
        date(2026, 8, 1), date(2026, 9, 5), AS_OF, 30, 5_000_00, CAL
    )
    assert comp.amount_paise == 25_000_00
    assert comp.inputs["due_date"] == "2026-08-31"


def test_property_documents_lost_60_days_and_not_released() -> None:
    """C3 lost documents: 60 days; not released yet accrues to as_of."""
    comp = property_documents_compensation(
        date(2026, 8, 1), None, date(2026, 10, 3), 60, 5_000_00, CAL
    )
    assert comp.amount_paise == 3 * 5_000_00
    assert comp.inputs["end_is_as_of"] is True


def test_deceased_locker() -> None:
    """C2: documents complete 1 Aug, 15 days, settled 20 Aug: 4 days x ₹5,000."""
    comp = deceased_locker_compensation(
        date(2026, 8, 1), date(2026, 8, 20), AS_OF, 15, 5_000_00, CAL
    )
    assert comp.amount_paise == 20_000_00


def test_credit_information_beyond_30() -> None:
    """B12: received 1 Aug, resolved 3 Sep (due 31 Aug): 3 days x ₹100."""
    comp = credit_information_compensation(
        date(2026, 8, 1), date(2026, 9, 3), AS_OF, 30, 100_00, CAL, DayBasis.CALENDAR
    )
    assert comp.amount_paise == 300_00


def test_card_closure_late_basis_is_explicit() -> None:
    """Mon 10 Aug + 7 WD (15 holiday, 16 Sun) = Wed 19 Aug; closed Sun 23: 4 calendar or 3 WD."""
    args = (date(2026, 8, 10), date(2026, 8, 23), AS_OF, 7, 500_00, CAL, "MH")
    cal = card_closure_compensation(*args, late_basis=DayBasis.CALENDAR)
    wd = card_closure_compensation(*args, late_basis=DayBasis.WORKING)
    assert cal.inputs["due_date"] == "2026-08-19"
    assert cal.amount_paise == 4 * 500_00
    assert wd.amount_paise == 3 * 500_00


def test_on_time_owes_nothing() -> None:
    """Released on the due date owes nothing."""
    comp = property_documents_compensation(
        date(2026, 8, 1), date(2026, 8, 31), AS_OF, 30, 5_000_00, CAL
    )
    assert comp.amount_paise == 0


def test_deceased_deposit_interest() -> None:
    """C1: ₹1,00,000 at 6.5% + 4% for 73 days (late settlement) = ₹2,100 exactly."""
    comp = deceased_deposit_interest(
        1_00_000_00,
        date(2026, 8, 1),
        date(2026, 10, 13),
        AS_OF,
        15,
        650,  # synthetic Bank Rate for the test, in basis points
        400,  # C1: + 4% p.a.
        PaiseRounding.DOWN,
        CAL,
    )
    assert comp.inputs["delay_days"] == 73
    assert comp.amount_paise == 2_100_00


def test_deceased_deposit_on_time_and_rounding() -> None:
    """No interest when settled in time; fractional paise follow the chosen rounding."""
    on_time = deceased_deposit_interest(
        1_00_000_00, date(2026, 8, 1), date(2026, 8, 10), AS_OF, 15, 650, 400, PaiseRounding.UP, CAL
    )
    assert on_time.amount_paise == 0
    args = (1_000_01, date(2026, 8, 1), date(2026, 8, 20), AS_OF, 15, 650, 400)
    down = deceased_deposit_interest(*args, PaiseRounding.DOWN, CAL)
    up = deceased_deposit_interest(*args, PaiseRounding.UP, CAL)
    assert up.amount_paise == down.amount_paise + 1


def test_bad_inputs() -> None:
    """Negative values, end before start and working days without a state are errors."""
    with pytest.raises(CalculatorError):
        days_beyond(
            date(2026, 8, 2), date(2026, 8, 1), AS_OF, 5, DayBasis.CALENDAR, DayBasis.CALENDAR, CAL
        )
    with pytest.raises(CalculatorError):
        days_beyond(date(2026, 8, 1), None, AS_OF, -1, DayBasis.CALENDAR, DayBasis.CALENDAR, CAL)
    with pytest.raises(CalculatorError):
        days_beyond(date(2026, 8, 1), None, AS_OF, 5, DayBasis.WORKING, DayBasis.CALENDAR, CAL)
    with pytest.raises(CalculatorError):
        deceased_deposit_interest(
            -1, date(2026, 8, 1), None, AS_OF, 15, 650, 400, PaiseRounding.DOWN, CAL
        )
