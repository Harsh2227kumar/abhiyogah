"""Behaviour every Store must have: append-only, idempotent, chained."""

from datetime import UTC, date, datetime, timedelta

import pytest

from abhiyogah.domain.decision import DecisionResult
from abhiyogah.domain.events import ComplaintEvent, EventType
from abhiyogah.ledger import verify_chain
from abhiyogah.store import EvidenceConflictError, Store
from abhiyogah.workflow import ReviewKind, ReviewStatus, ReviewTask
from tests.domain.test_decision import make_record
from tests.workflow.builders import OFFICER, ev


def other(n: int, complaint_id: str, d: date) -> ComplaintEvent:
    """An event on another complaint."""
    occurred = datetime(d.year, d.month, d.day, 6, tzinfo=UTC)
    return ComplaintEvent(
        event_id=f"OTHER-{n}",
        complaint_id=complaint_id,
        type=EventType.BANK_RECEIVED,
        occurred_at=occurred,
        recorded_at=occurred + timedelta(seconds=5),
        provenance=OFFICER,
    )


E1 = ev(1, EventType.BANK_RECEIVED, date(2026, 8, 3), {"handling_unit": "BRANCH-042"})
E2 = ev(2, EventType.OUTCOME_SET, date(2026, 8, 10), {"outcome": "WHOLLY_REJECTED"})


def test_events_are_returned_in_recorded_order(store: Store) -> None:
    """Insertion order does not matter; recorded order does."""
    assert store.append_events([E2, E1]) == [E2, E1]
    assert store.events("CMP-WF-1") == [E1, E2]
    assert store.events("NOPE") == []


def test_resending_an_event_is_a_no_op(store: Store) -> None:
    """The same event twice is stored once."""
    store.append_events([E1])
    assert store.append_events([E1, E2]) == [E2]
    assert store.events("CMP-WF-1") == [E1, E2]


def test_reusing_an_event_id_for_other_content_is_refused(store: Store) -> None:
    """Evidence is never overwritten."""
    store.append_events([E1])
    changed = E1.model_copy(update={"payload": {"handling_unit": "BRANCH-999"}})
    with pytest.raises(EvidenceConflictError):
        store.append_events([changed])
    assert store.events("CMP-WF-1") == [E1]


def test_complaint_ids_are_distinct_and_sorted(store: Store) -> None:
    """Each complaint is listed once."""
    store.append_events([E1, E2, other(1, "CMP-A", date(2026, 8, 1))])
    assert store.complaint_ids() == ["CMP-A", "CMP-WF-1"]


def test_decisions_chain_across_appends(store: Store) -> None:
    """Two batches form one verified chain; each record is found by its hash."""
    first = store.append_decisions("CMP-TEST-1", [make_record(), make_record()])
    second = store.append_decisions("CMP-TEST-1", [make_record(DecisionResult.RUNNING)])
    chain = store.decisions("CMP-TEST-1")
    assert chain == first + second
    assert verify_chain(chain).verified
    for r in chain:
        assert r.hash is not None
        assert store.decision(r.hash) == r
    assert store.decision("0" * 64) is None


def test_each_complaint_has_its_own_chain(store: Store) -> None:
    """Chains do not interleave between complaints."""
    a = store.append_decisions("CMP-TEST-1", [make_record()])
    b = store.append_decisions(
        "CMP-TEST-2", [make_record().model_copy(update={"complaint_id": "CMP-TEST-2"})]
    )
    assert a[0].prev_hash == b[0].prev_hash == "0" * 64
    assert store.decisions("CMP-TEST-2") == b


def task(n: int, complaint_id: str = "CMP-WF-1") -> ReviewTask:
    """A synthetic review task."""
    return ReviewTask(
        task_id=f"RT-{n}",
        complaint_id=complaint_id,
        kind=ReviewKind.NOT_A_COMPLAINT,
        reason="test",
        source_ref=f"PF-{n}",
        created_at=datetime(2026, 8, 4, n, tzinfo=UTC),
    )


def test_review_tasks_are_opened_once_and_filtered(store: Store) -> None:
    """A task ID opens one task; filters by complaint and status work."""
    assert store.add_review_task(task(2))
    assert store.add_review_task(task(1, "CMP-OTHER"))
    assert not store.add_review_task(task(2))
    assert [t.task_id for t in store.review_tasks()] == ["RT-1", "RT-2"]
    assert [t.task_id for t in store.review_tasks("CMP-WF-1")] == ["RT-2"]
    assert len(store.review_tasks(status=ReviewStatus.OPEN)) == 2
    assert store.review_tasks(status=ReviewStatus.DONE) == []


def test_review_task_closes_once_with_a_stored_event(store: Store) -> None:
    """OPEN -> DONE naming the event; a second close and unknown IDs are refused."""
    from abhiyogah.store import ReviewTaskClosedError, UnknownReviewTaskError

    store.append_events([E1])
    store.add_review_task(task(1))
    closed = store.close_review_task("RT-1", E1.event_id)
    assert closed.status is ReviewStatus.DONE
    assert closed.closed_by_event_id == E1.event_id
    assert store.review_task("RT-1") == closed
    assert store.review_tasks(status=ReviewStatus.DONE) == [closed]
    with pytest.raises(ReviewTaskClosedError):
        store.close_review_task("RT-1", E1.event_id)
    with pytest.raises(UnknownReviewTaskError):
        store.close_review_task("RT-404", E1.event_id)
    store.add_review_task(task(2))
    with pytest.raises(UnknownReviewTaskError):
        store.close_review_task("RT-2", "NO-SUCH-EVENT")
    assert store.review_task("RT-2") is not None
    assert store.review_task("RT-2").status is ReviewStatus.OPEN  # type: ignore[union-attr]
