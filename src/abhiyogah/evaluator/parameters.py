"""Dated parameter lookup and the clock-duration building blocks.

``parameter_at`` picks the value whose effective date is the latest on or before the anchor date
(the rule in ``rules/README.md``). It stands in for the registry resolver until the rule-pack stream
ships ``registry/resolve.py``.

A clocked obligation names its duration with exactly one of these parameters, as set out in
``rules/obligations/_conventions.md``. The numbers always come from the rule pack. ``s`` is the
clock's start date and ``TAT`` the ``external_tat_days`` fact.

``max_days``
    ``due = s + max_days`` (e.g. A13 ordinary limb, 20 days).
``base_days``
    ``due = s + max(base_days, TAT)``, or ``s + base_days`` when no external TAT is known
    (A2: "30 days, or RBI/NPCI/card-network TAT if higher").
``base_days`` + ``filing_window``
    ``due = max(s + max(base_days, TAT), last_bank_communication_date) + filing_window`` (A3).
    ``filing_window`` is ``{days: n}`` or ``{years: n}``; adding years keeps month and day. Calendar
    basis only.
``io_review_days``
    ``due = s + TAT - io_review_days`` (A13 cl. 14(1)(a), 10 days for IO review). Without a TAT the
    obligation is not triggered.
Optionally, ``stop_conditions`` maps a stop event to a condition (``evaluator.conditions``)
checked against that event's own payload, so only matching events stop the clock (A8 stops on an
``APPEAL_FILED`` with ``appellant`` = ``COMPLAINANT``, A7 on one with ``BANK``).

``tat_days_by_channel``
    ``due = s + table[channel]`` (B1, B2). An unknown channel, a channel missing from the table or a
    channel listed in ``follows_underlying_system`` gives ``INSUFFICIENT_FACTS``.
"""

from dataclasses import dataclass, field
from datetime import date

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.decision import DecisionResult, ParameterUse
from abhiyogah.domain.enums import DayBasis
from abhiyogah.domain.events import EventType
from abhiyogah.evaluator.errors import ParameterError
from abhiyogah.registry.schema import Obligation, ParameterValue

__all__ = [
    "DURATION_PARAMETERS",
    "FILING_WINDOW",
    "PER_DAY_PARAMETER",
    "STOP_CONDITIONS",
    "UNDERLYING_SYSTEM",
    "Duration",
    "DurationUndecided",
    "int_parameter",
    "parameter_at",
    "resolve_duration",
    "stop_conditions_at",
]

DURATION_PARAMETERS = ("max_days", "base_days", "io_review_days", "tat_days_by_channel")
UNDERLYING_SYSTEM = "follows_underlying_system"
STOP_CONDITIONS = "stop_conditions"
"""Optional parameter: ``{STOP_EVENT: condition}``; that stop counts only if its payload passes."""
FILING_WINDOW = "filing_window"

PER_DAY_PARAMETER = "compensation_per_day_paise"
"""Optional parameter: paise owed per calendar day late (e.g. B1 ₹100/day = 10000)."""


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


def _filing_window(obligation: Obligation, anchor: date) -> tuple[str, int, ParameterUse] | None:
    """The ``filing_window`` in force: (unit, amount, use), or None if none yet."""
    found = parameter_at(obligation, FILING_WINDOW, anchor)
    if found is None:
        return None
    effective, pv = found
    value = pv.value
    if (
        not isinstance(value, dict)
        or len(value) != 1
        or not set(value) <= {"days", "years"}
        or not isinstance(next(iter(value.values())), int)
        or isinstance(next(iter(value.values())), bool)
    ):
        raise ParameterError(
            f"{obligation.obligation_id}: filing_window must be {{days: n}} or {{years: n}}"
        )
    ((unit, amount),) = value.items()
    assert isinstance(amount, int)  # noqa: S101 - checked above
    use = ParameterUse(
        name=FILING_WINDOW,
        value=value,
        effective_date=effective,
        reference=pv.reference,
        verification=pv.verification,
    )
    return unit, amount, use


def stop_conditions_at(
    obligation: Obligation, anchor: date
) -> tuple[dict[EventType, str], ParameterUse] | None:
    """The ``stop_conditions`` in force on ``anchor``: stop event -> condition on its payload."""
    found = parameter_at(obligation, STOP_CONDITIONS, anchor)
    if found is None:
        return None
    effective, pv = found
    value = pv.value
    stops = obligation.clock.stop if obligation.clock is not None else []
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and k in stops and isinstance(v, str) for k, v in value.items()
    ):
        raise ParameterError(
            f"{obligation.obligation_id}: {STOP_CONDITIONS} must map the clock's stop events to "
            "condition strings"
        )
    use = ParameterUse(
        name=STOP_CONDITIONS,
        value=value,
        effective_date=effective,
        reference=pv.reference,
        verification=pv.verification,
    )
    return {EventType(k): v for k, v in value.items() if isinstance(v, str)}, use


def _channel_duration(
    obligation: Obligation, facts: ComplaintFacts, anchor: date, start_name: str
) -> Duration | DurationUndecided:
    """``tat_days_by_channel``: the TAT for the complaint's channel (B1, B2)."""
    name = "tat_days_by_channel"
    found = parameter_at(obligation, name, anchor)
    if found is None:
        return DurationUndecided(
            f"no {name} in force on anchor date {anchor}", DecisionResult.NOT_APPLICABLE
        )
    effective, pv = found
    table = pv.value
    if not isinstance(table, dict) or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in table.values()
    ):
        raise ParameterError(f"{obligation.obligation_id}: {name} must map channels to integers")
    if facts.channel is None:
        return DurationUndecided("channel unknown", DecisionResult.INSUFFICIENT_FACTS)
    channel = facts.channel.value.value
    read = ("channel",)
    if UNDERLYING_SYSTEM in obligation.parameters:
        underlying = parameter_at(obligation, UNDERLYING_SYSTEM, anchor)
        if (
            underlying is not None
            and isinstance(underlying[1].value, list)
            and channel in underlying[1].value
        ):
            return DurationUndecided(
                f"{channel} follows the underlying system, which is not known",
                DecisionResult.INSUFFICIENT_FACTS,
                facts_read=read,
            )
    days = table.get(channel)
    if days is None:
        return DurationUndecided(
            f"{channel} is not in this obligation's {name}",
            DecisionResult.INSUFFICIENT_FACTS,
            facts_read=read,
        )
    assert isinstance(days, int)  # noqa: S101 - checked above
    use = ParameterUse(
        name=f"{name}.{channel}",
        value=days,
        effective_date=effective,
        reference=pv.reference,
        verification=pv.verification,
    )
    return Duration(days, f"{start_name} + {days}d ({channel})", (use,), read)


def resolve_duration(
    obligation: Obligation, facts: ComplaintFacts, anchor: date, start: date, start_name: str
) -> Duration | DurationUndecided:
    """Resolve the obligation's duration at ``anchor`` for a clock starting on ``start``."""
    names = [n for n in DURATION_PARAMETERS if n in obligation.parameters]
    if len(names) != 1:
        raise ParameterError(
            f"{obligation.obligation_id}: a clocked obligation needs exactly one of "
            f"{', '.join(DURATION_PARAMETERS)}; found {names or 'none'}"
        )
    (name,) = names
    has_window = FILING_WINDOW in obligation.parameters
    if has_window and name != "base_days":
        raise ParameterError(f"{obligation.obligation_id}: filing_window needs base_days")
    if name == "tat_days_by_channel":
        return _channel_duration(obligation, facts, anchor, start_name)
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
    if name == "io_review_days":
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
    days = n if tat is None else max(n, tat)
    base_rule = (
        f"{start_name} + max({n}d, {tat}d TAT)" if tat is not None else f"{start_name} + {n}d"
    )
    if not has_window:
        return Duration(days, base_rule, (use,), read)
    if obligation.clock is None or obligation.clock.basis is not DayBasis.CALENDAR:
        raise ParameterError(f"{obligation.obligation_id}: filing_window needs a calendar clock")
    window = _filing_window(obligation, anchor)
    if window is None:
        return DurationUndecided(
            f"no {FILING_WINDOW} in force on anchor date {anchor}",
            DecisionResult.NOT_APPLICABLE,
            (use,),
            read,
        )
    unit, amount, wuse = window
    base_end = date.fromordinal(start.toordinal() + days)
    rule = f"max({base_rule}"
    if facts.last_bank_communication_date is not None:
        read = (*read, "last_bank_communication_date")
        base_end = max(base_end, facts.last_bank_communication_date.value)
        rule += ", last_bank_communication_date"
    rule += f") + {amount} {unit}"
    if unit == "days":
        due = date.fromordinal(base_end.toordinal() + amount)
    else:
        try:
            due = base_end.replace(year=base_end.year + amount)
        except ValueError:
            return DurationUndecided(
                f"no rule for adding {amount} years to {base_end}",
                DecisionResult.INSUFFICIENT_FACTS,
                (use, wuse),
                read,
            )
    return Duration((due - start).days, rule, (use, wuse), read)
