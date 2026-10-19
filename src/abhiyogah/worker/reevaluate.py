"""Re-evaluation: run the engine over a stored complaint and append only what changed.

Shared by the API (after each new event) and the scheduler (periodically). It reads events from the
store, calls the pure evaluator at ``as_of`` and appends to the complaint's chain only records whose
material content differs from the latest stored record for that obligation. ``as_of`` and the hash
fields are not material, so an unchanged result is never written twice. It also opens the review
tasks the workflow asks for. This module imports no queue library, so the API can use it.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import JsonValue

from abhiyogah.clocks import BankCalendar
from abhiyogah.domain.complaint import fold_events
from abhiyogah.domain.decision import DecisionRecord
from abhiyogah.domain.events import ComplaintEvent
from abhiyogah.evaluator import EntityProfile, evaluate
from abhiyogah.registry.schema import Obligation
from abhiyogah.store import Store
from abhiyogah.workflow import review_task_for_routing

__all__ = ["EngineContext", "ReevaluationResult", "evaluate_stored", "material", "reevaluate"]


@dataclass(frozen=True)
class EngineContext:
    """What the engine needs besides events: the rule pack, the calendar and the entity profile."""

    obligations: Sequence[Obligation]
    calendar: BankCalendar
    profile: EntityProfile


@dataclass(frozen=True)
class ReevaluationResult:
    """What one re-evaluation appended."""

    complaint_id: str
    appended: list[DecisionRecord] = field(default_factory=list)
    review_tasks_opened: list[str] = field(default_factory=list)


_NOT_MATERIAL = frozenset({"as_of", "prev_hash", "hash"})


def material(record: DecisionRecord) -> dict[str, JsonValue]:
    """The record without ``as_of`` and hashes: what must change for a new record."""
    return record.model_dump(mode="json", exclude=set(_NOT_MATERIAL))


def latest_by_obligation(chain: Sequence[DecisionRecord]) -> dict[str, DecisionRecord]:
    """The last stored record per obligation."""
    latest: dict[str, DecisionRecord] = {}
    for r in chain:
        latest[r.obligation_id] = r
    return latest


def evaluate_stored(
    events: Sequence[ComplaintEvent], ctx: EngineContext, complaint_id: str, as_of: datetime
) -> list[DecisionRecord]:
    """Evaluate a complaint's events at ``as_of`` (unsealed records, sorted by obligation)."""
    return evaluate(
        events,
        ctx.obligations,
        ctx.calendar,
        as_of,
        profile=ctx.profile,
        complaint_id=complaint_id,
    )


def reevaluate(
    store: Store, ctx: EngineContext, complaint_id: str, as_of: datetime
) -> ReevaluationResult:
    """Evaluate one complaint at ``as_of``; append changed records and open review tasks."""
    events = store.events(complaint_id)
    fresh = evaluate_stored(events, ctx, complaint_id, as_of)
    latest = latest_by_obligation(store.decisions(complaint_id))
    changed = [
        r
        for r in fresh
        if r.obligation_id not in latest or material(latest[r.obligation_id]) != material(r)
    ]
    appended = store.append_decisions(complaint_id, changed) if changed else []
    opened: list[str] = []
    known = [e for e in events if e.recorded_at <= as_of]
    task = review_task_for_routing(fold_events(complaint_id, known), as_of)
    if task is not None and store.add_review_task(task):
        opened.append(task.task_id)
    return ReevaluationResult(complaint_id, appended, opened)
