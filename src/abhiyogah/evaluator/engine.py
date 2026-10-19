"""``evaluate``: run obligations over one complaint's events and produce decision records.

A pure function of its arguments. It reads no clock, file, database or network; ``as_of`` is
required, so the same inputs always give byte-identical records (replay) and tests can time-travel.

The semantics follow ``rules/obligations/_conventions.md`` (rule-pack stream). For each
obligation, in this order, every step leaving a ``ConditionTrace`` line:

1. **Applicability.** A ``FUTURE_DATED`` rule is never evaluated (B10's draft figures stay
   blocked until the owner changes its status). The entity type (the complaint's
   ``entity_type`` fact, else the profile) is bound by ``applies_to``; the outlet count meets
   ``min_outlets`` as on ``outlets_as_on``; the ``as_of`` date is within ``valid_from`` to
   ``valid_to``. Otherwise ``NOT_APPLICABLE`` (``INSUFFICIENT_FACTS`` if outlets are unknown).
2. **Trigger.** The trigger event has occurred by ``as_of`` and the trigger condition holds
   (``evaluator.conditions``). Otherwise ``NOT_TRIGGERED``.
3. **Anchor.** Parameters are resolved at the anchor date: the ``anchor`` fact, else the clock
   start. When the anchor fact is unknown and it is one of the clock's own stop facts (A3: RBI
   receipt), the ``as_of`` date stands in ("if it stopped now"); any other unknown anchor gives
   ``INSUFFICIENT_FACTS``.
4. **Clock.** The duration parameter (``evaluator.parameters``) and the clock spec build a ``Clock``
   (``abhiyogah.clocks``). A missing fact gives ``INSUFFICIENT_FACTS``; nothing is assumed.
5. **Overrides.** ``overridden_by`` is resolved to one deadline (``clocks.overrides``). The
   overriding obligation reports the deadline; the overridden one reports
   ``NOT_APPLICABLE`` with the reason.
6. **State.** The clock state at ``as_of`` gives the result, any breach, and the required actions.
   A ``PERMISSION`` (a complainant's right, such as A2 and A3) never produces a breach, a required
   action or compensation; its result only says whether the window has lapsed.
7. **Compensation.** If the obligation has a ``compensation_per_day_paise`` parameter, a breached or
   late clock owes that amount per calendar day late (``calculators.per_day_compensation``).

Obligations without a clock stop after step 2 with ``NOT_APPLICABLE`` and a trace line saying so;
they are enforced by the workflow gates, not by deadlines.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from pydantic import JsonValue

from abhiyogah.calculators import per_day_compensation
from abhiyogah.clocks import (
    BankCalendar,
    Clock,
    ClockError,
    ClockState,
    DeadlineCandidate,
    MissingFactError,
    NotApplied,
    build_clock,
    pauses_from_events,
    resolve_overrides,
    start_fact_name,
    stop_fact_names,
)
from abhiyogah.domain.complaint import ComplaintFacts, Fact, fold_events
from abhiyogah.domain.decision import (
    Breach,
    Compensation,
    ConditionTrace,
    Deadline,
    DecisionRecord,
    DecisionResult,
    InputFact,
    ParameterUse,
    RequiredAction,
)
from abhiyogah.domain.enums import Deontic, EntityType, FactSource, RuleStatus
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance
from abhiyogah.domain.tz import ist_date
from abhiyogah.evaluator.actions import action_code
from abhiyogah.evaluator.conditions import evaluate_condition, fact_spelling
from abhiyogah.evaluator.errors import EvaluationError
from abhiyogah.evaluator.parameters import (
    PER_DAY_PARAMETER,
    STOP_CONDITIONS,
    DurationUndecided,
    int_parameter,
    resolve_duration,
    stop_conditions_at,
)
from abhiyogah.evaluator.profile import EntityProfile
from abhiyogah.registry.schema import Obligation

__all__ = ["evaluate", "obligation_version"]

PROFILE_PROVENANCE = Provenance(source=FactSource.SYSTEM, actor="entity_profile")
"""Provenance of inputs taken from the ``EntityProfile`` rather than from complaint events."""


def obligation_version(obligation: Obligation) -> str:
    """SHA-256 of the obligation's canonical JSON; changes whenever any field changes."""
    data = json.dumps(
        obligation.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass
class _Draft:
    """A record under construction for one obligation."""

    obligation: Obligation
    trace: list[ConditionTrace] = field(default_factory=list)
    fact_names: list[str] = field(default_factory=list)
    profile_inputs: dict[str, JsonValue] = field(default_factory=dict)
    parameters: list[ParameterUse] = field(default_factory=list)
    anchor_date: date | None = None
    result: DecisionResult | None = None
    candidate: DeadlineCandidate | None = None
    per_day_paise: int | None = None
    stop_event: EventType | None = None
    """The event that stopped the clock, when a filtered stop chose it."""

    def check(self, condition: str, result: bool, detail: str = "") -> bool:
        """Add a trace line and return ``result``."""
        self.trace.append(ConditionTrace(condition=condition, result=result, detail=detail))
        return result

    def read(self, *names: str) -> None:
        """Note complaint facts this evaluation read."""
        self.fact_names.extend(n for n in names if n not in self.fact_names)

    def stop(self, result: DecisionResult) -> None:
        """Finish with a result and no deadline."""
        self.result = result


def _check_applicability(d: _Draft, facts: ComplaintFacts, profile: EntityProfile) -> bool:
    """Step 1: status, entity type and outlet threshold."""
    if d.obligation.status is RuleStatus.FUTURE_DATED:
        d.check("status is not FUTURE_DATED", False, "future-dated rules are never evaluated")
        d.stop(DecisionResult.NOT_APPLICABLE)
        return False
    applies = d.obligation.applies_to
    if facts.entity_type is not None:
        entity: EntityType = facts.entity_type.value
        d.read("entity_type")
    else:
        entity = profile.entity_type
        d.profile_inputs["entity_type"] = entity.value
    allowed = [e.value for e in applies.entity_types()]
    if not d.check(f"entity_type in {allowed}", entity.value in allowed, f"entity_type = {entity}"):
        d.stop(DecisionResult.NOT_APPLICABLE)
        return False
    if applies.min_outlets is None:
        return True
    cond = f"outlets >= {applies.min_outlets}"
    if applies.outlets_as_on is not None:
        cond += f" as on {applies.outlets_as_on}"
    if profile.outlets is None or (
        applies.outlets_as_on is not None and profile.outlets_as_on != applies.outlets_as_on
    ):
        d.check(cond, False, f"outlet count as on {applies.outlets_as_on} unknown")
        d.stop(DecisionResult.INSUFFICIENT_FACTS)
        return False
    d.profile_inputs["outlets"] = profile.outlets
    if profile.outlets_as_on is not None:
        d.profile_inputs["outlets_as_on"] = profile.outlets_as_on.isoformat()
    if not d.check(cond, profile.outlets >= applies.min_outlets, f"outlets = {profile.outlets}"):
        d.stop(DecisionResult.NOT_APPLICABLE)
        return False
    return True


def _check_validity(d: _Draft, day: date) -> bool:
    """Step 1 (cont.): is this version of the rule in the pack on the ``as_of`` date?"""
    ob = d.obligation
    valid_to = ob.valid_to.isoformat() if ob.valid_to is not None else "open"
    in_force = ob.valid_from <= day and (ob.valid_to is None or day <= ob.valid_to)
    if not d.check(f"{ob.valid_from} <= as_of <= {valid_to}", in_force, f"as_of = {day}"):
        d.stop(DecisionResult.NOT_APPLICABLE)
        return False
    return True


def _check_trigger(d: _Draft, facts: ComplaintFacts, events: Sequence[ComplaintEvent]) -> bool:
    """Step 2: trigger event and condition."""
    trigger = d.obligation.trigger
    hits = [e for e in events if e.type is trigger.event]
    detail = f"first on {min(ist_date(e.occurred_at) for e in hits)}" if hits else "not yet"
    if not d.check(f"event {trigger.event} occurred", bool(hits), detail):
        d.stop(DecisionResult.NOT_TRIGGERED)
        return False
    outcome = evaluate_condition(trigger.condition, facts)
    d.trace.extend(outcome.trace)
    d.read(*outcome.facts_read)
    if not outcome.result:
        d.stop(DecisionResult.NOT_TRIGGERED)
        return False
    return True


def _date_fact(facts: ComplaintFacts, name: str) -> Fact[date] | None:
    """Read a date fact by field name."""
    value: Fact[date] | None = getattr(facts, name)
    return value


def _build_candidate(
    d: _Draft,
    facts: ComplaintFacts,
    events: Sequence[ComplaintEvent],
    calendar: BankCalendar,
    profile: EntityProfile,
    day: date,
) -> None:
    """Steps 3 and 4: anchor, duration and clock."""
    ob = d.obligation
    spec = ob.clock
    if spec is None:
        d.check("obligation has a clock", False, "no deadline; enforced by workflow gates")
        d.stop(DecisionResult.NOT_APPLICABLE)
        return
    start_name = start_fact_name(spec)
    start = _date_fact(facts, start_name)
    d.read(start_name)
    if start is None:
        d.check(f"{start_name} is known", False, "clock start unknown")
        d.stop(DecisionResult.INSUFFICIENT_FACTS)
        return
    anchor_name = ob.anchor or start_name
    anchor_fact = _date_fact(facts, anchor_name)
    d.read(anchor_name)
    if anchor_fact is not None:
        anchor = anchor_fact.value
    elif anchor_name in stop_fact_names(spec):
        anchor = day
        d.check(f"{anchor_name} is known", False, f"not yet: as_of {day} stands in")
    else:
        d.check(f"{anchor_name} is known", False, "anchor date unknown")
        d.stop(DecisionResult.INSUFFICIENT_FACTS)
        return
    d.anchor_date = anchor
    duration = resolve_duration(ob, facts, anchor, start.value, start_name)
    d.parameters.extend(duration.parameters)
    d.read(*duration.facts_read)
    if isinstance(duration, DurationUndecided):
        d.check("duration resolved", False, duration.reason)
        d.stop(duration.result)
        return
    d.check("duration resolved", True, duration.rule)
    if PER_DAY_PARAMETER in ob.parameters:
        per_day = int_parameter(ob, PER_DAY_PARAMETER, anchor)
        if per_day is None:
            d.check(f"{PER_DAY_PARAMETER} in force", False, f"none on {anchor}")
            d.stop(DecisionResult.NOT_APPLICABLE)
            return
        d.per_day_paise, use = per_day
        d.parameters.append(use)
    pauses = pauses_from_events(spec.pause, events) if spec.pause is not None else []
    d.read(start_name, *stop_fact_names(spec))
    if facts.home_branch_state is not None:
        d.read("home_branch_state")
    elif profile.home_branch_state is not None:
        d.profile_inputs["home_branch_state"] = profile.home_branch_state
    try:
        clock = build_clock(
            spec, facts, duration.days, calendar, pauses, default_state=profile.home_branch_state
        )
    except MissingFactError as exc:
        d.check(f"{exc.fact} is known", False, "needed by the clock")
        d.stop(DecisionResult.INSUFFICIENT_FACTS)
        return
    except ClockError as exc:
        d.check("clock facts are consistent", False, str(exc))
        d.stop(DecisionResult.INSUFFICIENT_FACTS)
        return
    if STOP_CONDITIONS in ob.parameters:
        ok, filtered = _filtered_stop(d, facts, events, anchor)
        if not ok:
            return
        try:
            clock = replace(clock, stop_date=filtered)
        except ClockError as exc:
            d.check("clock facts are consistent", False, str(exc))
            d.stop(DecisionResult.INSUFFICIENT_FACTS)
            return
    d.candidate = DeadlineCandidate(ob.obligation_id, clock, duration.rule)


def _filtered_stop(
    d: _Draft, facts: ComplaintFacts, events: Sequence[ComplaintEvent], anchor: date
) -> tuple[bool, date | None]:
    """The stop date when some stop events must pass a condition on their own payload.

    Returns ``(False, None)`` and finishes the draft when no ``stop_conditions`` are in force;
    otherwise ``(True, earliest qualifying stop)``, or ``(True, None)`` if nothing stopped it yet.
    """
    ob = d.obligation
    spec = ob.clock
    assert spec is not None  # noqa: S101 - only called for clocked obligations
    found = stop_conditions_at(ob, anchor)
    if found is None:
        d.check(f"{STOP_CONDITIONS} in force", False, f"none on {anchor}")
        d.stop(DecisionResult.NOT_APPLICABLE)
        return False, None
    conditions, use = found
    d.parameters.append(use)
    best: tuple[date, EventType] | None = None
    for ev_type, fact_name in zip(spec.stop, stop_fact_names(spec), strict=True):
        cond = conditions.get(ev_type)
        if cond is None:
            fact = _date_fact(facts, fact_name)
            candidates = [] if fact is None else [fact.value]
        else:
            candidates = []
            for e in sorted(events, key=lambda e: (e.occurred_at, e.event_id)):
                if e.type is not ev_type:
                    continue
                own = fold_events(e.complaint_id, [e])
                outcome = evaluate_condition(cond, own)
                d.check(
                    f"{e.event_id} {ev_type} stops the clock: {cond}",
                    outcome.result,
                    "; ".join(t.detail for t in outcome.trace),
                )
                if outcome.result:
                    candidates.append(ist_date(e.occurred_at))
        for when in candidates:
            if best is None or when < best[0]:
                best = (when, ev_type)
    if best is None:
        return True, None
    d.stop_event = best[1]
    return True, best[0]


def _resolve(drafts: dict[str, _Draft], day: date) -> None:
    """Step 5: resolve each obligation's ``overridden_by`` list."""
    for oid in sorted(drafts):
        d = drafts[oid]
        if d.candidate is None or not d.obligation.overridden_by:
            continue
        items: list[DeadlineCandidate | NotApplied] = []
        for other_id in d.obligation.overridden_by:
            other = drafts.get(other_id)
            if other is None:
                raise EvaluationError(f"{oid}: overridden_by names {other_id}, which is not loaded")
            if other.candidate is not None:
                items.append(other.candidate)
            else:
                last = other.trace[-1].detail if other.trace else ""
                items.append(NotApplied(other_id, f"{other.result}: {last}".rstrip(": ")))
        res = resolve_overrides(d.candidate, items, day)
        d.trace.extend(res.trace)
        if res.overridden:
            winner = drafts[res.chosen.obligation_id]
            applied = next(t for t in res.trace if t.result)
            winner.check(f"replaces {oid}", True, applied.detail)
            d.candidate = None
            d.stop(DecisionResult.NOT_APPLICABLE)


def _event_type_of(fact: Fact[date] | None, events: Sequence[ComplaintEvent]) -> EventType | None:
    """The type of the event that asserted ``fact``."""
    if fact is None:
        return None
    return next((e.type for e in events if e.event_id == fact.event_id), None)


def _finish(
    d: _Draft, facts: ComplaintFacts, events: Sequence[ComplaintEvent], day: date
) -> tuple[Deadline | None, Breach | None, list[RequiredAction], Compensation | None]:
    """Steps 6 and 7: state, deadline, breach, required actions and compensation."""
    if d.candidate is None:
        return None, None, [], None
    ob = d.obligation
    spec = ob.clock
    assert spec is not None  # noqa: S101 - a candidate exists only for clocked obligations
    clock: Clock = d.candidate.clock
    state = clock.state(day)
    due = clock.due_date(day)
    stop = clock.stop_known(day)
    d.result = DecisionResult(state.value)
    start_type = (
        spec.start
        if isinstance(spec.start, EventType)
        else _event_type_of(_date_fact(facts, spec.start), events)
    )
    if start_type is None:
        raise EvaluationError(f"{ob.obligation_id}: cannot find the event behind the clock start")
    stop_type: EventType | None = spec.stop[0] if spec.stop else None
    if stop is not None and d.stop_event is not None:
        stop_type = d.stop_event
    elif stop is not None:
        for ev, name in zip(spec.stop, stop_fact_names(spec), strict=True):
            f = _date_fact(facts, name)
            if f is not None and f.value == stop:
                stop_type = ev
                break
    deadline = Deadline(
        due_date=due,
        basis=clock.basis,
        basis_status=clock.basis_status,
        start_event=start_type,
        stop_event=stop_type,
        start_date=clock.start_date,
        duration_days=clock.duration_days,
        rule=d.candidate.rule,
    )
    d.check(
        f"stopped by {due}" if stop is not None else f"{day} <= {due} or stopped",
        state in (ClockState.STOPPED_ON_TIME, ClockState.RUNNING),
        f"state {state}" + (f", stopped {stop}" if stop is not None else ""),
    )
    permission = ob.deontic is Deontic.PERMISSION
    breach = None
    if not permission and spec.stop and state in (ClockState.BREACHED, ClockState.STOPPED_LATE):
        breach = Breach(
            obligation_id=ob.obligation_id,
            due_date=due,
            stop_date=stop if state is ClockState.STOPPED_LATE else None,
            days_late=clock.days_late(day),
        )
    actions: list[RequiredAction] = []
    if not permission and state in (ClockState.RUNNING, ClockState.BREACHED):
        actions = [
            RequiredAction(
                action=action_code(spec.stop[0]),
                due_date=due,
                reason=f"{ob.clause}: clock {state}",
            )
        ]
    compensation = None
    if d.per_day_paise is not None and breach is not None:
        compensation = per_day_compensation(
            d.per_day_paise,
            breach.days_late,
            f"{PER_DAY_PARAMETER} x days late past {d.candidate.rule}",
            {"due_date": due.isoformat(), "end_date": (stop or day).isoformat()},
        )
    return deadline, breach, actions, compensation


def _input_facts(d: _Draft, facts: ComplaintFacts) -> list[InputFact]:
    """The facts read, with provenance, then the profile inputs."""
    out: list[InputFact] = []
    for name in d.fact_names:
        fact: Fact[object] | None = getattr(facts, name)
        if fact is None:
            continue
        out.append(
            InputFact(
                name=name,
                value=fact_spelling(fact.value) if not isinstance(fact.value, int) else fact.value,
                provenance=fact.provenance,
                event_id=fact.event_id,
            )
        )
    for name in sorted(d.profile_inputs):
        out.append(
            InputFact(
                name=f"profile.{name}",
                value=d.profile_inputs[name],
                provenance=PROFILE_PROVENANCE,
            )
        )
    return out


def evaluate(
    complaint_events: Sequence[ComplaintEvent],
    obligations: Sequence[Obligation],
    calendar: BankCalendar,
    as_of: datetime,
    *,
    profile: EntityProfile,
    complaint_id: str | None = None,
) -> list[DecisionRecord]:
    """Evaluate every obligation on one complaint at ``as_of``; one unsealed record each, by ID.

    Only events that occurred and were recorded by ``as_of`` count. ``complaint_id`` is required
    when there are no events. See the module docstring for the steps.
    """
    day = ist_date(as_of)
    ids = {e.complaint_id for e in complaint_events}
    if complaint_id is None:
        if len(ids) != 1:
            raise EvaluationError("complaint_id is needed when events are empty or mixed")
        complaint_id = next(iter(ids))
    seen = [e for e in complaint_events if e.recorded_at <= as_of and e.occurred_at <= as_of]
    facts = fold_events(complaint_id, seen)
    by_id: dict[str, _Draft] = {}
    for ob in obligations:
        if ob.obligation_id in by_id:
            raise EvaluationError(f"duplicate obligation {ob.obligation_id}")
        by_id[ob.obligation_id] = _Draft(ob)
    for d in by_id.values():
        if (
            _check_applicability(d, facts, profile)
            and _check_validity(d, day)
            and _check_trigger(d, facts, seen)
        ):
            _build_candidate(d, facts, seen, calendar, profile, day)
    _resolve(by_id, day)
    records = []
    for oid in sorted(by_id):
        d = by_id[oid]
        deadline, breach, actions, compensation = _finish(d, facts, seen, day)
        assert d.result is not None  # noqa: S101 - every path sets a result
        records.append(
            DecisionRecord(
                complaint_id=complaint_id,
                obligation_id=oid,
                obligation_version=obligation_version(d.obligation),
                clause=d.obligation.clause,
                anchor_date=d.anchor_date,
                as_of=as_of,
                input_facts=_input_facts(d, facts),
                parameters=d.parameters,
                condition_trace=d.trace,
                deadline=deadline,
                calendar_version=calendar.version,
                result=d.result,
                breach=breach,
                compensation=compensation,
                required_actions=actions,
            )
        )
    return records
