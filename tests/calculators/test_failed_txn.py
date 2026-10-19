"""Failed-transaction compensation: per_day x max(0, R - (T + n)) (report B1)."""

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from abhiyogah.calculators import CalculatorError
from abhiyogah.calculators.failed_txn import (
    DelayKind,
    Recipient,
    failed_txn_compensation,
)

PER_DAY = 100_00  # B1: ₹100 per day, in paise (the rule pack supplies it in production)
T = date(2026, 8, 3)


def test_upi_p2p_reversed_three_days_late() -> None:
    """UPI P2P T+1 (B1): T 3 Aug, due 4 Aug, R 7 Aug -> 3 days -> ₹300."""
    res = failed_txn_compensation(T, date(2026, 8, 7), date(2026, 8, 20), 1, PER_DAY)
    assert res.due_date == date(2026, 8, 4)
    assert res.days_late == 3
    assert res.compensation.amount_paise == 300_00
    assert res.compensation.inputs["R"] == "2026-08-07"


def test_reversed_on_time_owes_nothing() -> None:
    """R on T + n owes nothing."""
    res = failed_txn_compensation(T, date(2026, 8, 8), date(2026, 8, 20), 5, PER_DAY)
    assert res.compensation.amount_paise == 0


def test_unreversed_accrues_to_as_of() -> None:
    """With no reversal yet, the amount owed so far runs to as_of."""
    res = failed_txn_compensation(T, None, date(2026, 8, 10), 5, PER_DAY)
    assert res.days_late == 2
    assert res.compensation.amount_paise == 200_00
    assert "R = as_of" in res.compensation.formula


def test_future_reversal_is_not_yet_known() -> None:
    """A reversal after as_of is treated as not yet happened."""
    res = failed_txn_compensation(T, date(2026, 8, 30), date(2026, 8, 10), 5, PER_DAY)
    assert res.days_late == 2


def test_recipient_rule() -> None:
    """Beneficiary for a delayed credit-push, originator for delayed initiation."""
    push = failed_txn_compensation(T, T, T, 1, PER_DAY, DelayKind.CREDIT_PUSH)
    init = failed_txn_compensation(T, T, T, 1, PER_DAY, DelayKind.INITIATION)
    assert push.recipient is Recipient.BENEFICIARY
    assert init.recipient is Recipient.ORIGINATOR
    assert failed_txn_compensation(T, T, T, 1, PER_DAY).recipient is None


def test_bad_inputs() -> None:
    """Reversal before T, negative TAT or amount, as_of before T are errors."""
    with pytest.raises(CalculatorError):
        failed_txn_compensation(T, T - timedelta(days=1), T, 1, PER_DAY)
    with pytest.raises(CalculatorError):
        failed_txn_compensation(T, None, T, -1, PER_DAY)
    with pytest.raises(CalculatorError):
        failed_txn_compensation(T, None, T, 1, -1)
    with pytest.raises(CalculatorError):
        failed_txn_compensation(T, None, T - timedelta(days=1), 1, PER_DAY)


@given(
    st.integers(min_value=0, max_value=10),
    st.integers(min_value=0, max_value=60),
    st.integers(min_value=0, max_value=10_000_00),
)
def test_formula_property(n: int, delay: int, per_day: int) -> None:
    """Amount is always per_day x max(0, R - (T + n)) and never negative."""
    r = T + timedelta(days=delay)
    res = failed_txn_compensation(T, r, r, n, per_day)
    assert res.compensation.amount_paise == per_day * max(0, delay - n)
