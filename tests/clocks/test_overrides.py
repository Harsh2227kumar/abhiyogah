"""Override resolution: 20 days vs TAT - 10 days resolves to one deadline with a trace."""

from datetime import date

import pytest

from abhiyogah.clocks import Clock
from abhiyogah.clocks.overrides import (
    DeadlineCandidate,
    NotApplied,
    OverrideConflictError,
    resolve_overrides,
)
from abhiyogah.domain.enums import BasisStatus, DayBasis
from tests.clocks.fakes import FakeCalendar

CAL = FakeCalendar()
RECEIPT = date(2026, 8, 3)


def candidate(obligation_id: str, days: int, rule: str) -> DeadlineCandidate:
    """A calendar-day deadline from the bank receipt date."""
    clock = Clock(
        start_date=RECEIPT,
        duration_days=days,
        basis=DayBasis.CALENDAR,
        basis_status=BasisStatus.INFERRED,
        calendar=CAL,
    )
    return DeadlineCandidate(obligation_id, clock, rule)


BASE = candidate("IO-CB-2026-14-1-b", 20, "bank_receipt_date + 20d")
# Synthetic external TAT of 25 days: 25 - 10 = 15 days from receipt.
TAT = candidate("IO-CB-2026-14-1-a", 15, "bank_receipt_date + (25d TAT - 10d)")


def test_no_override_applies_keeps_base() -> None:
    """Without an external TAT, the 20-day deadline stands and the trace says why."""
    res = resolve_overrides(BASE, [NotApplied("IO-CB-2026-14-1-a", "external_tat_days unknown")])
    assert res.chosen is BASE
    assert not res.overridden
    (line,) = res.trace
    assert line.result is False
    assert line.condition == "override IO-CB-2026-14-1-a applies"
    assert "external_tat_days" in line.detail


def test_applicable_override_replaces_base() -> None:
    """With an external TAT, TAT - 10 replaces the 20-day deadline."""
    res = resolve_overrides(BASE, [TAT])
    assert res.chosen is TAT
    assert res.replaced is BASE
    assert res.chosen.clock.due_date() == date(2026, 8, 18)
    (line,) = res.trace
    assert line.result is True
    assert "2026-08-18" in line.detail
    assert "2026-08-23" in line.detail


def test_override_replaces_even_when_later() -> None:
    """Replacement, not the earlier of the two: a longer TAT - 10 still governs."""
    long_tat = candidate("IO-CB-2026-14-1-a", 35, "bank_receipt_date + (45d TAT - 10d)")
    assert resolve_overrides(BASE, [long_tat]).chosen is long_tat


def test_two_applicable_overrides_conflict() -> None:
    """The engine never chooses between two applicable overrides."""
    other = candidate("X-2026-1", 10, "synthetic")
    with pytest.raises(OverrideConflictError):
        resolve_overrides(BASE, [TAT, other])
