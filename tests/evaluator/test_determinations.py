"""Determinations (DETERMINED with outputs and actions) and clock outputs.

Obligations here are test fixtures shaped like the rule pack's (report rows A1, A2, A3, A14, A15,
A18, B5); their values are the report's.
"""

from datetime import date
from typing import Any

from pydantic import JsonValue

from abhiyogah.domain.decision import DecisionRecord, DecisionResult
from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance
from abhiyogah.evaluator import evaluate
from abhiyogah.registry.schema import Obligation
from tests.evaluator.builders import obligation
from tests.evaluator.test_evaluate import CAL, PROFILE, a2_like, a3_like, at, ev

P = {"reference": "test fixture from the report", "verification": "PRIMARY_TEXT_READ"}


def run(ob: Obligation, events: list[ComplaintEvent], as_of: date) -> DecisionRecord:
    """Evaluate one obligation."""
    (rec,) = evaluate(events, [ob], CAL, at(as_of, 18), profile=PROFILE, complaint_id="CMP-1")
    return rec


def clockless(oid: str, **kw: Any) -> Obligation:
    """A clockless obligation with the given ID and fields."""
    kw.setdefault("parameters", {})
    return obligation(obligation_id=oid, clock=None, **kw)


def human(n: int, type_: EventType, d: date, payload: dict[str, JsonValue]) -> ComplaintEvent:
    """An event recorded by a person (needed for liability_fault)."""
    base = ev(n, type_, d, payload)
    return base.model_copy(
        update={"provenance": Provenance(source=FactSource.HUMAN, actor="officer-1")}
    )


RECEIVED = ev(1, EventType.BANK_RECEIVED, date(2026, 8, 3))


def test_scheme_router_uses_parameter_at_anchor() -> None:
    """A1: RBI receipt 30 Jun 2026 -> RB-IOS-2021; 1 Jul 2026 -> RB-IOS-2026."""
    ob = clockless(
        "RBIOS-2026-20-2",
        trigger={"event": "RBI_RECEIVED"},
        anchor="rbi_receipt_date",
        parameters={
            "scheme": {
                "2021-11-12": {"value": "RB-IOS-2021", **P},
                "2026-07-01": {"value": "RB-IOS-2026", **P},
            }
        },
    )
    old = run(ob, [ev(2, EventType.RBI_RECEIVED, date(2026, 6, 30))], date(2026, 7, 10))
    assert old.result is DecisionResult.DETERMINED
    assert old.outputs == {"scheme": "RB-IOS-2021"}
    new = run(ob, [ev(2, EventType.RBI_RECEIVED, date(2026, 7, 1))], date(2026, 7, 10))
    assert new.outputs == {"scheme": "RB-IOS-2026"}
    assert new.deadline is None


def a14() -> Obligation:
    """A14: outcome classified at closure."""
    return clockless(
        "IO-CB-2026-14-2",
        trigger={"event": "FINAL_REPLY_SENT"},
        anchor="final_reply_date",
        parameters={
            "allowed_outcomes": {
                "2026-06-30": {
                    "value": ["FULLY_RESOLVED", "PARTIALLY_RESOLVED", "WHOLLY_REJECTED"],
                    **P,
                }
            }
        },
    )


def test_outcome_classified_or_missing() -> None:
    """Set before the reply: true. Missing at the reply: false plus SET_OUTCOME."""
    outcome = ev(2, EventType.OUTCOME_SET, date(2026, 8, 10), {"outcome": "WHOLLY_REJECTED"})
    reply = ev(3, EventType.FINAL_REPLY_SENT, date(2026, 8, 12))
    good = run(a14(), [RECEIVED, outcome, reply], date(2026, 8, 13))
    assert good.outputs == {"classified_at_closure": True}
    assert good.required_actions == []
    missing = run(a14(), [RECEIVED, reply], date(2026, 8, 13))
    assert missing.result is DecisionResult.DETERMINED
    assert missing.outputs == {"classified_at_closure": False}
    assert [a.action for a in missing.required_actions] == ["SET_OUTCOME"]
    assert missing.breach is None


def test_outcome_check_before_parameter_in_force() -> None:
    """A reply before the compliance date: the check did not apply then."""
    reply = ev(3, EventType.FINAL_REPLY_SENT, date(2026, 6, 15))
    assert run(a14(), [RECEIVED, reply], date(2026, 8, 1)).result is DecisionResult.NOT_APPLICABLE


def test_closure_units() -> None:
    """A15 closure: both units are needed; different units -> true."""
    ob = clockless("IO-CB-2026-14-3-4-closure", trigger={"event": "FINAL_REPLY_SENT"})
    received = ev(1, EventType.BANK_RECEIVED, date(2026, 8, 3), {"handling_unit": "BR-1"})
    other = ev(3, EventType.FINAL_REPLY_SENT, date(2026, 8, 12), {"closing_unit": "GRC-1"})
    assert run(ob, [received, other], date(2026, 8, 13)).outputs == {"closed_by_other_unit": True}
    unknown = ev(3, EventType.FINAL_REPLY_SENT, date(2026, 8, 12))
    rec = run(ob, [received, unknown], date(2026, 8, 13))
    assert rec.result is DecisionResult.INSUFFICIENT_FACTS
    assert rec.outputs == {}


def test_senior_review() -> None:
    """A15 review: pending review asks for SENIOR_REVIEW; skipped before IO is false, no action."""
    ob = clockless("IO-CB-2026-14-3-4-review")
    outcome = ev(2, EventType.OUTCOME_SET, date(2026, 8, 10), {"outcome": "WHOLLY_REJECTED"})
    pending = run(ob, [RECEIVED, outcome], date(2026, 8, 12))
    assert pending.outputs == {"senior_reviewed_before_io": False}
    assert [a.action for a in pending.required_actions] == ["SENIOR_REVIEW"]
    referred = ev(3, EventType.IO_REFERRED, date(2026, 8, 14))
    skipped = run(ob, [RECEIVED, outcome, referred], date(2026, 8, 15))
    assert skipped.outputs == {"senior_reviewed_before_io": False}
    assert skipped.required_actions == []
    reviewed = ev(4, EventType.SENIOR_REVIEWED, date(2026, 8, 12))
    done = run(ob, [RECEIVED, outcome, reviewed, referred], date(2026, 8, 15))
    assert done.outputs == {"senior_reviewed_before_io": True}


def test_reply_content() -> None:
    """A18: missing elements are listed, sorted, with SEND_CORRECTED_REPLY; the IO extra applies."""
    ob = clockless(
        "IO-CB-2026-14-11-12",
        trigger={"event": "FINAL_REPLY_SENT"},
        anchor="final_reply_date",
        parameters={
            "required_elements": {"2026-01-14": {"value": ["B", "A"], **P}},
            "required_elements_if_io_upheld": {"2026-01-14": {"value": ["IO"], **P}},
        },
    )
    upheld = ev(2, EventType.IO_DECIDED, date(2026, 8, 20), {"io_upheld": True})
    reply = ev(3, EventType.FINAL_REPLY_SENT, date(2026, 8, 27), {"reply_elements": ["A"]})
    rec = run(ob, [RECEIVED, upheld, reply], date(2026, 8, 28))
    assert rec.outputs == {"reply_complete": False, "missing_elements": ["B", "IO"]}
    assert [a.action for a in rec.required_actions] == ["SEND_CORRECTED_REPLY"]
    full = ev(3, EventType.FINAL_REPLY_SENT, date(2026, 8, 27), {"reply_elements": ["A", "B"]})
    assert run(ob, [RECEIVED, full], date(2026, 8, 28)).outputs == {
        "reply_complete": True,
        "missing_elements": [],
    }


def b5() -> Obligation:
    """B5: limited liability with the report's thresholds (3 / 7 WD) and two caps."""
    return obligation(
        obligation_id="RBCCB-2025-67-71",
        clause="paras 67-71",
        applies_to={"entity_type": "COMMERCIAL_BANK"},
        trigger={"event": "CUSTOMER_REPORTED"},
        clock={
            "start": "ALERT_RECEIVED",
            "stop": "CUSTOMER_REPORTED",
            "basis": "WORKING",
            "basis_status": "EXPLICIT",
        },
        valid_from="2025-11-28",
        parameters={
            "zero_liability_max_working_days": {"2025-11-28": {"value": 3, **P}},
            "limited_liability_max_working_days": {"2025-11-28": {"value": 7, **P}},
            "cap_paise_by_account_type": {
                "2025-11-28": {"value": {"BSBD": 500000, "OTHER_SAVINGS": 1000000}, **P}
            },
        },
    )


def b5_events(reported: date, fault: str, account: str = "OTHER_SAVINGS") -> list[ComplaintEvent]:
    """Alert Mon 8 Jun 2026, report on ``reported``, ₹40,000 transaction."""
    return [
        ev(1, EventType.ALERT_RECEIVED, date(2026, 6, 8)),
        ev(
            2,
            EventType.CUSTOMER_REPORTED,
            reported,
            {"account_type": account, "amount_paise": 4000000},
        ),
        human(3, EventType.FACTS_RECORDED, reported, {"liability_fault": fault}),
    ]


def test_liability_tiers() -> None:
    """Fake calendar (Sundays closed): 3 WD zero, 5 capped, 9 board policy; bank fault is zero."""
    three = run(b5(), b5_events(date(2026, 6, 11), "THIRD_PARTY"), date(2026, 6, 11))
    assert three.result is DecisionResult.DETERMINED
    assert three.deadline is None
    assert three.outputs == {
        "delay_working_days": 3,
        "liability_tier": "ZERO",
        "customer_liability_paise": 0,
    }
    five = run(b5(), b5_events(date(2026, 6, 13), "THIRD_PARTY"), date(2026, 6, 13))
    assert five.outputs["customer_liability_paise"] == 1000000
    board = run(b5(), b5_events(date(2026, 6, 18), "THIRD_PARTY"), date(2026, 6, 18))
    assert board.outputs == {
        "delay_working_days": 9,
        "liability_tier": "BOARD_POLICY",
        "customer_liability_paise": None,
    }
    bank = run(b5(), b5_events(date(2026, 6, 18), "BANK"), date(2026, 6, 18))
    assert bank.outputs["liability_tier"] == "ZERO"


def test_liability_needs_the_fault() -> None:
    """Without a person's finding on fault, nothing is decided."""
    events = b5_events(date(2026, 6, 13), "THIRD_PARTY")[:2]
    rec = run(b5(), events, date(2026, 6, 13))
    assert rec.result is DecisionResult.INSUFFICIENT_FACTS


def test_clock_outputs() -> None:
    """A2 escalation_open; A3 filed_in_time only once filed."""
    lapsed = run(a2_like(), [RECEIVED], date(2026, 9, 10))
    assert lapsed.outputs == {"escalation_open": True}
    running = run(a2_like(), [RECEIVED], date(2026, 8, 10))
    assert running.outputs == {"escalation_open": False}
    dissatisfied = ev(2, EventType.CUSTOMER_DISSATISFIED, date(2026, 8, 5))
    assert run(a2_like(), [RECEIVED, dissatisfied], date(2026, 8, 10)).outputs == {
        "escalation_open": True
    }
    a3 = a3_like({"days": 90})
    assert run(a3, [RECEIVED], date(2026, 10, 1)).outputs == {}
    filed = ev(2, EventType.RBI_RECEIVED, date(2026, 10, 1))
    assert run(a3, [RECEIVED, filed], date(2026, 10, 2)).outputs == {"filed_in_time": True}


def test_clockless_without_determination_is_not_applicable() -> None:
    """An unknown clockless obligation still reports NOT_APPLICABLE with its reason."""
    rec = run(
        clockless("X-2026-1", trigger={"event": "BANK_RECEIVED"}), [RECEIVED], date(2026, 8, 5)
    )
    assert rec.result is DecisionResult.NOT_APPLICABLE
    assert rec.condition_trace[-1].condition == "obligation has a building block"
