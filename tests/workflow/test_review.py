"""Every "not a complaint" or "no deficiency" finding opens a human-review task (hard rule 4)."""

from datetime import UTC, datetime

import pytest

from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import ComplaintEvent, Provenance, TextSpan
from abhiyogah.workflow import (
    FindingKind,
    PerceptionFinding,
    ReviewKind,
    ReviewStatus,
    review_task_for_finding,
    review_task_for_routing,
)
from tests.workflow.builders import CID, RECEIVED, exclusion, facts, outcome

LLM = Provenance(
    source=FactSource.LLM,
    model="test-model",
    prompt_version="classify-v1",
    span=TextSpan(document_ref="doc-1", start=0, end=42),
)
SYSTEM = Provenance(source=FactSource.SYSTEM, actor="rules-classifier")
AT = datetime(2026, 8, 4, 9, tzinfo=UTC)


def finding(kind: FindingKind, provenance: Provenance = LLM) -> PerceptionFinding:
    """A synthetic finding on the workflow test complaint."""
    return PerceptionFinding(
        finding_id="PF-1", complaint_id=CID, kind=kind, provenance=provenance, found_at=AT
    )


@pytest.mark.parametrize(
    ("kind", "review"),
    [
        (FindingKind.NOT_A_COMPLAINT, ReviewKind.NOT_A_COMPLAINT),
        (FindingKind.NO_DEFICIENCY, ReviewKind.NO_DEFICIENCY),
    ],
)
@pytest.mark.parametrize("provenance", [LLM, SYSTEM])
def test_dismissive_findings_open_a_review_task(
    kind: FindingKind, review: ReviewKind, provenance: Provenance
) -> None:
    """Whoever made the finding, a person must confirm it; provenance is kept on the task."""
    task = review_task_for_finding(finding(kind, provenance))
    assert task is not None
    assert task.kind is review
    assert task.status is ReviewStatus.OPEN
    assert task.provenance == provenance
    assert task.complaint_id == CID
    assert task.created_at == AT


@pytest.mark.parametrize("kind", [FindingKind.IS_COMPLAINT, FindingKind.DEFICIENCY])
def test_findings_that_keep_the_complaint_in_scope_open_no_task(kind: FindingKind) -> None:
    """Only findings that would drop the complaint need review."""
    assert review_task_for_finding(finding(kind)) is None


def test_task_id_is_stable_for_the_same_finding() -> None:
    """The same finding always maps to the same task, so it is opened once."""
    a = review_task_for_finding(finding(FindingKind.NOT_A_COMPLAINT))
    b = review_task_for_finding(finding(FindingKind.NOT_A_COMPLAINT))
    assert a is not None
    assert b is not None
    assert a.task_id == b.task_id


def test_out_of_purview_adverse_outcome_opens_a_routing_review() -> None:
    """Limb (c)-(e) with a rejected outcome goes to a person (#26)."""
    task = review_task_for_routing(
        facts(RECEIVED, exclusion("14_5_e"), outcome("WHOLLY_REJECTED")), AT
    )
    assert task is not None
    assert task.kind is ReviewKind.EXCLUSION_ROUTING
    assert "14(5)(e)" in task.reason


@pytest.mark.parametrize(
    "events",
    [
        (RECEIVED, outcome("WHOLLY_REJECTED")),
        (RECEIVED, exclusion("14_5_a"), outcome("WHOLLY_REJECTED")),
        (RECEIVED, exclusion("14_5_c"), outcome("FULLY_RESOLVED")),
        (RECEIVED, exclusion("14_5_c")),
    ],
)
def test_routing_review_only_when_routing_is_unsettled(events: tuple[ComplaintEvent, ...]) -> None:
    """Default and forwarded limbs, or non-adverse outcomes, need no routing review."""
    assert review_task_for_routing(facts(*events), AT) is None
