"""can_close: no same-unit closure and senior review before the IO (report row A15)."""

from datetime import date

import pytest

from abhiyogah.domain.events import ComplaintEvent, EventType
from abhiyogah.workflow import Actor, can_close
from tests.workflow.builders import RECEIVED, ev, exclusion, facts, outcome

OTHER_UNIT = Actor(actor_id="officer-777", unit="NODAL-CELL")
SAME_UNIT = Actor(actor_id="officer-001", unit="BRANCH-042")
REVIEWED = ev(3, EventType.SENIOR_REVIEWED, date(2026, 8, 11))
REFERRED = ev(4, EventType.IO_REFERRED, date(2026, 8, 12))
DECIDED = ev(5, EventType.IO_DECIDED, date(2026, 8, 18), {"io_upheld": True})


def codes(*events: ComplaintEvent, actor: Actor = OTHER_UNIT) -> list[str]:
    """Reason codes from can_close."""
    return [r.code for r in can_close(facts(*events), actor).reasons]


def test_fully_resolved_closed_by_another_unit_is_allowed() -> None:
    """The plain happy path."""
    assert can_close(facts(RECEIVED, outcome("FULLY_RESOLVED")), OTHER_UNIT).allowed


def test_same_unit_closure_is_refused() -> None:
    """The handling branch may not close its own complaint."""
    assert codes(RECEIVED, outcome("FULLY_RESOLVED"), actor=SAME_UNIT) == ["SAME_UNIT_CLOSURE"]


def test_unknown_handling_unit_is_refused() -> None:
    """Without the handling unit the check cannot pass; nothing is assumed."""
    received = ev(1, EventType.BANK_RECEIVED, date(2026, 8, 3))
    assert codes(received, outcome("FULLY_RESOLVED")) == ["HANDLING_UNIT_UNKNOWN"]


def test_missing_outcome_is_reported_with_the_other_reasons() -> None:
    """Every reason is listed, not just the first."""
    assert codes(RECEIVED, actor=SAME_UNIT) == ["OUTCOME_NOT_SET", "SAME_UNIT_CLOSURE"]


@pytest.mark.parametrize("value", ["PARTIALLY_RESOLVED", "WHOLLY_REJECTED"])
def test_adverse_outcome_needs_senior_review_and_io_decision(value: str) -> None:
    """A partial or rejected outcome without review or IO decision is refused on both counts."""
    assert codes(RECEIVED, outcome(value)) == ["SENIOR_REVIEW_MISSING", "IO_DECISION_MISSING"]


def test_adverse_outcome_with_review_then_io_is_allowed() -> None:
    """Senior review, then IO referral and decision: closure is allowed."""
    assert codes(RECEIVED, outcome("WHOLLY_REJECTED"), REVIEWED, REFERRED, DECIDED) == []


def test_senior_review_after_io_referral_is_refused() -> None:
    """The review must come before the case goes to the IO."""
    late_review = ev(3, EventType.SENIOR_REVIEWED, date(2026, 8, 14))
    assert codes(RECEIVED, outcome("WHOLLY_REJECTED"), late_review, REFERRED, DECIDED) == [
        "SENIOR_REVIEW_AFTER_IO"
    ]


def test_out_of_purview_adverse_outcome_does_not_demand_an_io_decision() -> None:
    """Limbs (c)-(e) route to a person (#26); can_close does not invent an IO requirement."""
    assert codes(RECEIVED, exclusion("14_5_d"), outcome("WHOLLY_REJECTED"), REVIEWED) == []


def test_reasons_cite_clauses() -> None:
    """Every refusal cites the IO Directions."""
    result = can_close(facts(RECEIVED, outcome("PARTIALLY_RESOLVED")), SAME_UNIT)
    assert all("IO Directions 2026" in r.clause for r in result.reasons)
