"""Closure gates: what must be true before a complaint may be closed.

``outcome_gate`` is the three-state rule (report row A14, IO Directions 2026 cl. 14(2)): a complaint
is closed only with "Fully Resolved", "Partially Resolved" or "Wholly Rejected". The ``Outcome``
enum already refuses any other value, so the gate checks that one was recorded. Out-of-purview
complaints (cl. 14(5)(c)-(e)) are exempt (see ``workflow.routing``).

``can_close`` adds the segregation-of-duties checks of report row A15 (IO Directions 2026
cl. 14(3)-(4); which limb is in which sub-clause is open question Q16): the unit that handled the
complaint does not close it, and a partially resolved or wholly rejected outcome is reviewed at a
senior level before it goes to the IO. Such an outcome also goes to the IO before the final reply
(report rows A13 and A18), unless its exclusion route leaves that to a person.
"""

from pydantic import BaseModel, ConfigDict, Field

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.enums import Outcome
from abhiyogah.workflow.gates import GateReason, GateResult
from abhiyogah.workflow.routing import IoRoute, route_for

__all__ = ["ADVERSE_OUTCOMES", "CLAUSE_14_2", "CLAUSE_14_3_4", "Actor", "can_close", "outcome_gate"]

CLAUSE_14_2 = "IO Directions 2026 cl. 14(2)"
CLAUSE_14_3_4 = "IO Directions 2026 cl. 14(3)-(4)"
CLAUSE_IO_REVIEW = "IO Directions 2026 cl. 14(1), 14(11)"

ADVERSE_OUTCOMES = frozenset({Outcome.PARTIALLY_RESOLVED, Outcome.WHOLLY_REJECTED})
"""Outcomes that go to senior review and to the IO (report rows A13 and A15)."""


class Actor(BaseModel):
    """The person attempting an action, and the unit they belong to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: str = Field(min_length=1)
    unit: str = Field(min_length=1, description="Branch, unit or touch point of the actor.")


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


def _unit_gate(facts: ComplaintFacts, actor: Actor) -> GateResult:
    """The handling unit is known and is not the actor's unit."""
    if facts.handling_unit is None:
        return GateResult(
            reasons=[
                GateReason(
                    code="HANDLING_UNIT_UNKNOWN",
                    message="Handling unit not recorded; same-unit closure cannot be ruled out.",
                    clause=CLAUSE_14_3_4,
                )
            ]
        )
    if facts.handling_unit.value == actor.unit:
        return GateResult(
            reasons=[
                GateReason(
                    code="SAME_UNIT_CLOSURE",
                    message=f"Unit {actor.unit} handled this complaint and may not close it.",
                    clause=CLAUSE_14_3_4,
                )
            ]
        )
    return GateResult()


def _adverse_gate(facts: ComplaintFacts) -> GateResult:
    """A partial or rejected outcome had senior review before the IO, and an IO decision."""
    if facts.outcome is None or facts.outcome.value not in ADVERSE_OUTCOMES:
        return GateResult()
    reasons: list[GateReason] = []
    review = facts.senior_review_date
    if review is None:
        reasons.append(
            GateReason(
                code="SENIOR_REVIEW_MISSING",
                message=f"A {facts.outcome.value} outcome needs a senior review (SENIOR_REVIEWED).",
                clause=CLAUSE_14_3_4,
            )
        )
    elif facts.io_referred_date is not None and review.value > facts.io_referred_date.value:
        reasons.append(
            GateReason(
                code="SENIOR_REVIEW_AFTER_IO",
                message=(
                    f"Senior review on {review.value} came after the IO referral on "
                    f"{facts.io_referred_date.value}; it must come before."
                ),
                clause=CLAUSE_14_3_4,
            )
        )
    if route_for(facts).io_route is IoRoute.FORWARD_IF_ADVERSE and facts.io_decided_date is None:
        reasons.append(
            GateReason(
                code="IO_DECISION_MISSING",
                message=f"A {facts.outcome.value} outcome is decided by the IO before closure.",
                clause=CLAUSE_IO_REVIEW,
            )
        )
    return GateResult(reasons=reasons)


def can_close(facts: ComplaintFacts, actor: Actor) -> GateResult:
    """Whether ``actor`` may close the complaint now, with every reason they may not."""
    return outcome_gate(facts) + _unit_gate(facts, actor) + _adverse_gate(facts)
