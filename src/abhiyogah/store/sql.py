"""``Store`` on PostgreSQL with SQLAlchemy 2 (psycopg 3).

Appending to a decision chain takes a transaction-scoped advisory lock on the complaint, reads the
head, seals with the ledger and inserts; the unique ``(complaint_id, prev_hash)`` constraint is the
backstop that makes a forked chain impossible even without the lock.
"""

from collections.abc import Sequence

from sqlalchemy import Engine, create_engine, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from abhiyogah.domain.decision import GENESIS_HASH, DecisionRecord
from abhiyogah.domain.events import ComplaintEvent
from abhiyogah.ledger import seal_chain
from abhiyogah.store.errors import (
    EvidenceConflictError,
    ReviewTaskClosedError,
    UnknownReviewTaskError,
)
from abhiyogah.store.models import DecisionRow, EventRow, ReviewTaskRow
from abhiyogah.workflow import ReviewStatus, ReviewTask

__all__ = ["SqlStore", "make_engine"]


def make_engine(url: str) -> Engine:
    """An engine for ``url`` (``postgresql+psycopg://...``)."""
    return create_engine(url, pool_pre_ping=True)


def _to_event(row: EventRow) -> ComplaintEvent:
    """Row to domain event."""
    return ComplaintEvent.model_validate(
        {
            "event_id": row.event_id,
            "complaint_id": row.complaint_id,
            "type": row.type,
            "occurred_at": row.occurred_at,
            "recorded_at": row.recorded_at,
            "payload": row.payload,
            "provenance": row.provenance,
        }
    )


def _to_task(task: dict[str, object], status: str, closed_by: str | None) -> ReviewTask:
    """Row to review task; status and closing event come from their columns."""
    return ReviewTask.model_validate({**task, "status": status, "closed_by_event_id": closed_by})


class SqlStore:
    """A ``Store`` backed by PostgreSQL. Tables come from the Alembic migrations."""

    def __init__(self, engine: Engine) -> None:
        """Use ``engine`` for every call; each call is its own transaction."""
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def append_events(self, events: Sequence[ComplaintEvent]) -> list[ComplaintEvent]:
        """Store new events; return the ones that were not already stored."""
        new: list[ComplaintEvent] = []
        with self._sessions.begin() as s:
            for ev in events:
                inserted = s.execute(
                    insert(EventRow)
                    .values(
                        event_id=ev.event_id,
                        complaint_id=ev.complaint_id,
                        type=ev.type.value,
                        occurred_at=ev.occurred_at,
                        recorded_at=ev.recorded_at,
                        payload=ev.model_dump(mode="json")["payload"],
                        provenance=ev.provenance.model_dump(mode="json"),
                    )
                    .on_conflict_do_nothing(index_elements=["event_id"])
                    .returning(EventRow.id)
                ).scalar_one_or_none()
                if inserted is not None:
                    new.append(ev)
                    continue
                old = s.scalars(select(EventRow).where(EventRow.event_id == ev.event_id)).one()
                if _to_event(old) != ev:
                    raise EvidenceConflictError(f"event {ev.event_id} reused with other content")
        return new

    def events(self, complaint_id: str) -> list[ComplaintEvent]:
        """A complaint's events in recorded order."""
        with self._sessions() as s:
            rows = s.scalars(
                select(EventRow)
                .where(EventRow.complaint_id == complaint_id)
                .order_by(EventRow.recorded_at, EventRow.occurred_at, EventRow.event_id)
            )
            return [_to_event(r) for r in rows]

    def complaint_ids(self) -> list[str]:
        """Every complaint with at least one event, sorted."""
        with self._sessions() as s:
            return list(
                s.scalars(select(EventRow.complaint_id).distinct().order_by(EventRow.complaint_id))
            )

    @staticmethod
    def _head(s: Session, complaint_id: str) -> str:
        """The hash of the complaint's last record, or the genesis hash."""
        last = s.scalars(
            select(DecisionRow.hash)
            .where(DecisionRow.complaint_id == complaint_id)
            .order_by(DecisionRow.id.desc())
            .limit(1)
        ).one_or_none()
        return last or GENESIS_HASH

    def append_decisions(
        self, complaint_id: str, records: Sequence[DecisionRecord]
    ) -> list[DecisionRecord]:
        """Seal unsealed records onto the complaint's chain head and store them."""
        with self._sessions.begin() as s:
            s.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:cid, 0))"),
                {"cid": complaint_id},
            )
            sealed = seal_chain(records, self._head(s, complaint_id))
            for r in sealed:
                assert r.hash is not None  # noqa: S101 - sealed
                s.add(
                    DecisionRow(
                        hash=r.hash,
                        prev_hash=r.prev_hash,
                        complaint_id=complaint_id,
                        obligation_id=r.obligation_id,
                        result=r.result.value,
                        as_of=r.as_of,
                        record=r.model_dump(mode="json"),
                    )
                )
                s.flush()
        return sealed

    def decisions(self, complaint_id: str) -> list[DecisionRecord]:
        """A complaint's decision chain, oldest first."""
        with self._sessions() as s:
            rows = s.scalars(
                select(DecisionRow.record)
                .where(DecisionRow.complaint_id == complaint_id)
                .order_by(DecisionRow.id)
            )
            return [DecisionRecord.model_validate(r) for r in rows]

    def decision(self, record_hash: str) -> DecisionRecord | None:
        """One sealed record by its hash."""
        with self._sessions() as s:
            row = s.scalars(
                select(DecisionRow.record).where(DecisionRow.hash == record_hash)
            ).one_or_none()
            return None if row is None else DecisionRecord.model_validate(row)

    def add_review_task(self, task: ReviewTask) -> bool:
        """Open a task; False if a task with that ID already exists."""
        with self._sessions.begin() as s:
            inserted = s.execute(
                insert(ReviewTaskRow)
                .values(
                    task_id=task.task_id,
                    complaint_id=task.complaint_id,
                    kind=task.kind.value,
                    status=task.status.value,
                    created_at=task.created_at,
                    task=task.model_dump(mode="json"),
                )
                .on_conflict_do_nothing(index_elements=["task_id"])
                .returning(ReviewTaskRow.task_id)
            ).scalar_one_or_none()
        return inserted is not None

    def review_tasks(
        self, complaint_id: str | None = None, status: ReviewStatus | None = None
    ) -> list[ReviewTask]:
        """Review tasks, filtered, by creation time."""
        query = select(ReviewTaskRow.task, ReviewTaskRow.status, ReviewTaskRow.closed_by_event_id)
        if complaint_id is not None:
            query = query.where(ReviewTaskRow.complaint_id == complaint_id)
        if status is not None:
            query = query.where(ReviewTaskRow.status == status.value)
        query = query.order_by(ReviewTaskRow.created_at, ReviewTaskRow.task_id)
        with self._sessions() as s:
            return [_to_task(task, st, by) for task, st, by in s.execute(query)]

    def review_task(self, task_id: str) -> ReviewTask | None:
        """One review task by ID."""
        with self._sessions() as s:
            row = s.execute(
                select(
                    ReviewTaskRow.task, ReviewTaskRow.status, ReviewTaskRow.closed_by_event_id
                ).where(ReviewTaskRow.task_id == task_id)
            ).one_or_none()
            return None if row is None else _to_task(*row)

    def close_review_task(self, task_id: str, event_id: str) -> ReviewTask:
        """Mark an open task DONE, closed by the stored event ``event_id``."""
        with self._sessions.begin() as s:
            row = s.execute(
                select(ReviewTaskRow.status)
                .where(ReviewTaskRow.task_id == task_id)
                .with_for_update()
            ).one_or_none()
            if row is None:
                raise UnknownReviewTaskError(task_id)
            if row.status != ReviewStatus.OPEN.value:
                raise ReviewTaskClosedError(task_id)
            known = s.scalar(select(EventRow.id).where(EventRow.event_id == event_id))
            if known is None:
                raise UnknownReviewTaskError(f"{task_id}: no event {event_id}")
            s.execute(
                update(ReviewTaskRow)
                .where(ReviewTaskRow.task_id == task_id)
                .values(status=ReviewStatus.DONE.value, closed_by_event_id=event_id)
            )
        closed = self.review_task(task_id)
        assert closed is not None  # noqa: S101 - just updated
        return closed

    def count_decisions(self) -> int:
        """Total decision records stored (for health checks)."""
        with self._sessions() as s:
            return s.scalar(select(func.count()).select_from(DecisionRow)) or 0
