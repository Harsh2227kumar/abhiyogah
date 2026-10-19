"""IO auto-escalation (A13) takes the evaluator's deadline; exclusion routing is data (A16)."""

from datetime import UTC, date, datetime

import pytest

from abhiyogah.domain.decision import DecisionRecord, DecisionResult
from abhiyogah.domain.events import ComplaintEvent, EventType
from abhiyogah.evaluator import evaluate
from abhiyogah.workflow import REFER_TO_IO, io_escalation
from tests.evaluator.builders import ordinary_limb, tat_limb
from tests.evaluator.test_evaluate import CAL, PROFILE
from tests.workflow.builders import RECEIVED, ev, exclusion, facts, outcome

AS_OF = datetime(2026, 8, 15, 12, tzinfo=UTC)


def records_for(*events: ComplaintEvent, as_of: datetime = AS_OF) -> list[DecisionRecord]:
    """Evaluate the A13 limbs over the events."""
    return evaluate(
        list(events),
        [ordinary_limb(), tat_limb()],
        CAL,
        as_of,
        profile=PROFILE,
    )


@pytest.mark.parametrize("value", ["PARTIALLY_RESOLVED", "WHOLLY_REJECTED"])
def test_adverse_outcome_requires_io_referral_by_the_evaluator_deadline(value: str) -> None:
    """Receipt 3 Aug + 20 calendar days: refer by 23 Aug (cl. 14(1)(b))."""
    events = [RECEIVED, outcome(value)]
    action = io_escalation(facts(*events), records_for(*events))
    assert action is not None
    assert action.action == REFER_TO_IO
    assert action.due_date == date(2026, 8, 23)
    assert "IO-CB-2026-14-1-b" in action.reason


def test_breached_deadline_still_requires_referral() -> None:
    """Past day 20 the referral is still required, with the missed due date."""
    events = [RECEIVED, outcome("WHOLLY_REJECTED")]
    late = records_for(*events, as_of=datetime(2026, 8, 30, tzinfo=UTC))
    assert any(r.result is DecisionResult.BREACHED for r in late)
    action = io_escalation(facts(*events), late)
    assert action is not None
    assert action.due_date == date(2026, 8, 23)


def test_external_tat_limb_wins_when_the_evaluator_keeps_it() -> None:
    """An external TAT of 25 days moves the due date to receipt + 25 - 10 = 18 Aug."""
    tat = ev(7, EventType.FACTS_RECORDED, date(2026, 8, 3), {"external_tat_days": 25})
    events = [RECEIVED, tat, outcome("WHOLLY_REJECTED")]
    action = io_escalation(facts(*events), records_for(*events))
    assert action is not None
    assert action.due_date == date(2026, 8, 18)
    assert "IO-CB-2026-14-1-a" in action.reason


def test_no_referral_for_fully_resolved_or_unset_outcome() -> None:
    """Only partial or rejected outcomes escalate."""
    assert io_escalation(facts(RECEIVED), []) is None
    assert io_escalation(facts(RECEIVED, outcome("FULLY_RESOLVED")), []) is None


def test_no_referral_once_referred() -> None:
    """The IO_REFERRED event fulfils the action."""
    events = [RECEIVED, outcome("WHOLLY_REJECTED"), ev(4, EventType.IO_REFERRED, date(2026, 8, 12))]
    assert io_escalation(facts(*events), records_for(*events)) is None


def test_referral_without_a_computed_deadline_has_no_due_date() -> None:
    """No decision records: the referral is still required, but no date is invented."""
    action = io_escalation(facts(RECEIVED, outcome("WHOLLY_REJECTED")), [])
    assert action is not None
    assert action.due_date is None
    assert "no IO deadline" in action.reason


@pytest.mark.parametrize(("limb", "escalates"), [("14_5_a", True), ("14_5_c", False)])
def test_exclusion_routing_comes_from_the_table(limb: str, escalates: bool) -> None:
    """(a) is forwarded on an adverse outcome; (c) goes to a person (#26)."""
    events = [RECEIVED, exclusion(limb), outcome("WHOLLY_REJECTED")]
    assert (io_escalation(facts(*events), records_for(*events)) is not None) is escalates
