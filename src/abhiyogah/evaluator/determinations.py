"""Determinations and outputs: what an obligation determined, beyond a deadline.

The rule pack (``rules/obligations/_conventions.md``) names, per obligation, the outputs it
determines. The obligation schema has no field saying which building block computes them, so the
engine keys them by obligation ID here. Every number still comes from the obligation's parameters;
only the shape of the computation lives in code.

Two kinds:

- **Determinations** (``DETERMINATIONS``) replace the deadline step entirely and end ``DETERMINED``:
  routers (A1), checks of the complaint's state when the trigger fires (A14, A15, A18), and B5,
  whose clock only counts working days. A failed check has no ``Breach`` (a breach needs a due
  date); it shows as an output ``false`` plus a required action while it can still be fixed.
- **Clock outputs** (``CLOCK_OUTPUTS``) are read off a clocked obligation's final state (A2, A3, A6,
  A8) and are added to its ordinary result.

An obligation without an entry here behaves as before: no outputs, and a clockless one ends
``NOT_APPLICABLE`` with a trace line saying it has no building block.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date

from pydantic import JsonValue

from abhiyogah.calculators.errors import CalculatorError
from abhiyogah.calculators.limited_liability import customer_liability, delay_working_days
from abhiyogah.clocks import BankCalendar, ClockState
from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.decision import ConditionTrace, DecisionResult, ParameterUse
from abhiyogah.domain.enums import AccountType, LiabilityFault
from abhiyogah.evaluator.errors import ParameterError
from abhiyogah.evaluator.parameters import int_parameter, parameter_at
from abhiyogah.registry.schema import Obligation

__all__ = [
    "CLOCK_OUTPUTS",
    "DETERMINATIONS",
    "Determination",
    "DeterminationInput",
]


@dataclass(frozen=True, slots=True)
class DeterminationInput:
    """What a determination may read: the rule, the facts, its anchor date and the calendar."""

    obligation: Obligation
    facts: ComplaintFacts
    anchor: date
    calendar: BankCalendar
    home_state: str | None


@dataclass
class Determination:
    """A determination's result, outputs, action codes, trace and inputs read."""

    result: DecisionResult = DecisionResult.DETERMINED
    outputs: dict[str, JsonValue] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    trace: list[ConditionTrace] = field(default_factory=list)
    facts_read: list[str] = field(default_factory=list)
    parameters: list[ParameterUse] = field(default_factory=list)

    def check(self, condition: str, result: bool, detail: str = "") -> bool:
        """Add a trace line and return ``result``."""
        self.trace.append(ConditionTrace(condition=condition, result=result, detail=detail))
        return result

    def need(self, *names: str) -> None:
        """Record facts read."""
        self.facts_read.extend(n for n in names if n not in self.facts_read)

    def insufficient(self, fact: str, why: str = "needed by this check") -> "Determination":
        """End with ``INSUFFICIENT_FACTS`` for an unknown fact; nothing is assumed."""
        self.check(f"{fact} is known", False, why)
        self.result = DecisionResult.INSUFFICIENT_FACTS
        self.outputs = {}
        self.actions = []
        return self

    def not_applicable(self, why: str) -> "Determination":
        """End with ``NOT_APPLICABLE`` (e.g. no parameter in force on the anchor date)."""
        self.check("parameter in force on the anchor date", False, why)
        self.result = DecisionResult.NOT_APPLICABLE
        self.outputs = {}
        self.actions = []
        return self


def _use(obligation: Obligation, name: str, anchor: date) -> tuple[JsonValue, ParameterUse] | None:
    """Any parameter value in force on ``anchor`` and its ``ParameterUse``."""
    found = parameter_at(obligation, name, anchor)
    if found is None:
        return None
    effective, pv = found
    return pv.value, ParameterUse(
        name=name,
        value=pv.value,
        effective_date=effective,
        reference=pv.reference,
        verification=pv.verification,
    )


def _str_list(obligation: Obligation, name: str, value: JsonValue) -> list[str]:
    """A parameter that must be a list of strings."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ParameterError(f"{obligation.obligation_id}: {name} must be a list of strings")
    return [v for v in value if isinstance(v, str)]


def scheme_router(i: DeterminationInput) -> Determination:
    """A1: ``scheme`` is the ``scheme`` parameter in force on the anchor (RBI receipt) date."""
    det = Determination()
    found = _use(i.obligation, "scheme", i.anchor)
    if found is None:
        return det.not_applicable(f"no scheme in force on {i.anchor}")
    value, use = found
    det.parameters.append(use)
    det.outputs["scheme"] = value
    det.check("scheme in force on anchor date", True, f"{i.anchor}: {value}")
    return det


def outcome_classified(i: DeterminationInput) -> Determination:
    """A14: ``classified_at_closure`` = outcome set (and allowed) on or before the final reply."""
    det = Determination()
    found = _use(i.obligation, "allowed_outcomes", i.anchor)
    if found is None:
        return det.not_applicable(f"no allowed_outcomes in force on {i.anchor}")
    value, use = found
    det.parameters.append(use)
    allowed = _str_list(i.obligation, "allowed_outcomes", value)
    det.need("outcome", "outcome_date", "final_reply_date")
    f = i.facts
    if f.final_reply_date is None:
        return det.insufficient("final_reply_date")
    if f.outcome is None or f.outcome_date is None:
        det.check("outcome is set", False, "no outcome recorded")
        det.outputs["classified_at_closure"] = False
        det.actions.append("SET_OUTCOME")
        return det
    ok = f.outcome.value.value in allowed and f.outcome_date.value <= f.final_reply_date.value
    det.check(
        "outcome set by the final reply",
        ok,
        f"{f.outcome.value} on {f.outcome_date.value}, reply {f.final_reply_date.value}",
    )
    det.outputs["classified_at_closure"] = ok
    return det


def closure_unit(i: DeterminationInput) -> Determination:
    """A15 closure: ``closed_by_other_unit`` = closing unit differs from the handling unit."""
    det = Determination()
    det.need("handling_unit", "closing_unit")
    f = i.facts
    if f.handling_unit is None:
        return det.insufficient("handling_unit")
    if f.closing_unit is None:
        return det.insufficient("closing_unit")
    other = f.closing_unit.value != f.handling_unit.value
    det.check(
        "closing_unit != handling_unit",
        other,
        f"handled by {f.handling_unit.value}, closed by {f.closing_unit.value}",
    )
    det.outputs["closed_by_other_unit"] = other
    return det


def senior_review(i: DeterminationInput) -> Determination:
    """A15 review: reviewed at a senior level on or before the IO referral (if any)."""
    det = Determination()
    det.need("senior_review_date", "io_referred_date")
    f = i.facts
    reviewed = f.senior_review_date is not None and (
        f.io_referred_date is None or f.senior_review_date.value <= f.io_referred_date.value
    )
    det.check(
        "senior review on or before IO referral",
        reviewed,
        f"reviewed {f.senior_review_date.value if f.senior_review_date else 'never'}, "
        f"referred {f.io_referred_date.value if f.io_referred_date else 'not yet'}",
    )
    det.outputs["senior_reviewed_before_io"] = reviewed
    if not reviewed and f.io_referred_date is None:
        det.actions.append("SENIOR_REVIEW")
    return det


def reply_content(i: DeterminationInput) -> Determination:
    """A18: elements the reply must carry (more if the IO upheld it), and which are missing."""
    det = Determination()
    found = _use(i.obligation, "required_elements", i.anchor)
    if found is None:
        return det.not_applicable(f"no required_elements in force on {i.anchor}")
    value, use = found
    det.parameters.append(use)
    required = set(_str_list(i.obligation, "required_elements", value))
    det.need("reply_elements", "io_upheld")
    f = i.facts
    if f.io_upheld is not None and f.io_upheld.value:
        extra = _use(i.obligation, "required_elements_if_io_upheld", i.anchor)
        if extra is not None:
            det.parameters.append(extra[1])
            required |= set(_str_list(i.obligation, "required_elements_if_io_upheld", extra[0]))
    if f.reply_elements is None:
        return det.insufficient("reply_elements", "the sent reply's elements are not recorded")
    missing = sorted(required - set(f.reply_elements.value))
    det.check("reply carries every required element", not missing, ", ".join(missing) or "all")
    det.outputs["reply_complete"] = not missing
    missing_json: list[JsonValue] = list(missing)
    det.outputs["missing_elements"] = missing_json
    if missing:
        det.actions.append("SEND_CORRECTED_REPLY")
    return det


def liability(i: DeterminationInput) -> Determination:
    """B5: delay in working days (para 71), liability tier and the customer's liability."""
    det = Determination()
    ob = i.obligation
    det.need("alert_received_date", "customer_reported_date", "liability_fault")
    f = i.facts
    if f.alert_received_date is None:
        return det.insufficient("alert_received_date")
    if f.customer_reported_date is None:
        return det.insufficient("customer_reported_date")
    if f.liability_fault is None:
        return det.insufficient("liability_fault", "set only by a person (hard rule 4)")
    if not i.home_state:
        return det.insufficient("home_branch_state", "working days follow the home branch")
    det.need("home_branch_state")
    zero = int_parameter(ob, "zero_liability_max_working_days", i.anchor)
    limited = int_parameter(ob, "limited_liability_max_working_days", i.anchor)
    caps_found = _use(ob, "cap_paise_by_account_type", i.anchor)
    if zero is None or limited is None or caps_found is None:
        return det.not_applicable(f"liability parameters not all in force on {i.anchor}")
    det.parameters.extend([zero[1], limited[1], caps_found[1]])
    caps_raw = caps_found[0]
    if not isinstance(caps_raw, dict) or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in caps_raw.values()
    ):
        raise ParameterError(f"{ob.obligation_id}: cap_paise_by_account_type must map to integers")
    try:
        caps: Mapping[AccountType, int] = {
            AccountType(k): v for k, v in caps_raw.items() if isinstance(v, int)
        }
    except ValueError as exc:
        raise ParameterError(f"{ob.obligation_id}: unknown account type in caps") from exc
    delay = delay_working_days(
        i.calendar, f.alert_received_date.value, f.customer_reported_date.value, i.home_state
    )
    bank_fault = f.liability_fault.value is LiabilityFault.BANK
    det.check("bank at fault", bank_fault, f"liability_fault = {f.liability_fault.value}")
    det.outputs["delay_working_days"] = delay
    needs_amount = not bank_fault and zero[0] < delay <= limited[0]
    if needs_amount:
        det.need("account_type", "amount_paise")
        if f.account_type is None:
            return det.insufficient("account_type", "selects the liability cap")
        if f.amount_paise is None:
            return det.insufficient("amount_paise")
    account = f.account_type.value if f.account_type is not None else None
    amount = f.amount_paise.value if f.amount_paise is not None else None
    try:
        res = customer_liability(
            delay, amount, account, caps, zero[0], limited[0], bank_at_fault=bank_fault
        )
    except CalculatorError as exc:
        raise ParameterError(f"{ob.obligation_id}: {exc}") from exc
    det.check(f"liability tier {res.tier}", True, f"{res.reason}; {res.formula}")
    det.outputs["liability_tier"] = res.tier.value
    det.outputs["customer_liability_paise"] = (
        int(res.customer_liability_paise) if res.customer_liability_paise is not None else None
    )
    return det


DETERMINATIONS: dict[str, Callable[[DeterminationInput], Determination]] = {
    "RBIOS-2026-20-2": scheme_router,
    "IO-CB-2026-14-2": outcome_classified,
    "IO-CB-2026-14-3-4-closure": closure_unit,
    "IO-CB-2026-14-3-4-review": senior_review,
    "IO-CB-2026-14-11-12": reply_content,
    "RBCCB-2025-67-71": liability,
}
"""Obligation ID -> determination, per ``rules/obligations/_conventions.md``."""


def _lapsed(state: ClockState, facts: ComplaintFacts) -> dict[str, JsonValue]:
    """A2: escalation is open once the reply window lapsed or the complainant is dissatisfied."""
    late = state in (ClockState.BREACHED, ClockState.STOPPED_LATE)
    return {"escalation_open": late or facts.customer_dissatisfied_date is not None}


def _stopped_in_time(name: str) -> Callable[[ClockState, ComplaintFacts], dict[str, JsonValue]]:
    """A3, A8: ``name`` is true/false once the clock stopped; absent before."""

    def output(state: ClockState, facts: ComplaintFacts) -> dict[str, JsonValue]:
        if state is ClockState.STOPPED_ON_TIME:
            return {name: True}
        if state is ClockState.STOPPED_LATE:
            return {name: False}
        return {}

    return output


def _award_lapsed(state: ClockState, facts: ComplaintFacts) -> dict[str, JsonValue]:
    """A6: the award lapsed if not accepted within the window."""
    return {"award_lapsed": state in (ClockState.BREACHED, ClockState.STOPPED_LATE)}


CLOCK_OUTPUTS: dict[str, Callable[[ClockState, ComplaintFacts], dict[str, JsonValue]]] = {
    "RBIOS-2026-10-1-f": _lapsed,
    "RBIOS-2026-10-1-g": _stopped_in_time("filed_in_time"),
    "RBIOS-2026-15-4": _award_lapsed,
    "RBIOS-2026-17": _stopped_in_time("appeal_in_time"),
}
"""Obligation ID -> outputs read off its clock's final state."""
