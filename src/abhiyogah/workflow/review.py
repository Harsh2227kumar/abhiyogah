"""Human-review tasks (CLAUDE.md hard rule 4).

Perception (LLM classification and extraction) only reports findings. A finding that would let a
complaint drop out of the regulated flow, "not a complaint" or "no deficiency", is never acted on
by itself: it always opens a review task for a person. Exclusion limbs whose IO routing the report
does not settle (``workflow.routing``) open one too. Task IDs are derived from their source, so the
same finding never opens two tasks.
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.events import Provenance
from abhiyogah.workflow.closure import ADVERSE_OUTCOMES
from abhiyogah.workflow.routing import IoRoute, route_for

__all__ = [
    "FindingKind",
    "PerceptionFinding",
    "ReviewKind",
    "ReviewStatus",
    "ReviewTask",
    "review_task_for_finding",
    "review_task_for_routing",
]


class FindingKind(StrEnum):
    """What a perception step concluded about a complaint."""

    IS_COMPLAINT = "IS_COMPLAINT"
    NOT_A_COMPLAINT = "NOT_A_COMPLAINT"
    DEFICIENCY = "DEFICIENCY"
    NO_DEFICIENCY = "NO_DEFICIENCY"


class PerceptionFinding(BaseModel):
    """A classification from perception, with provenance (model, prompt version, span)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str = Field(min_length=1)
    complaint_id: str = Field(min_length=1)
    kind: FindingKind
    provenance: Provenance
    found_at: AwareDatetime
    detail: str = ""


class ReviewKind(StrEnum):
    """Why a person must look at a complaint."""

    NOT_A_COMPLAINT = "NOT_A_COMPLAINT"
    NO_DEFICIENCY = "NO_DEFICIENCY"
    EXCLUSION_ROUTING = "EXCLUSION_ROUTING"


class ReviewStatus(StrEnum):
    """Review task lifecycle; a decision is recorded as a new business event, never an edit."""

    OPEN = "OPEN"
    DONE = "DONE"


class ReviewTask(BaseModel):
    """A task for a person, opened by the engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(min_length=1)
    complaint_id: str = Field(min_length=1)
    kind: ReviewKind
    reason: str
    source_ref: str = Field(description="The finding ID or rule that opened the task.")
    provenance: Provenance | None = Field(
        default=None, description="Provenance of the finding under review, if any."
    )
    created_at: AwareDatetime
    status: ReviewStatus = ReviewStatus.OPEN
    closed_by_event_id: str | None = Field(
        default=None, description="The business event that recorded the person's decision."
    )


_NEEDS_REVIEW: dict[FindingKind, ReviewKind] = {
    FindingKind.NOT_A_COMPLAINT: ReviewKind.NOT_A_COMPLAINT,
    FindingKind.NO_DEFICIENCY: ReviewKind.NO_DEFICIENCY,
}


def review_task_for_finding(finding: PerceptionFinding) -> ReviewTask | None:
    """A review task for every "not a complaint" or "no deficiency" finding, whoever made it."""
    kind = _NEEDS_REVIEW.get(finding.kind)
    if kind is None:
        return None
    detail = f": {finding.detail}" if finding.detail else ""
    return ReviewTask(
        task_id=f"RT-{kind.value}-{finding.finding_id}",
        complaint_id=finding.complaint_id,
        kind=kind,
        reason=f"Perception found {finding.kind.value}{detail}. A person must confirm.",
        source_ref=finding.finding_id,
        provenance=finding.provenance,
        created_at=finding.found_at,
    )


def review_task_for_routing(facts: ComplaintFacts, as_of: AwareDatetime) -> ReviewTask | None:
    """A review task when an adverse outcome's IO routing is left to a person."""
    route = route_for(facts)
    if (
        route.io_route is not IoRoute.HUMAN_REVIEW
        or facts.outcome is None
        or facts.outcome.value not in ADVERSE_OUTCOMES
        or facts.io_referred_date is not None
    ):
        return None
    return ReviewTask(
        task_id=f"RT-{ReviewKind.EXCLUSION_ROUTING.value}-{facts.complaint_id}-{route.category}",
        complaint_id=facts.complaint_id,
        kind=ReviewKind.EXCLUSION_ROUTING,
        reason=f"Outcome {facts.outcome.value.value} under {route.clause}: {route.note}",
        source_ref=route.clause,
        created_at=as_of,
    )
