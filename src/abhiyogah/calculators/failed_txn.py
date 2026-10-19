"""Failed-transaction compensation (report row B1, RBI/2019-20/67 Annex).

``compensation = per_day x max(0, R - (T + n))`` in calendar days (T is defined as a calendar
date), credited without a claim. ``n`` is the channel's TAT and ``per_day`` the per-day amount, both
read from the rule pack (B1: ₹100 per day). While the reversal R has not happened, the amount owed
so far is computed with the ``as_of`` date in place of R, and the formula says so.

Who is paid (B1): the beneficiary for a delayed credit-push, the originator for delayed initiation.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from abhiyogah.calculators.errors import CalculatorError
from abhiyogah.calculators.per_day import per_day_compensation
from abhiyogah.domain.decision import Compensation

__all__ = ["DelayKind", "FailedTxnResult", "Recipient", "failed_txn_compensation", "recipient_for"]


class DelayKind(StrEnum):
    """What was delayed (B1 payee rule)."""

    CREDIT_PUSH = "CREDIT_PUSH"
    """The credit to the beneficiary was delayed."""
    INITIATION = "INITIATION"
    """The originator-side action (initiation or reversal of the debit) was delayed."""


class Recipient(StrEnum):
    """Who receives failed-transaction compensation."""

    BENEFICIARY = "BENEFICIARY"
    ORIGINATOR = "ORIGINATOR"


def recipient_for(kind: DelayKind) -> Recipient:
    """B1: beneficiary for a delayed credit-push, originator for delayed initiation."""
    return Recipient.BENEFICIARY if kind is DelayKind.CREDIT_PUSH else Recipient.ORIGINATOR


@dataclass(frozen=True, slots=True)
class FailedTxnResult:
    """The compensation, the TAT due date, days late and (if known) who is paid."""

    compensation: Compensation
    due_date: date
    days_late: int
    recipient: Recipient | None


def failed_txn_compensation(
    t: date,
    r: date | None,
    as_of: date,
    tat_days: int,
    per_day_paise: int,
    delay_kind: DelayKind | None = None,
) -> FailedTxnResult:
    """B1 compensation at ``as_of``: ``per_day x max(0, R - (T + n))``, R = ``as_of`` if unknown."""
    if tat_days < 0:
        raise CalculatorError(f"TAT must be >= 0 days, got {tat_days}")
    if r is not None and r < t:
        raise CalculatorError(f"reversal {r} is before transaction date {t}")
    if as_of < t:
        raise CalculatorError(f"as_of {as_of} is before transaction date {t}")
    due = date.fromordinal(t.toordinal() + tat_days)
    end = r if r is not None and r <= as_of else as_of
    days_late = max(0, (end - due).days)
    recipient = recipient_for(delay_kind) if delay_kind is not None else None
    formula = "per_day x max(0, R - (T + n))" + (
        "" if end == r else " with R = as_of (no reversal)"
    )
    comp = per_day_compensation(
        per_day_paise,
        days_late,
        formula,
        {
            "T": t.isoformat(),
            "R": end.isoformat(),
            "n": tat_days,
            "recipient": recipient.value if recipient is not None else None,
        },
    )
    return FailedTxnResult(comp, due, days_late, recipient)
