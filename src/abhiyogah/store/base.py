"""The storage interface the API and worker use, and an in-memory implementation.

Events and decision records are append-only evidence (CLAUDE.md hard rule 7): there is no update or
delete. ``append_events`` is idempotent on ``event_id`` (re-sending the same event is a no-op;
re-using an ID for different content is an ``EvidenceConflictError``). ``append_decisions`` seals
the records onto the complaint's chain head with the ledger, so every store chains the same way.
Review tasks are opened once per ``task_id``; closing one is a status change, never a delete.
"""

from collections.abc import Sequence
from threading import Lock
from typing import Protocol

from abhiyogah.domain.decision import DecisionRecord
from abhiyogah.domain.events import ComplaintEvent
from abhiyogah.ledger import chain_head, seal_chain
from abhiyogah.store.errors import EvidenceConflictError
from abhiyogah.workflow import ReviewStatus, ReviewTask

__all__ = ["MemoryStore", "Store"]


class Store(Protocol):
    """Append-only storage of events, decision chains and review tasks."""

    def append_events(self, events: Sequence[ComplaintEvent]) -> list[ComplaintEvent]:
        """Store new events; return the ones that were not already stored."""
        ...

    def events(self, complaint_id: str) -> list[ComplaintEvent]:
        """A complaint's events in recorded order."""
        ...

    def complaint_ids(self) -> list[str]:
        """Every complaint with at least one event, sorted."""
        ...

    def append_decisions(
        self, complaint_id: str, records: Sequence[DecisionRecord]
    ) -> list[DecisionRecord]:
        """Seal unsealed records onto the complaint's chain head and store them."""
        ...

    def decisions(self, complaint_id: str) -> list[DecisionRecord]:
        """A complaint's decision chain, oldest first."""
        ...

    def decision(self, record_hash: str) -> DecisionRecord | None:
        """One sealed record by its hash."""
        ...

    def add_review_task(self, task: ReviewTask) -> bool:
        """Open a task; False if a task with that ID already exists."""
        ...

    def review_tasks(
        self, complaint_id: str | None = None, status: ReviewStatus | None = None
    ) -> list[ReviewTask]:
        """Review tasks, filtered, by creation time."""
        ...


def _event_order(e: ComplaintEvent) -> tuple[object, ...]:
    """The folding order of ``fold_events``."""
    return (e.recorded_at, e.occurred_at, e.event_id)


class MemoryStore:
    """A thread-safe in-process ``Store`` for tests and demos without PostgreSQL."""

    def __init__(self) -> None:
        """Start empty."""
        self._lock = Lock()
        self._events: dict[str, ComplaintEvent] = {}
        self._chains: dict[str, list[DecisionRecord]] = {}
        self._by_hash: dict[str, DecisionRecord] = {}
        self._tasks: dict[str, ReviewTask] = {}

    def append_events(self, events: Sequence[ComplaintEvent]) -> list[ComplaintEvent]:
        """Store new events; return the ones that were not already stored."""
        with self._lock:
            new: list[ComplaintEvent] = []
            for ev in events:
                old = self._events.get(ev.event_id)
                if old is not None:
                    if old != ev:
                        raise EvidenceConflictError(
                            f"event {ev.event_id} exists with other content"
                        )
                    continue
                self._events[ev.event_id] = ev
                new.append(ev)
            return new

    def events(self, complaint_id: str) -> list[ComplaintEvent]:
        """A complaint's events in recorded order."""
        with self._lock:
            found = [e for e in self._events.values() if e.complaint_id == complaint_id]
        return sorted(found, key=_event_order)

    def complaint_ids(self) -> list[str]:
        """Every complaint with at least one event, sorted."""
        with self._lock:
            return sorted({e.complaint_id for e in self._events.values()})

    def append_decisions(
        self, complaint_id: str, records: Sequence[DecisionRecord]
    ) -> list[DecisionRecord]:
        """Seal unsealed records onto the complaint's chain head and store them."""
        with self._lock:
            chain = self._chains.setdefault(complaint_id, [])
            sealed = seal_chain(records, chain_head(chain))
            chain.extend(sealed)
            for r in sealed:
                assert r.hash is not None  # noqa: S101 - sealed
                self._by_hash[r.hash] = r
            return sealed

    def decisions(self, complaint_id: str) -> list[DecisionRecord]:
        """A complaint's decision chain, oldest first."""
        with self._lock:
            return list(self._chains.get(complaint_id, []))

    def decision(self, record_hash: str) -> DecisionRecord | None:
        """One sealed record by its hash."""
        with self._lock:
            return self._by_hash.get(record_hash)

    def add_review_task(self, task: ReviewTask) -> bool:
        """Open a task; False if a task with that ID already exists."""
        with self._lock:
            if task.task_id in self._tasks:
                return False
            self._tasks[task.task_id] = task
            return True

    def review_tasks(
        self, complaint_id: str | None = None, status: ReviewStatus | None = None
    ) -> list[ReviewTask]:
        """Review tasks, filtered, by creation time."""
        with self._lock:
            tasks = [
                t
                for t in self._tasks.values()
                if (complaint_id is None or t.complaint_id == complaint_id)
                and (status is None or t.status is status)
            ]
        return sorted(tasks, key=lambda t: (t.created_at, t.task_id))
