"""Dated parameter resolution, OpenFisca-style.

A parameter is a history of values keyed by effective date. The value in force on an anchor date is
the one with the latest effective date on or before it. There is no fallback to a later value: a
date before the first effective date has no value in force.
"""

from datetime import date

from abhiyogah.registry.errors import NoParameterInForce, UnknownParameterError
from abhiyogah.registry.schema import Obligation, ParameterValue

__all__ = ["parameter_at"]


def parameter_at(obligation: Obligation, name: str, anchor_date: date) -> ParameterValue:
    """The value of ``name`` in force on ``anchor_date`` (latest effective date ≤ anchor)."""
    history = obligation.parameters.get(name)
    if history is None:
        raise UnknownParameterError(f"{obligation.obligation_id} has no parameter {name!r}")
    effective = [d for d in history if d <= anchor_date]
    if not effective:
        first = min(history)
        raise NoParameterInForce(
            f"{obligation.obligation_id}.{name}: no value in force on {anchor_date.isoformat()} "
            f"(first effective date {first.isoformat()})"
        )
    return history[max(effective)]
