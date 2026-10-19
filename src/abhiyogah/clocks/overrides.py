"""Resolve an obligation's ``overridden_by`` list to exactly one deadline.

An obligation such as IO Directions 2026 cl. 14(1)(b) (escalate within 20 days) names the
obligations that replace its deadline when they apply, here cl. 14(1)(a) (escalate by the external
TAT minus 10 days). The report's formula is a replacement, not "whichever is earlier":
``io_due = bank_receipt + 20d`` for ordinary complaints and
``io_due = external_TAT_deadline - 10d`` for network-governed ones.

Resolution rules:

1. If no overriding obligation applies, the base deadline stands.
2. If exactly one applies, its deadline replaces the base one.
3. If more than one applies, the rule pack is ambiguous and ``OverrideConflictError`` is raised. The
   engine never picks one on its own.

Every overriding obligation, applied or not, leaves a ``ConditionTrace`` line saying why.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from abhiyogah.clocks.clock import Clock
from abhiyogah.clocks.errors import ClockError
from abhiyogah.domain.decision import ConditionTrace

__all__ = [
    "DeadlineCandidate",
    "NotApplied",
    "OverrideConflictError",
    "OverrideResolution",
    "resolve_overrides",
]


class OverrideConflictError(ClockError):
    """More than one overriding obligation applies; the rule pack must say which one wins."""


@dataclass(frozen=True, slots=True)
class DeadlineCandidate:
    """A deadline one obligation would impose: its clock and how its duration was derived."""

    obligation_id: str
    clock: Clock
    rule: str
    """How the deadline was derived, e.g. ``'bank_receipt_date + 20d'``."""


@dataclass(frozen=True, slots=True)
class NotApplied:
    """An overriding obligation that does not apply to this complaint, and why."""

    obligation_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class OverrideResolution:
    """The one deadline that governs, the one it replaced (if any), and the trace."""

    chosen: DeadlineCandidate
    replaced: DeadlineCandidate | None
    trace: tuple[ConditionTrace, ...]

    @property
    def overridden(self) -> bool:
        """True if an overriding obligation replaced the base deadline."""
        return self.replaced is not None


def resolve_overrides(
    base: DeadlineCandidate,
    overrides: Sequence[DeadlineCandidate | NotApplied],
    as_of: date | datetime | None = None,
) -> OverrideResolution:
    """Resolve ``base`` against its ``overridden_by`` obligations (see the module docstring)."""
    trace: list[ConditionTrace] = []
    applied: list[DeadlineCandidate] = []
    for item in overrides:
        if isinstance(item, NotApplied):
            trace.append(
                ConditionTrace(
                    condition=f"override {item.obligation_id} applies",
                    result=False,
                    detail=item.reason,
                )
            )
            continue
        applied.append(item)
        trace.append(
            ConditionTrace(
                condition=f"override {item.obligation_id} applies",
                result=True,
                detail=(
                    f"due {item.clock.due_date(as_of)} ({item.rule}) replaces "
                    f"{base.obligation_id} due {base.clock.due_date(as_of)} ({base.rule})"
                ),
            )
        )
    if len(applied) > 1:
        ids = ", ".join(c.obligation_id for c in applied)
        raise OverrideConflictError(f"{base.obligation_id}: several overrides apply: {ids}")
    if applied:
        return OverrideResolution(chosen=applied[0], replaced=base, trace=tuple(trace))
    return OverrideResolution(chosen=base, replaced=None, trace=tuple(trace))
