"""The evaluator: applicability, trigger, validity, clock, overrides and the trace."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import JsonValue

from abhiyogah.domain.decision import DecisionRecord, DecisionResult
from abhiyogah.domain.enums import EntityType, FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance
from abhiyogah.domain.tz import IST
from abhiyogah.evaluator import EntityProfile, EvaluationError, evaluate
from abhiyogah.registry.schema import Obligation
from tests.clocks.fakes import FakeCalendar
from tests.evaluator.builders import obligation, ordinary_limb, tat_limb

CAL = FakeCalendar()
PROFILE = EntityProfile(
    entity_type=EntityType.COMMERCIAL_BANK,
    outlets=120,
    outlets_as_on=date(2025, 3, 31),
    home_branch_state="MH",
)
SYSTEM = Provenance(source=FactSource.SYSTEM, actor="cbs-feed")


def at(d: date, hour: int = 11) -> datetime:
    """An IST instant on ``d``."""
    return datetime(d.year, d.month, d.day, hour, tzinfo=IST)


def ev(
    n: int, type_: EventType, d: date, payload: dict[str, JsonValue] | None = None
) -> ComplaintEvent:
    """A synthetic event on complaint CMP-1, recorded a minute after it occurred."""
    occurred = at(d)
    return ComplaintEvent(
        event_id=f"EV-{n}",
        complaint_id="CMP-1",
        type=type_,
        occurred_at=occurred,
        recorded_at=occurred + timedelta(minutes=1),
        payload=payload or {},
        provenance=SYSTEM,
    )


RECEIVED = ev(1, EventType.BANK_RECEIVED, date(2026, 8, 3))
REJECTED = ev(2, EventType.OUTCOME_SET, date(2026, 8, 10), {"outcome": "WHOLLY_REJECTED"})


def one(
    events: list[ComplaintEvent],
    as_of: date,
    obligations: list[Obligation] | None = None,
    profile: EntityProfile = PROFILE,
    oid: str = "IO-CB-2026-14-1-b",
) -> DecisionRecord:
    """Evaluate and return the record for ``oid``."""
    records = evaluate(events, obligations or [obligation()], CAL, at(as_of, 18), profile=profile)
    return next(r for r in records if r.obligation_id == oid)


def test_example_scenario_breached() -> None:
    """Receipt 3 Aug + 20d = 23 Aug; no referral by 25 Aug: breached, 2 days late."""
    rec = one([RECEIVED, REJECTED], date(2026, 8, 25))
    assert rec.result is DecisionResult.BREACHED
    assert rec.deadline is not None
    assert rec.deadline.due_date == date(2026, 8, 23)
    assert rec.deadline.start_event is EventType.BANK_RECEIVED
    assert rec.deadline.stop_event is EventType.IO_REFERRED
    assert rec.breach is not None
    assert rec.breach.days_late == 2
    assert [a.action for a in rec.required_actions] == ["REFER_TO_IO"]
    assert rec.anchor_date == date(2026, 8, 3)
    assert rec.calendar_version == "fake-calendar-1"
    assert [p.name for p in rec.parameters] == ["max_days"]
    assert {f.name for f in rec.input_facts} >= {"outcome", "bank_receipt_date"}
    assert all(t.result for t in rec.condition_trace[:-1])


def test_running_then_stopped_on_time() -> None:
    """Running before the due date; a referral on day 18 stops it on time with no action."""
    assert one([RECEIVED, REJECTED], date(2026, 8, 12)).result is DecisionResult.RUNNING
    referred = ev(3, EventType.IO_REFERRED, date(2026, 8, 21))
    rec = one([RECEIVED, REJECTED, referred], date(2026, 8, 30))
    assert rec.result is DecisionResult.STOPPED_ON_TIME
    assert rec.breach is None
    assert rec.required_actions == []


def test_stopped_late() -> None:
    """A referral on 26 Aug is 3 days late."""
    referred = ev(3, EventType.IO_REFERRED, date(2026, 8, 26))
    rec = one([RECEIVED, REJECTED, referred], date(2026, 8, 30))
    assert rec.result is DecisionResult.STOPPED_LATE
    assert rec.breach is not None
    assert rec.breach.stop_date == date(2026, 8, 26)
    assert rec.breach.days_late == 3


def test_fully_resolved_not_triggered() -> None:
    """A fully resolved complaint is not escalated."""
    resolved = ev(2, EventType.OUTCOME_SET, date(2026, 8, 10), {"outcome": "FULLY_RESOLVED"})
    rec = one([RECEIVED, resolved], date(2026, 8, 30))
    assert rec.result is DecisionResult.NOT_TRIGGERED
    assert rec.deadline is None


def test_no_outcome_yet_not_triggered() -> None:
    """Without the trigger event the obligation has not bitten."""
    assert one([RECEIVED], date(2026, 8, 30)).result is DecisionResult.NOT_TRIGGERED


def test_wrong_entity_type_not_applicable() -> None:
    """An NBFC is not bound by the commercial-bank IO Directions."""
    nbfc = PROFILE.model_copy(update={"entity_type": EntityType.NBFC})
    rec = one([RECEIVED, REJECTED], date(2026, 8, 30), profile=nbfc)
    assert rec.result is DecisionResult.NOT_APPLICABLE


def test_outlets_below_threshold_or_unknown() -> None:
    """Fewer outlets: not applicable. Unknown count: insufficient facts, nothing assumed."""
    small = PROFILE.model_copy(update={"outlets": 5})
    assert one([RECEIVED, REJECTED], date(2026, 8, 30), profile=small).result is (
        DecisionResult.NOT_APPLICABLE
    )
    unknown = PROFILE.model_copy(update={"outlets": None})
    assert one([RECEIVED, REJECTED], date(2026, 8, 30), profile=unknown).result is (
        DecisionResult.INSUFFICIENT_FACTS
    )


def test_missing_receipt_is_insufficient_facts() -> None:
    """No bank receipt date: the clock cannot start."""
    rec = one([REJECTED], date(2026, 8, 30))
    assert rec.result is DecisionResult.INSUFFICIENT_FACTS
    assert rec.condition_trace[-1].result is False


def test_missing_outcome_value_is_insufficient() -> None:
    """A condition on an unknown fact cannot be decided."""
    ob = obligation(trigger={"event": "BANK_RECEIVED", "condition": "outcome in [WHOLLY_REJECTED]"})
    assert one([RECEIVED], date(2026, 8, 30), [ob]).result is DecisionResult.INSUFFICIENT_FACTS


def test_receipt_before_valid_from_not_applicable() -> None:
    """A complaint received before the Directions took effect is outside this version."""
    early = ev(1, EventType.BANK_RECEIVED, date(2026, 1, 5))
    rec = one([early, REJECTED], date(2026, 8, 30))
    assert rec.result is DecisionResult.NOT_APPLICABLE
    assert rec.anchor_date == date(2026, 1, 5)


def test_parameter_version_selected_by_anchor() -> None:
    """The value in force on the anchor date is used, not the latest one."""
    params = {
        "max_days": {
            "2026-01-14": {"value": 20, "reference": "a", "verification": "PRIMARY_TEXT_READ"},
            "2026-09-01": {"value": 15, "reference": "b", "verification": "UNVERIFIED"},
        }
    }
    rec = one([RECEIVED, REJECTED], date(2026, 8, 25), [obligation(parameters=params)])
    assert rec.deadline is not None
    assert rec.deadline.due_date == date(2026, 8, 23)
    assert rec.parameters[0].effective_date == date(2026, 1, 14)


def test_events_after_as_of_are_ignored() -> None:
    """A referral recorded after as_of is not yet known: the replay shows a breach."""
    referred = ev(3, EventType.IO_REFERRED, date(2026, 8, 27))
    rec = one([RECEIVED, REJECTED, referred], date(2026, 8, 25))
    assert rec.result is DecisionResult.BREACHED


def test_tat_override_replaces_20_days() -> None:
    """With a 25-day external TAT, TAT - 10 = 15 days: due 18 Aug, reported by the 14(1)(a) limb."""
    tat = ev(3, EventType.FACTS_RECORDED, date(2026, 8, 3), {"external_tat_days": 25})
    obs = [ordinary_limb(), tat_limb()]
    base = one([RECEIVED, REJECTED, tat], date(2026, 8, 20), obs)
    assert base.result is DecisionResult.NOT_APPLICABLE
    assert base.deadline is None
    assert any("IO-CB-2026-14-1-a" in t.condition and t.result for t in base.condition_trace)
    limb = one([RECEIVED, REJECTED, tat], date(2026, 8, 20), obs, oid="IO-CB-2026-14-1-a")
    assert limb.result is DecisionResult.BREACHED
    assert limb.deadline is not None
    assert limb.deadline.due_date == date(2026, 8, 18)
    assert limb.condition_trace[-2].condition == "replaces IO-CB-2026-14-1-b"


def test_no_tat_keeps_20_days() -> None:
    """Without an external TAT the TAT limb is not triggered and 20 days stands."""
    obs = [ordinary_limb(), tat_limb()]
    base = one([RECEIVED, REJECTED], date(2026, 8, 25), obs)
    assert base.result is DecisionResult.BREACHED
    assert any("IO-CB-2026-14-1-a" in t.condition and not t.result for t in base.condition_trace)
    limb = one([RECEIVED, REJECTED], date(2026, 8, 25), obs, oid="IO-CB-2026-14-1-a")
    assert limb.result is DecisionResult.NOT_TRIGGERED


def test_unknown_override_is_a_rule_pack_error() -> None:
    """overridden_by must name a loaded obligation."""
    with pytest.raises(EvaluationError):
        evaluate(
            [RECEIVED, REJECTED], [ordinary_limb()], CAL, at(date(2026, 8, 25)), profile=PROFILE
        )


def test_no_clock_obligation_not_applicable() -> None:
    """Clockless obligations are left to the workflow gates."""
    rec = one([RECEIVED, REJECTED], date(2026, 8, 25), [obligation(clock=None, parameters={})])
    assert rec.result is DecisionResult.NOT_APPLICABLE
    assert rec.condition_trace[-1].condition == "obligation has a clock"


def test_requires_aware_as_of_and_complaint_id() -> None:
    """as_of must be aware; complaint_id is needed when there are no events."""
    with pytest.raises(ValueError, match="naive"):
        evaluate([RECEIVED], [obligation()], CAL, datetime(2026, 8, 25), profile=PROFILE)  # noqa: DTZ001
    with pytest.raises(EvaluationError):
        evaluate([], [obligation()], CAL, datetime(2026, 8, 25, tzinfo=UTC), profile=PROFILE)
    (rec,) = evaluate(
        [],
        [obligation()],
        CAL,
        datetime(2026, 8, 25, tzinfo=UTC),
        profile=PROFILE,
        complaint_id="X",
    )
    assert rec.result is DecisionResult.NOT_TRIGGERED


def test_working_day_clock_uses_profile_state() -> None:
    """A working-day clock reads the home-branch state, from the profile when no fact is set."""
    ob = obligation(
        clock={
            "start": "BANK_RECEIVED",
            "stop": "IO_REFERRED",
            "basis": "WORKING",
            "basis_status": "EXPLICIT",
        }
    )
    rec = one([RECEIVED, REJECTED], date(2026, 8, 25), [ob])
    assert rec.deadline is not None
    assert rec.deadline.due_date == date(2026, 8, 26)  # 20 working days skipping 3 Sundays
    assert any(f.name == "profile.home_branch_state" for f in rec.input_facts)
    stateless = PROFILE.model_copy(update={"home_branch_state": None})
    assert one([RECEIVED, REJECTED], date(2026, 8, 25), [ob], profile=stateless).result is (
        DecisionResult.INSUFFICIENT_FACTS
    )
