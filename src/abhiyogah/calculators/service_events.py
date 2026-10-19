"""Service-event compensation (report Table C, row B12 and the "formulas" section).

The report's formulas, with every amount, rate and period passed in from the rule pack:

- **Property documents (C3, paras 354-360):** ``per_day x days beyond allowed_days`` after full
  repayment (₹5,000/day beyond 30 days, or 60 if documents were lost).
- **Deceased locker claims (C2, paras 320, 322):** ``per_day x days of delay`` beyond the
  settlement period (₹5,000/day, 15 days).
- **Deceased deposit claims (C1, paras 317-321):** interest at no less than Bank Rate + 4% p.a. on
  the amount, from the date documents were complete, when settlement is late:
  ``amount x (bank_rate + spread) x delay / 365``.
- **Card closure:** ``per_day x days beyond allowed working days`` (₹500/day beyond 7 working days).
- **Credit information (B12):** ``per_day x days beyond allowed_days`` (₹100/day beyond 30 days).

Two things the report does not settle are explicit arguments, never defaults: the basis on which
"days of delay" after a working-day deadline are counted (``late_basis``), and how fractional paise
of interest are rounded (``rounding``).
"""

from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import StrEnum

from abhiyogah.calculators.errors import CalculatorError
from abhiyogah.calculators.per_day import per_day_compensation
from abhiyogah.clocks import BankCalendar
from abhiyogah.domain.decision import Compensation
from abhiyogah.domain.enums import DayBasis
from abhiyogah.domain.money import Paise

__all__ = [
    "PaiseRounding",
    "card_closure_compensation",
    "credit_information_compensation",
    "days_beyond",
    "deceased_deposit_interest",
    "deceased_locker_compensation",
    "property_documents_compensation",
]


class PaiseRounding(StrEnum):
    """How fractional paise are rounded. The rule pack or the bank's policy chooses."""

    DOWN = "DOWN"
    UP = "UP"
    HALF_UP = "HALF_UP"


_DECIMAL_ROUNDING = {
    PaiseRounding.DOWN: ROUND_FLOOR,
    PaiseRounding.UP: ROUND_CEILING,
    PaiseRounding.HALF_UP: ROUND_HALF_UP,
}


def days_beyond(
    start: date,
    end: date | None,
    as_of: date,
    allowed: int,
    allowed_basis: DayBasis,
    late_basis: DayBasis,
    calendar: BankCalendar,
    state: str | None = None,
) -> tuple[date, int]:
    """The due date and the days late at ``end`` (or ``as_of`` if not done), on ``late_basis``."""
    if allowed < 0:
        raise CalculatorError(f"allowed days must be >= 0, got {allowed}")
    if end is not None and end < start:
        raise CalculatorError(f"end {end} is before start {start}")
    if DayBasis.WORKING in (allowed_basis, late_basis) and not state:
        raise CalculatorError("working-day counting needs the home-branch state")
    if allowed_basis is DayBasis.WORKING:
        assert state is not None  # noqa: S101 - checked above
        due = calendar.add_working_days(start, allowed, state)
    else:
        due = calendar.add_calendar_days(start, allowed)
    stop = end if end is not None and end <= as_of else as_of
    if stop <= due:
        return due, 0
    if late_basis is DayBasis.WORKING:
        assert state is not None  # noqa: S101 - checked above
        return due, calendar.working_days_between(due, stop, state)
    return due, (stop - due).days


def _per_day(
    label: str,
    start: date,
    end: date | None,
    as_of: date,
    allowed: int,
    per_day_paise: int,
    calendar: BankCalendar,
    allowed_basis: DayBasis = DayBasis.CALENDAR,
    late_basis: DayBasis = DayBasis.CALENDAR,
    state: str | None = None,
) -> Compensation:
    """Shared body of the per-day service-event formulas."""
    due, late = days_beyond(start, end, as_of, allowed, allowed_basis, late_basis, calendar, state)
    stop = end if end is not None and end <= as_of else as_of
    return per_day_compensation(
        per_day_paise,
        late,
        f"{label}: per_day x days beyond {allowed} {allowed_basis.lower()} days",
        {
            "start": start.isoformat(),
            "end": stop.isoformat(),
            "end_is_as_of": stop != end,
            "due_date": due.isoformat(),
            "allowed_days": allowed,
            "late_basis": late_basis.value,
        },
    )


def property_documents_compensation(
    full_repayment: date,
    released: date | None,
    as_of: date,
    allowed_days: int,
    per_day_paise: int,
    calendar: BankCalendar,
) -> Compensation:
    """C3: per-day compensation for releasing property documents late (calendar days)."""
    return _per_day(
        "property documents", full_repayment, released, as_of, allowed_days, per_day_paise, calendar
    )


def deceased_locker_compensation(
    documents_complete: date,
    settled: date | None,
    as_of: date,
    allowed_days: int,
    per_day_paise: int,
    calendar: BankCalendar,
) -> Compensation:
    """C2: per-day compensation for settling a deceased hirer's locker claim late."""
    return _per_day(
        "deceased locker", documents_complete, settled, as_of, allowed_days, per_day_paise, calendar
    )


def credit_information_compensation(
    received: date,
    resolved: date | None,
    as_of: date,
    allowed_days: int,
    per_day_paise: int,
    calendar: BankCalendar,
    allowed_basis: DayBasis,
) -> Compensation:
    """B12: per-day compensation beyond the resolution period (basis conflicting, Q10)."""
    return _per_day(
        "credit information",
        received,
        resolved,
        as_of,
        allowed_days,
        per_day_paise,
        calendar,
        allowed_basis=allowed_basis,
        late_basis=allowed_basis,
    )


def card_closure_compensation(
    requested: date,
    closed: date | None,
    as_of: date,
    allowed_wd: int,
    per_day_paise: int,
    calendar: BankCalendar,
    state: str,
    late_basis: DayBasis,
) -> Compensation:
    """Card closure: per-day compensation beyond ``allowed_wd`` working days."""
    return _per_day(
        "card closure",
        requested,
        closed,
        as_of,
        allowed_wd,
        per_day_paise,
        calendar,
        allowed_basis=DayBasis.WORKING,
        late_basis=late_basis,
        state=state,
    )


def deceased_deposit_interest(
    amount_paise: int,
    documents_complete: date,
    settled: date | None,
    as_of: date,
    allowed_days: int,
    bank_rate_bp: int,
    spread_bp: int,
    rounding: PaiseRounding,
    calendar: BankCalendar,
) -> Compensation:
    """C1: ``amount x (bank_rate + spread) x delay / 365`` when settlement is late.

    The delay runs from the date documents were complete; rates are in basis points per annum.
    """
    if amount_paise < 0 or bank_rate_bp < 0 or spread_bp < 0:
        raise CalculatorError("amount and rates must be >= 0")
    due, late = days_beyond(
        documents_complete,
        settled,
        as_of,
        allowed_days,
        DayBasis.CALENDAR,
        DayBasis.CALENDAR,
        calendar,
    )
    stop = settled if settled is not None and settled <= as_of else as_of
    delay = (stop - documents_complete).days if late > 0 else 0
    rate_bp = bank_rate_bp + spread_bp
    exact = Decimal(amount_paise) * rate_bp * delay / (Decimal(10_000) * 365)
    amount = int(exact.quantize(Decimal(1), rounding=_DECIMAL_ROUNDING[rounding]))
    return Compensation(
        amount_paise=Paise(amount),
        formula="amount x (bank_rate + spread) x delay / 365, delay from documents complete",
        inputs={
            "amount_paise": amount_paise,
            "bank_rate_bp": bank_rate_bp,
            "spread_bp": spread_bp,
            "delay_days": delay,
            "due_date": due.isoformat(),
            "end": stop.isoformat(),
            "rounding": rounding.value,
            "exact_paise": str(exact),
        },
    )
