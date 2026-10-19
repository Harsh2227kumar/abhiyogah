"""Dated parameter lookup and the clock-duration building blocks.

``parameter_at`` picks the value whose effective date is the latest on or before the anchor date
(the rule in ``rules/README.md``). It stands in for the registry resolver until the rule-pack stream
ships ``registry/resolve.py``.

A clocked obligation names its duration with exactly one of these parameters. They are the only
duration shapes the report's formulas need; the numbers themselves always come from the rule pack.

``max_days``
    A fixed number of days: ``due = start + max_days`` (e.g. A13 ordinary limb, 20 days).
``min_days``
    That many days, or the external TAT if it is longer: ``due = start + max(min_days, TAT)``
    (A2: "30 days, or RBI/NPCI/card-network TAT if higher"). With no ``external_tat_days`` fact, no
    external TAT applies and ``min_days`` is used.
``tat_minus_days``
    The external TAT less that many days: ``due = start + (TAT - tat_minus_days)``
    (A13 cl. 14(1)(a), 10 days for IO review). Without an
    ``external_tat_days`` fact the obligation is not triggered.
"""

from dataclasses import dataclass, field
from datetime import date

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.decision import DecisionResult, ParameterUse
from abhiyogah.evaluator.errors import ParameterError
from abhiyogah.registry.schema import Obligation, ParameterValue

__all__ = [
    "DURATION_PARAMETERS",
    "Duration",
    "DurationUndecided",
    "int_parameter",
    "parameter_at",
    "resolve_duration",
]

DURATION_PARAMETERS = ("max_days", "min_days", "tat_minus_days")


def parameter_at(
    obligation: Obligation, name: str, anchor: date
) -> tuple[date, ParameterValue] | None:
    """The ``(effective_date, value)`` in force on ``anchor``, or None if none is yet."""
    history = obligation.parameters.get(name)
    if history is None:
        raise ParameterError(f"{obligation.obligation_id}: no parameter {name!r}")
    eligible = [d for d in history if d <= anchor]
    if not eligible:
        return None
    effective = max(eligible)
    return effective, history[effective]


def int_parameter(
    obligation: Obligation, name: str, anchor: date
) -> tuple[int, ParameterUse] | None:
    """An integer parameter in force on ``anchor`` and its ``ParameterUse``; None if none yet."""
    found = parameter_at(obligation, name, anchor)
    if found is None:
        return None
    effective, pv = found
    if not isinstance(pv.value, int) or isinstance(pv.value, bool):
        raise ParameterError(f"{obligation.obligation_id}: {name!r} must be an integer")
    use = ParameterUse(
        name=name,
        value=pv.value,
        effective_date=effective,
        reference=pv.reference,
        verification=pv.verification,
    )
    return pv.value, use


@dataclass(frozen=True, slots=True)
class Duration:
    """A resolved clock duration, how it was derived, and what it read."""

    days: int
    rule: str
    parameters: tuple[ParameterUse, ...]
    facts_read: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class DurationUndecided:
    """No duration, the result that follows from that, and why."""

    reason: str
    result: DecisionResult
    parameters: tuple[ParameterUse, ...] = ()
    facts_read: tuple[str, ...] = ()


def resolve_duration(
    obligation: Obligation, facts: ComplaintFacts, anchor: date, start_name: str
) -> Duration | DurationUndecided:
    """Resolve the obligation's duration parameter at ``anchor`` (see the module docstring)."""
    names = [n for n in DURATION_PARAMETERS if n in obligation.parameters]
    if len(names) != 1:
        raise ParameterError(
            f"{obligation.obligation_id}: a clocked obligation needs exactly one of "
            f"{', '.join(DURATION_PARAMETERS)}; found {names or 'none'}"
        )
    (name,) = names
    found = int_parameter(obligation, name, anchor)
    if found is None:
        return DurationUndecided(
            f"no {name} in force on anchor date {anchor}", DecisionResult.NOT_APPLICABLE
        )
    n, use = found
    tat = facts.external_tat_days.value if facts.external_tat_days is not None else None
    read: tuple[str, ...] = () if tat is None else ("external_tat_days",)
    if name == "max_days":
        return Duration(n, f"{start_name} + {n}d", (use,))
    if name == "min_days":
        if tat is None or tat <= n:
            detail = "no external TAT" if tat is None else f"external TAT {tat}d <= {n}d"
            return Duration(n, f"{start_name} + {n}d ({detail})", (use,), read)
        return Duration(tat, f"{start_name} + {tat}d (external TAT > {n}d)", (use,), read)
    if tat is None:
        return DurationUndecided(
            "external_tat_days unknown: no external TAT applies",
            DecisionResult.NOT_TRIGGERED,
            (use,),
        )
    if tat < n:
        return DurationUndecided(
            f"external TAT {tat}d is shorter than {name} {n}d",
            DecisionResult.INSUFFICIENT_FACTS,
            (use,),
            read,
        )
    return Duration(tat - n, f"{start_name} + ({tat}d TAT - {n}d)", (use,), read)
