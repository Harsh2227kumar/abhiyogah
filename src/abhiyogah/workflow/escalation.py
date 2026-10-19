"""IO auto-escalation (report row A13, IO Directions 2026 cl. 14(1)).

A partially resolved or wholly rejected complaint is referred to the IO. The workflow does not
compute the due date itself: it takes it from the evaluator's decision records for the obligations
whose clock stops on ``IO_REFERRED`` (the 20-day limb or the external-TAT limb, whichever the
evaluator kept after overrides). How the complaint is routed is data (``workflow.routing``): a
cl. 14(5) limb that leaves routing to a person produces no automatic referral.
"""

from collections.abc import Iterable

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.decision import DecisionRecord, DecisionResult, RequiredAction
from abhiyogah.domain.events import EventType
from abhiyogah.evaluator.actions import action_code
from abhiyogah.workflow.closure import ADVERSE_OUTCOMES
from abhiyogah.workflow.routing import IoRoute, route_for

__all__ = ["REFER_TO_IO", "io_escalation"]

REFER_TO_IO = action_code(EventType.IO_REFERRED)
"""The action code the ``IO_REFERRED`` event fulfils (same code the evaluator uses)."""

_LIVE = frozenset({DecisionResult.RUNNING, DecisionResult.BREACHED})


def io_escalation(
    facts: ComplaintFacts, records: Iterable[DecisionRecord]
) -> RequiredAction | None:
    """The required IO referral for an adverse outcome not yet referred, else None."""
    if facts.outcome is None or facts.outcome.value not in ADVERSE_OUTCOMES:
        return None
    if facts.io_referred_date is not None:
        return None
    route = route_for(facts)
    if route.io_route is not IoRoute.FORWARD_IF_ADVERSE:
        return None
    clocks = [
        (r.deadline.due_date, r.obligation_id, r)
        for r in records
        if r.complaint_id == facts.complaint_id
        and r.result in _LIVE
        and r.deadline is not None
        and r.deadline.stop_event is EventType.IO_REFERRED
    ]
    outcome = facts.outcome.value.value
    if not clocks:
        return RequiredAction(
            action=REFER_TO_IO,
            due_date=None,
            reason=f"Outcome {outcome}: refer to the IO ({route.clause}); no IO deadline computed.",
        )
    due, _, first = min(clocks, key=lambda c: (c[0], c[1]))
    return RequiredAction(
        action=REFER_TO_IO,
        due_date=due,
        reason=(
            f"Outcome {outcome}: refer to the IO by {due} "
            f"({first.obligation_id}, cl. {first.clause}; {route.clause})."
        ),
    )
