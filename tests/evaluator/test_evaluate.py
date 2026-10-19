"""The evaluator: applicability, trigger, validity, clock, overrides and the trace."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import JsonValue

from abhiyogah.domain.decision import DecisionRecord, DecisionResult
from abhiyogah.domain.enums import EntityType, FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance
from abhiyogah.domain.tz import IST
from abhiyogah.evaluator import EntityProfile, EvaluationError, ParameterError, evaluate
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


def test_condition_on_unknown_fact_is_not_triggered() -> None:
    """An unknown fact makes an `in` clause false (rule-pack conventions); nothing is assumed."""
    ob = obligation(trigger={"event": "BANK_RECEIVED", "condition": "outcome in [WHOLLY_REJECTED]"})
    rec = one([RECEIVED], date(2026, 8, 30), [ob])
    assert rec.result is DecisionResult.NOT_TRIGGERED
    assert rec.condition_trace[-1].detail == "outcome is unknown"


def test_anchor_before_first_parameter_not_applicable() -> None:
    """A complaint received before the first parameter version: the rule did not apply then."""
    early = ev(1, EventType.BANK_RECEIVED, date(2026, 1, 5))
    rec = one([early, REJECTED], date(2026, 8, 30))
    assert rec.result is DecisionResult.NOT_APPLICABLE
    assert rec.anchor_date == date(2026, 1, 5)


def test_validity_checked_at_as_of() -> None:
    """valid_from/valid_to bound the as_of date: is the rule in the pack at evaluation time?"""
    ended = obligation(valid_to="2026-08-20")
    assert one([RECEIVED, REJECTED], date(2026, 8, 25), [ended]).result is (
        DecisionResult.NOT_APPLICABLE
    )
    assert one([RECEIVED, REJECTED], date(2026, 8, 19), [ended]).result is DecisionResult.RUNNING


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
    assert rec.condition_trace[-1].condition == "obligation has a building block"


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


def failed_txn_obligation() -> Obligation:
    """A B1-shaped obligation: UPI P2P T+1, ₹100/day (report Table B row B1)."""
    p = {"reference": "RBI/2019-20/67 Annex", "verification": "PRIMARY_TEXT_READ"}
    return obligation(
        obligation_id="TAT-2019-UPI-P2P",
        clause="Annex",
        applies_to={"entity_type": "COMMERCIAL_BANK"},
        trigger={"event": "FACTS_RECORDED", "condition": "channel == UPI_P2P"},
        clock={
            "start": "transaction_date_t",
            "stop": "REVERSAL_POSTED",
            "basis": "CALENDAR",
            "basis_status": "EXPLICIT",
        },
        anchor="transaction_date_t",
        valid_from="2019-10-15",
        parameters={
            "max_days": {"2019-10-15": {"value": 1, **p}},
            "compensation_per_day_paise": {"2019-10-15": {"value": 10000, **p}},
        },
    )


def test_failed_txn_compensation_through_evaluator() -> None:
    """T 3 Aug, due 4 Aug, R 7 Aug: 3 days late, ₹300 = 30000 paise."""
    facts = ev(
        1,
        EventType.FACTS_RECORDED,
        date(2026, 8, 3),
        {"transaction_date_t": "2026-08-03", "channel": "UPI_P2P"},
    )
    reversed_ = ev(2, EventType.REVERSAL_POSTED, date(2026, 8, 7))
    rec = one(
        [facts, reversed_], date(2026, 8, 20), [failed_txn_obligation()], oid="TAT-2019-UPI-P2P"
    )
    assert rec.result is DecisionResult.STOPPED_LATE
    assert rec.deadline is not None
    assert rec.deadline.start_event is EventType.FACTS_RECORDED
    assert rec.compensation is not None
    assert rec.compensation.amount_paise == 30000
    assert {p.name for p in rec.parameters} == {"max_days", "compensation_per_day_paise"}
    running = one([facts], date(2026, 8, 4), [failed_txn_obligation()], oid="TAT-2019-UPI-P2P")
    assert running.compensation is None
    accruing = one([facts], date(2026, 8, 6), [failed_txn_obligation()], oid="TAT-2019-UPI-P2P")
    assert accruing.compensation is not None
    assert accruing.compensation.amount_paise == 20000


def a2_like(**overrides: object) -> Obligation:
    """An A2-shaped PERMISSION: 30 days, or the external TAT if longer (report Table A row A2)."""
    p = {"reference": "RB-IOS 2026 cl. 10(1)(f)", "verification": "PRIMARY_TEXT_READ"}
    fields: dict[str, object] = {
        "obligation_id": "RBIOS-2026-10-1-f",
        "deontic": "PERMISSION",
        "subject": "complainant",
        "clause": "10(1)(f)",
        "applies_to": {"entity_type": "COMMERCIAL_BANK"},
        "trigger": {"event": "BANK_RECEIVED"},
        "clock": {
            "start": "BANK_RECEIVED",
            "stop": "FINAL_REPLY_SENT",
            "basis": "CALENDAR",
            "basis_status": "INFERRED",
        },
        "valid_from": "2026-07-01",
        "parameters": {"base_days": {"2026-07-01": {"value": 30, **p}}},
    }
    fields.update(overrides)
    return obligation(**fields)


def test_base_days_takes_longer_external_tat() -> None:
    """A2: max(30, TAT): 30 days without a TAT, 40 with a synthetic 40-day TAT."""
    plain = one([RECEIVED], date(2026, 8, 10), [a2_like()], oid="RBIOS-2026-10-1-f")
    assert plain.deadline is not None
    assert plain.deadline.due_date == date(2026, 9, 2)
    tat = ev(3, EventType.FACTS_RECORDED, date(2026, 8, 3), {"external_tat_days": 40})
    longer = one([RECEIVED, tat], date(2026, 8, 10), [a2_like()], oid="RBIOS-2026-10-1-f")
    assert longer.deadline is not None
    assert longer.deadline.due_date == date(2026, 9, 12)


def test_permission_lapses_without_breach_or_action() -> None:
    """A complainant's right never breaches or requires a bank action; it just lapses."""
    rec = one([RECEIVED], date(2026, 9, 10), [a2_like()], oid="RBIOS-2026-10-1-f")
    assert rec.result is DecisionResult.BREACHED
    assert rec.breach is None
    assert rec.required_actions == []


def a3_like(window: dict[str, int]) -> Obligation:
    """An A3-shaped filing window: max(receipt + 30d, last communication) + window (Table A A3)."""
    p = {"reference": "RB-IOS 2026 cl. 10(1)(g)", "verification": "PRIMARY_TEXT_READ"}
    return a2_like(
        obligation_id="RBIOS-2026-10-1-g",
        clause="10(1)(g)",
        clock={
            "start": "BANK_RECEIVED",
            "stop": "RBI_RECEIVED",
            "basis": "CALENDAR",
            "basis_status": "INFERRED",
        },
        anchor="rbi_receipt_date",
        parameters={
            "base_days": {"2026-07-01": {"value": 30, **p}},
            "filing_window": {"2026-07-01": {"value": window, **p}},
        },
    )


def test_filing_window_with_as_of_standing_in() -> None:
    """Receipt 3 Aug: base end 2 Sep, last communication 10 Sep, + 90 days = 9 Dec."""
    comm = ev(3, EventType.BANK_COMMUNICATION_SENT, date(2026, 9, 10))
    rec = one([RECEIVED, comm], date(2026, 10, 1), [a3_like({"days": 90})], oid="RBIOS-2026-10-1-g")
    assert rec.deadline is not None
    assert rec.deadline.due_date == date(2026, 12, 9)
    assert rec.anchor_date == date(2026, 10, 1)  # RBI receipt unknown: as_of stands in
    assert rec.result is DecisionResult.RUNNING
    filed = ev(4, EventType.RBI_RECEIVED, date(2026, 12, 10))
    late = one(
        [RECEIVED, comm, filed],
        date(2026, 12, 20),
        [a3_like({"days": 90})],
        oid="RBIOS-2026-10-1-g",
    )
    assert late.result is DecisionResult.STOPPED_LATE
    assert late.anchor_date == date(2026, 12, 10)


def test_filing_window_in_years() -> None:
    """A {years: 1} window keeps month and day: 2 Sep 2026 + 1 year = 2 Sep 2027."""
    rec = one([RECEIVED], date(2026, 10, 1), [a3_like({"years": 1})], oid="RBIOS-2026-10-1-g")
    assert rec.deadline is not None
    assert rec.deadline.due_date == date(2027, 9, 2)


def channel_obligation() -> Obligation:
    """A B1-shaped obligation keyed by channel (report Table B row B1 values)."""
    p = {"reference": "RBI/2019-20/67 Annex", "verification": "PRIMARY_TEXT_READ"}
    return failed_txn_obligation().model_copy(
        update={
            "obligation_id": "TAT-2019-FAILED-TXN",
            "trigger": failed_txn_obligation().trigger.model_copy(
                update={"event": EventType.FACTS_RECORDED, "condition": "channel is set"}
            ),
            "parameters": obligation(
                parameters={
                    "tat_days_by_channel": {"2019-10-15": {"value": {"UPI_P2P": 1, "ATM": 5}, **p}},
                    "follows_underlying_system": {"2019-10-15": {"value": ["PPI_OFF_US"], **p}},
                    "compensation_per_day_paise": {"2019-10-15": {"value": 10000, **p}},
                }
            ).parameters,
        }
    )


def txn(channel: str) -> ComplaintEvent:
    """A failed transaction on 3 Aug through ``channel``."""
    payload: dict[str, JsonValue] = {"transaction_date_t": "2026-08-03", "channel": channel}
    return ev(1, EventType.FACTS_RECORDED, date(2026, 8, 3), payload)


def test_tat_by_channel() -> None:
    """ATM T+5: due 8 Aug; not reversed by 10 Aug: breached, ₹200 accrued, REVERSE_TRANSACTION."""
    rec = one([txn("ATM")], date(2026, 8, 10), [channel_obligation()], oid="TAT-2019-FAILED-TXN")
    assert rec.deadline is not None
    assert rec.deadline.due_date == date(2026, 8, 8)
    assert rec.parameters[0].name == "tat_days_by_channel.ATM"
    assert rec.compensation is not None
    assert rec.compensation.amount_paise == 20000
    assert [a.action for a in rec.required_actions] == ["REVERSE_TRANSACTION"]


def test_channel_outside_table_or_underlying_is_insufficient() -> None:
    """A channel without a TAT row, or one that follows its underlying system, is not assumed."""
    for channel in ("IMPS", "PPI_OFF_US"):
        rec = one(
            [txn(channel)], date(2026, 8, 10), [channel_obligation()], oid="TAT-2019-FAILED-TXN"
        )
        assert rec.result is DecisionResult.INSUFFICIENT_FACTS, channel


def test_future_dated_is_never_evaluated() -> None:
    """A FUTURE_DATED rule is NOT_APPLICABLE even after valid_from."""
    rec = one([RECEIVED, REJECTED], date(2026, 8, 25), [obligation(status="FUTURE_DATED")])
    assert rec.result is DecisionResult.NOT_APPLICABLE
    assert rec.deadline is None


def test_one_action_for_alternative_stops() -> None:
    """Comply or appeal (two stop events) is one action."""
    ob = obligation(
        clock={
            "start": "BANK_RECEIVED",
            "stop": ["COMPLIANCE_INTIMATED", "APPEAL_FILED"],
            "basis": "CALENDAR",
            "basis_status": "INFERRED",
        }
    )
    rec = one([RECEIVED, REJECTED], date(2026, 8, 25), [ob])
    assert [a.action for a in rec.required_actions] == ["COMPLY_WITH_AWARD_OR_APPEAL"]


def appeal_window(appellant: str) -> Obligation:
    """An A8-shaped PERMISSION: 30 days from the award to the complainant's appeal (report A8)."""
    p = {"reference": "RB-IOS 2026 cl. 17", "verification": "PRIMARY_TEXT_READ"}
    return a2_like(
        obligation_id="RBIOS-2026-17",
        clause="17",
        trigger={"event": "AWARD_RECEIVED"},
        clock={
            "start": "AWARD_RECEIVED",
            "stop": "APPEAL_FILED",
            "basis": "CALENDAR",
            "basis_status": "INFERRED",
        },
        parameters={
            "max_days": {"2026-07-01": {"value": 30, **p}},
            "stop_conditions": {
                "2026-07-01": {"value": {"APPEAL_FILED": f"appellant in [{appellant}]"}, **p}
            },
        },
    )


AWARD = ev(1, EventType.AWARD_RECEIVED, date(2026, 8, 3))


def appeal(n: int, d: date, appellant: str) -> ComplaintEvent:
    """An appeal filed on ``d`` by ``appellant``."""
    return ev(n, EventType.APPEAL_FILED, d, {"appellant": appellant})


def test_stop_filtered_by_payload() -> None:
    """A bank appeal does not stop the complainant's window; the complainant's own appeal does."""
    ob = appeal_window("COMPLAINANT")
    by_bank = [AWARD, appeal(2, date(2026, 8, 10), "BANK")]
    rec = one(by_bank, date(2026, 8, 20), [ob], oid="RBIOS-2026-17")
    assert rec.result is DecisionResult.RUNNING
    assert any("EV-2" in t.condition and not t.result for t in rec.condition_trace)
    both = [*by_bank, appeal(3, date(2026, 8, 25), "COMPLAINANT")]
    rec = one(both, date(2026, 9, 10), [ob], oid="RBIOS-2026-17")
    assert rec.result is DecisionResult.STOPPED_ON_TIME
    assert rec.deadline is not None
    assert rec.deadline.stop_event is EventType.APPEAL_FILED
    assert {p.name for p in rec.parameters} == {"max_days", "stop_conditions"}


def test_filtered_stop_never_matched_lapses() -> None:
    """With only a bank appeal, the complainant's 30-day window lapses after 2 Sep."""
    rec = one(
        [AWARD, appeal(2, date(2026, 8, 10), "BANK")],
        date(2026, 9, 5),
        [appeal_window("COMPLAINANT")],
        oid="RBIOS-2026-17",
    )
    assert rec.result is DecisionResult.BREACHED
    assert rec.breach is None  # a PERMISSION never breaches


def test_stop_conditions_must_name_stop_events() -> None:
    """A stop_conditions key that is not a stop event is a rule-pack error."""
    ob = appeal_window("COMPLAINANT")
    bad = ob.model_copy(
        update={
            "parameters": {
                **ob.parameters,
                "stop_conditions": obligation(
                    parameters={
                        "stop_conditions": {
                            "2026-07-01": {
                                "value": {"IO_REFERRED": "appellant is set"},
                                "reference": "x",
                                "verification": "UNVERIFIED",
                            }
                        }
                    }
                ).parameters["stop_conditions"],
            }
        }
    )
    with pytest.raises(ParameterError):
        one(
            [AWARD, appeal(2, date(2026, 8, 10), "BANK")],
            date(2026, 9, 5),
            [bad],
            oid="RBIOS-2026-17",
        )
