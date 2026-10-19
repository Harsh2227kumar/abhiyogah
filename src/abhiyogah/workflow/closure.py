"""Closure gates: what must be true before a complaint may be closed.

``outcome_gate`` is the three-state rule (report row A14, IO Directions 2026 cl. 14(2)): a complaint
is closed only with "Fully Resolved", "Partially Resolved" or "Wholly Rejected". The ``Outcome``
enum already refuses any other value, so the gate checks that one was recorded. Out-of-purview
complaints (cl. 14(5)(c)-(e)) are exempt (see ``workflow.routing``).
"""

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.enums import Outcome
from abhiyogah.workflow.gates import GateReason, GateResult
from abhiyogah.workflow.routing import route_for

__all__ = ["CLAUSE_14_2", "outcome_gate"]

CLAUSE_14_2 = "IO Directions 2026 cl. 14(2)"


def outcome_gate(facts: ComplaintFacts) -> GateResult:
    """Closing needs one of the three outcomes, unless the complaint is out of purview."""
    route = route_for(facts)
    if route.three_state_exempt or facts.outcome is not None:
        return GateResult()
    allowed = ", ".join(o.value for o in Outcome)
    return GateResult(
        reasons=[
            GateReason(
                code="OUTCOME_NOT_SET",
                message=f"Record an outcome ({allowed}) before closing.",
                clause=CLAUSE_14_2,
            )
        ]
    )
