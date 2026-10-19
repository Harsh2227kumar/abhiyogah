"""Customer liability for unauthorised electronic transactions (report rows B5-B7, RBC-CB 67-73).

Every threshold, cap and duration is passed in from the rule pack; nothing regulatory is a constant
here. The report's formulas:

- **Delay (B5, para 71):** ``delay_wd`` = working days on the home-branch calendar from the day the
  customer received the bank's transaction communication (that day excluded) to the report date.
- **Tier (B5, paras 67-70):** zero if the bank is at fault, or if a third-party breach is reported
  within ``zero_max_wd`` working days (3); ``min(transaction, cap[account_type])`` up to
  ``limited_max_wd`` working days (7); beyond that, the bank's board-approved policy decides.
- **Shadow credit (B6, para 72):** due ``shadow_credit_wd`` working days (10) after the customer's
  notification.
- **Determination (B7, para 73):** due ``determination_days`` calendar days (90, basis inferred)
  after the bank received the complaint.

An unknown "bank at fault" is never assumed: where it would change the answer the tier is
``UNDETERMINED``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from abhiyogah.calculators.errors import CalculatorError
from abhiyogah.clocks import BankCalendar
from abhiyogah.domain.enums import AccountType
from abhiyogah.domain.money import Paise

__all__ = [
    "LiabilityResult",
    "LiabilityTier",
    "customer_liability",
    "delay_working_days",
    "determination_due_date",
    "shadow_credit_due_date",
]


class LiabilityTier(StrEnum):
    """Which limb of the liability framework applies."""

    ZERO = "ZERO"
    LIMITED = "LIMITED"
    BOARD_POLICY = "BOARD_POLICY"
    UNDETERMINED = "UNDETERMINED"
    """Depends on whether the bank was at fault, which is not known."""


@dataclass(frozen=True, slots=True)
class LiabilityResult:
    """The tier, the customer's maximum liability in paise (None if not fixed by RBI), and why."""

    tier: LiabilityTier
    customer_liability_paise: Paise | None
    delay_wd: int
    reason: str
    formula: str


def delay_working_days(
    calendar: BankCalendar, communication_received: date, reported: date, state: str
) -> int:
    """Working days in ``(received, reported]`` in the home-branch calendar, para 71."""
    if reported < communication_received:
        raise CalculatorError(
            f"reported {reported} is before communication {communication_received}"
        )
    return calendar.working_days_between(communication_received, reported, state)


def customer_liability(
    delay_wd: int,
    transaction_paise: int | None,
    account_type: AccountType | None,
    caps: Mapping[AccountType, int],
    zero_max_wd: int,
    limited_max_wd: int,
    bank_at_fault: bool | None,
) -> LiabilityResult:
    """The B5 tier and the customer's liability (see the module docstring).

    The transaction amount and account type are needed only for the ``LIMITED`` tier; pass None
    when they are unknown and the tier turns out not to need them.
    """
    if delay_wd < 0 or (transaction_paise is not None and transaction_paise < 0):
        raise CalculatorError("delay and transaction amount must be >= 0")
    if not 0 <= zero_max_wd < limited_max_wd:
        raise CalculatorError(f"thresholds out of order: {zero_max_wd}, {limited_max_wd}")
    if bank_at_fault:
        return LiabilityResult(
            LiabilityTier.ZERO, Paise(0), delay_wd, "bank at fault", "zero liability"
        )
    if delay_wd <= zero_max_wd:
        return LiabilityResult(
            LiabilityTier.ZERO,
            Paise(0),
            delay_wd,
            f"reported within {zero_max_wd} working days",
            f"delay_wd {delay_wd} <= {zero_max_wd}: zero liability",
        )
    if bank_at_fault is None:
        return LiabilityResult(
            LiabilityTier.UNDETERMINED,
            None,
            delay_wd,
            "bank at fault unknown; it decides between zero and the delay tiers",
            f"delay_wd {delay_wd} > {zero_max_wd}",
        )
    if delay_wd <= limited_max_wd:
        if account_type is None or transaction_paise is None:
            raise CalculatorError("the LIMITED tier needs the account type and transaction amount")
        if account_type not in caps:
            raise CalculatorError(f"no liability cap for account type {account_type}")
        cap = caps[account_type]
        return LiabilityResult(
            LiabilityTier.LIMITED,
            Paise(min(transaction_paise, cap)),
            delay_wd,
            f"third-party breach reported in {zero_max_wd + 1}-{limited_max_wd} working days",
            f"min(transaction {transaction_paise}, cap[{account_type}] {cap})",
        )
    return LiabilityResult(
        LiabilityTier.BOARD_POLICY,
        None,
        delay_wd,
        f"reported after {limited_max_wd} working days",
        "per the bank's board-approved policy",
    )


def shadow_credit_due_date(
    calendar: BankCalendar, notified: date, shadow_credit_wd: int, state: str
) -> date:
    """B6: ``shadow_credit_wd`` working days after the customer's notification (day excluded)."""
    if shadow_credit_wd < 0:
        raise CalculatorError("shadow credit working days must be >= 0")
    return calendar.add_working_days(notified, shadow_credit_wd, state)


def determination_due_date(calendar: BankCalendar, received: date, determination_days: int) -> date:
    """B7: ``determination_days`` calendar days after the bank received the complaint."""
    if determination_days < 0:
        raise CalculatorError("determination days must be >= 0")
    return calendar.add_calendar_days(received, determination_days)
