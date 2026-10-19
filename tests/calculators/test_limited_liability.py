"""Limited liability: delay tier, caps, shadow credit and determination dates (B5-B7)."""

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from abhiyogah.calculators import CalculatorError
from abhiyogah.calculators.limited_liability import (
    LiabilityResult,
    LiabilityTier,
    customer_liability,
    delay_working_days,
    determination_due_date,
    shadow_credit_due_date,
)
from abhiyogah.domain.enums import AccountType
from tests.clocks.fakes import FakeCalendar

CAL = FakeCalendar(holidays=[date(2026, 8, 15)])
# Report Table B row B5 caps, in paise (the rule pack supplies these in production).
CAPS = {
    AccountType.BSBD: 5_000_00,
    AccountType.OTHER_SAVINGS: 10_000_00,
    AccountType.CREDIT_CARD_LARGE_LIMIT: 25_000_00,
}
ZERO_MAX, LIMITED_MAX = 3, 7  # B5: within 3 working days; 4-7 working days


def liability(
    delay: int, txn: int, acct: AccountType, fault: bool | None = False
) -> LiabilityResult:
    """Shorthand with the B5 thresholds."""
    return customer_liability(delay, txn, acct, CAPS, ZERO_MAX, LIMITED_MAX, fault)


def test_delay_excludes_receipt_day_and_closed_days() -> None:
    """Alert Thu 13 Aug; reported Tue 18 Aug: Fri 14, Mon 17, Tue 18 = 3 WD (15 holiday, 16 Sun)."""
    assert delay_working_days(CAL, date(2026, 8, 13), date(2026, 8, 18), "MH") == 3
    assert delay_working_days(CAL, date(2026, 8, 13), date(2026, 8, 13), "MH") == 0
    with pytest.raises(CalculatorError):
        delay_working_days(CAL, date(2026, 8, 13), date(2026, 8, 12), "MH")


def test_tiers() -> None:
    """0-3 WD zero; 4-7 WD min(txn, cap); beyond 7 board policy."""
    assert liability(3, 50_000_00, AccountType.BSBD).tier is LiabilityTier.ZERO
    four = liability(4, 50_000_00, AccountType.BSBD)
    assert four.tier is LiabilityTier.LIMITED
    assert four.customer_liability_paise == 5_000_00
    small = liability(7, 2_000_00, AccountType.OTHER_SAVINGS)
    assert small.customer_liability_paise == 2_000_00
    board = liability(8, 50_000_00, AccountType.BSBD)
    assert board.tier is LiabilityTier.BOARD_POLICY
    assert board.customer_liability_paise is None


def test_bank_fault() -> None:
    """Bank fault is zero whatever the delay; unknown fault is undetermined past 3 WD."""
    assert liability(30, 1_00, AccountType.BSBD, fault=True).tier is LiabilityTier.ZERO
    assert liability(2, 1_00, AccountType.BSBD, fault=None).tier is LiabilityTier.ZERO
    assert liability(5, 1_00, AccountType.BSBD, fault=None).tier is LiabilityTier.UNDETERMINED


def test_missing_cap_and_bad_inputs() -> None:
    """An account type without a cap, bad thresholds or negatives are errors."""
    with pytest.raises(CalculatorError):
        liability(5, 1_00, AccountType.PPI)
    with pytest.raises(CalculatorError):
        customer_liability(5, 1_00, AccountType.BSBD, CAPS, 7, 3, False)
    with pytest.raises(CalculatorError):
        liability(-1, 1_00, AccountType.BSBD)


def test_shadow_credit_and_determination_dates() -> None:
    """B6: 10 WD after notification; B7: 90 calendar days after receipt."""
    # Mon 10 Aug + 10 WD, skipping Sat 15 (holiday) and Sun 16: 11,12,13,14,17,18,19,20,21,22.
    assert shadow_credit_due_date(CAL, date(2026, 8, 10), 10, "MH") == date(2026, 8, 22)
    assert determination_due_date(CAL, date(2026, 8, 10), 90) == date(2026, 11, 8)
    with pytest.raises(CalculatorError):
        shadow_credit_due_date(CAL, date(2026, 8, 10), -1, "MH")
    with pytest.raises(CalculatorError):
        determination_due_date(CAL, date(2026, 8, 10), -1)


@given(st.integers(min_value=0, max_value=30), st.integers(min_value=0, max_value=10**8))
def test_liability_never_exceeds_transaction_or_cap(delay: int, txn: int) -> None:
    """Customer liability is never more than the transaction or the cap."""
    res = liability(delay, txn, AccountType.OTHER_SAVINGS)
    if res.customer_liability_paise is not None:
        assert res.customer_liability_paise <= min(txn, CAPS[AccountType.OTHER_SAVINGS])


def test_amount_and_account_needed_only_for_limited_tier() -> None:
    """Unknown amount/account is fine for ZERO and BOARD_POLICY, an error for LIMITED."""
    zero = customer_liability(2, None, None, CAPS, ZERO_MAX, LIMITED_MAX, False)
    assert zero.tier is LiabilityTier.ZERO
    board = customer_liability(9, None, None, CAPS, ZERO_MAX, LIMITED_MAX, False)
    assert board.tier is LiabilityTier.BOARD_POLICY
    with pytest.raises(CalculatorError):
        customer_liability(5, None, AccountType.BSBD, CAPS, ZERO_MAX, LIMITED_MAX, False)
