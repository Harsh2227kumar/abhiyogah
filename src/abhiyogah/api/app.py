"""The engine's REST API (FastAPI).

Writes record business events and perception findings; reads evaluate the pure engine over the
stored events at ``as_of``. ``as_of`` other than now is time travel and needs the ADMIN role. Reads
never write: the decision ledger grows only when events arrive (re-evaluation right after the
write) or when the scheduler re-evaluates. Workflow gates are advisory on reads
(``/complaints/{id}/closure``): a business event that already happened is always recorded, and the
check obligations then flag it.

Run with ``uvicorn abhiyogah.api.app:app``; ``create_app`` builds one with injected parts for tests.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from abhiyogah.api.auth import Principal, Role, parse_api_keys, require
from abhiyogah.api.rulepack import load_obligations
from abhiyogah.api.schemas import (
    ActionItem,
    BreachItem,
    ClosureCheck,
    ComplaintDetail,
    ComplaintSummary,
    DeadlineItem,
    DecisionChain,
    DecisionReplay,
    EventsAccepted,
    EventsIn,
    Explanation,
    FindingIn,
    NextDeadline,
)
from abhiyogah.api.settings import Settings
from abhiyogah.calendar import load_bank_calendar
from abhiyogah.domain.complaint import fold_events
from abhiyogah.domain.decision import DecisionRecord, DecisionResult
from abhiyogah.domain.errors import DomainError, FactFoldError
from abhiyogah.domain.events import ComplaintEvent, Provenance
from abhiyogah.evaluator import ForecastItem, forecast_records
from abhiyogah.ledger import ChainStatus, render_explanation, verify_chain
from abhiyogah.registry.schema import Obligation
from abhiyogah.store import EvidenceConflictError, MemoryStore, Store
from abhiyogah.worker.reevaluate import EngineContext, evaluate_stored, reevaluate
from abhiyogah.workflow import (
    Actor,
    PerceptionFinding,
    ReviewStatus,
    ReviewTask,
    can_close,
    io_escalation,
    review_task_for_finding,
)

__all__ = ["app", "create_app"]

Now = Callable[[], datetime]

CLOCK_SKEW = timedelta(minutes=5)
"""How far in the future an ``occurred_at`` may be before it is refused (client clock drift)."""

_TRIGGERED = frozenset(
    {
        DecisionResult.RUNNING,
        DecisionResult.BREACHED,
        DecisionResult.STOPPED_ON_TIME,
        DecisionResult.STOPPED_LATE,
        DecisionResult.DETERMINED,
        DecisionResult.INSUFFICIENT_FACTS,
    }
)


def _utc_now() -> datetime:
    """The wall clock, in UTC. Only the API edge reads it; the core is given ``as_of``."""
    return datetime.now(UTC)


Reader = Annotated[Principal, Depends(require(Role.READER))]
Writer = Annotated[Principal, Depends(require(Role.WRITER))]
AsOf = Annotated[
    datetime | None,
    Query(description="Evaluate as of this instant (ISO 8601 with offset). ADMIN only."),
]


def create_app(
    *,
    settings: Settings | None = None,
    store: Store | None = None,
    ctx: EngineContext | None = None,
    now: Now = _utc_now,
) -> FastAPI:
    """Build the API. Parts not given are built from ``settings`` (default: the environment)."""
    settings = settings or Settings.from_env()
    if store is None:
        if settings.database_url:
            from abhiyogah.store.sql import SqlStore, make_engine

            store = SqlStore(make_engine(settings.database_url))
        else:
            store = MemoryStore()
    if ctx is None:
        ctx = EngineContext(
            obligations=load_obligations(settings.rules_dir),
            calendar=load_bank_calendar(),
            profile=settings.profile,
        )
    api = FastAPI(
        title="Abhiyogah engine API",
        version="0.1.0",
        description="RBI complaint-compliance engine: clause-cited deadlines and breaches.",
    )
    api.state.keyring = parse_api_keys(settings.api_keys)
    api.add_exception_handler(DomainError, _engine_failed)
    _routes(api, store, ctx, now)
    return api


async def _engine_failed(request: Request, exc: Exception) -> JSONResponse:
    """A rule-pack or engine error on a read: 500 with the engine's message, not a traceback."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"the engine could not evaluate: {exc}"},
    )


def _as_of(principal: Principal, as_of: datetime | None, now: Now) -> datetime:
    """``as_of`` if the caller may time-travel, else now."""
    if as_of is None:
        return now()
    if principal.role < Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "as_of needs role ADMIN")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "as_of needs a UTC offset")
    return as_of


def _known(events: list[ComplaintEvent], as_of: datetime) -> list[ComplaintEvent]:
    """Events recorded and occurred by ``as_of``."""
    return [e for e in events if e.recorded_at <= as_of and e.occurred_at <= as_of]


def _chain_upto(chain: list[DecisionRecord], as_of: datetime) -> list[DecisionRecord]:
    """The stored chain as it stood at ``as_of`` (a prefix, so it still verifies)."""
    out: list[DecisionRecord] = []
    for r in chain:
        if r.as_of > as_of:
            break
        out.append(r)
    return out


def _actions(records: list[DecisionRecord], extra: ActionItem | None) -> list[ActionItem]:
    """Evaluator actions, plus a workflow action whose code no record already requires."""
    items = [
        ActionItem(source="EVALUATOR", obligation_id=r.obligation_id, action=a)
        for r in records
        for a in r.required_actions
    ]
    if extra is not None and all(i.action.action != extra.action.action for i in items):
        items.append(extra)
    return sorted(items, key=lambda i: (i.action.due_date is None, i.action.due_date, i.source))


def _routes(api: FastAPI, store: Store, ctx: EngineContext, now: Now) -> None:
    """Register every route on ``api``."""

    def require_known(complaint_id: str) -> list[ComplaintEvent]:
        """The complaint's events; 404 if it has none."""
        events = store.events(complaint_id)
        if not events:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown complaint {complaint_id}")
        return events

    def detail(complaint_id: str, as_of: datetime) -> ComplaintDetail:
        """Evaluate one complaint at ``as_of``."""
        events = _known(require_known(complaint_id), as_of)
        if not events:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"complaint {complaint_id} had no events by {as_of}"
            )
        facts = fold_events(complaint_id, events)
        records = evaluate_stored(events, ctx, complaint_id, as_of)
        escalation = io_escalation(facts, records)
        extra = (
            ActionItem(source="WORKFLOW", obligation_id=None, action=escalation)
            if escalation is not None
            else None
        )
        return ComplaintDetail(
            complaint_id=complaint_id,
            as_of=as_of,
            events=events,
            facts=facts,
            decisions=records,
            deadlines=sorted(
                (
                    DeadlineItem(
                        obligation_id=r.obligation_id,
                        clause=r.clause,
                        result=r.result,
                        deadline=r.deadline,
                    )
                    for r in records
                    if r.deadline is not None
                ),
                key=lambda d: (d.deadline.due_date, d.obligation_id),
            ),
            breaches=[
                BreachItem(clause=r.clause, breach=r.breach, compensation=r.compensation)
                for r in records
                if r.breach is not None
            ],
            required_actions=_actions(records, extra),
            review_tasks=[t for t in store.review_tasks(complaint_id) if t.created_at <= as_of],
            chain=verify_chain(_chain_upto(store.decisions(complaint_id), as_of)),
        )

    @api.get("/health", tags=["meta"], operation_id="health")
    def health() -> dict[str, str]:
        """Liveness probe; no authentication."""
        return {"status": "ok"}

    @api.post(
        "/complaints/{complaint_id}/events",
        status_code=status.HTTP_201_CREATED,
        operation_id="postEvents",
        tags=["complaints"],
    )
    def post_events(complaint_id: str, body: EventsIn, principal: Writer) -> EventsAccepted:
        """Record business events on a complaint, then re-evaluate it."""
        at = now()
        events: list[ComplaintEvent] = []
        for e in body.events:
            if e.occurred_at > at + CLOCK_SKEW:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"event {e.event_id}: occurred_at is in the future",
                )
            try:
                provenance = Provenance(
                    source=e.source,
                    actor=principal.actor_id,
                    model=e.model,
                    prompt_version=e.prompt_version,
                    span=e.span,
                )
                events.append(
                    ComplaintEvent(
                        event_id=e.event_id,
                        complaint_id=complaint_id,
                        type=e.type,
                        occurred_at=e.occurred_at,
                        recorded_at=at,
                        payload=e.payload,
                        provenance=provenance,
                    )
                )
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"event {e.event_id}: {exc}"
                ) from exc
        existing = store.events(complaint_id)
        try:
            fold_events(complaint_id, [*existing, *events])
        except FactFoldError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        stored_ids = {e.event_id for e in existing}
        # A re-sent event keeps its first recorded_at: compare it with the stored copy.
        fresh = [e for e in events if e.event_id not in stored_ids]
        by_id = {x.event_id: x for x in existing}
        for ev in events:
            old = by_id.get(ev.event_id)
            if old is not None and old.model_copy(update={"recorded_at": at}) != ev:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"event {ev.event_id} reused with other content"
                )
        try:
            new = store.append_events(fresh)
        except EvidenceConflictError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        new_ids = {e.event_id for e in new}
        accepted = [e.event_id for e in events if e.event_id in new_ids]
        already = [e.event_id for e in events if e.event_id not in new_ids]
        # The events are evidence and stay stored even if the engine fails; the scheduler retries.
        try:
            result = reevaluate(store, ctx, complaint_id, at)
        except DomainError as exc:
            return EventsAccepted(
                accepted=accepted,
                already_recorded=already,
                decisions_appended=0,
                evaluation_error=str(exc),
            )
        return EventsAccepted(
            accepted=accepted,
            already_recorded=already,
            decisions_appended=len(result.appended),
            review_tasks_opened=result.review_tasks_opened,
        )

    @api.post(
        "/complaints/{complaint_id}/findings",
        status_code=status.HTTP_201_CREATED,
        operation_id="postFinding",
        tags=["complaints"],
    )
    def post_finding(complaint_id: str, body: FindingIn, principal: Writer) -> ReviewTask | None:
        """Record a perception finding; a dismissive one opens a human-review task."""
        require_known(complaint_id)
        try:
            provenance = Provenance(
                source=body.source,
                actor=principal.actor_id,
                model=body.model,
                prompt_version=body.prompt_version,
                span=body.span,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        task = review_task_for_finding(
            PerceptionFinding(
                finding_id=body.finding_id,
                complaint_id=complaint_id,
                kind=body.kind,
                provenance=provenance,
                found_at=now(),
                detail=body.detail,
            )
        )
        if task is not None:
            store.add_review_task(task)
        return task

    @api.get("/complaints", operation_id="listComplaints", tags=["complaints"])
    def list_complaints(principal: Reader, as_of: AsOf = None) -> list[ComplaintSummary]:
        """Complaints with their next deadline, for the deadline board."""
        at = _as_of(principal, as_of, now)
        out: list[ComplaintSummary] = []
        for cid in store.complaint_ids():
            events = _known(store.events(cid), at)
            if not events:
                continue
            facts = fold_events(cid, events)
            records = evaluate_stored(events, ctx, cid, at)
            open_ = [
                r
                for r in records
                if r.deadline is not None
                and r.result in (DecisionResult.RUNNING, DecisionResult.BREACHED)
            ]
            due = [(r.deadline.due_date, r.obligation_id, r) for r in open_ if r.deadline]
            nxt = min(due, key=lambda d: (d[0], d[1]))[2] if due else None
            out.append(
                ComplaintSummary(
                    complaint_id=cid,
                    channel=facts.channel.value if facts.channel else None,
                    obligation_ids=[r.obligation_id for r in records if r.result in _TRIGGERED],
                    next_deadline=(
                        NextDeadline(
                            obligation_id=nxt.obligation_id,
                            due_date=nxt.deadline.due_date,
                            result=nxt.result,
                        )
                        if nxt is not None and nxt.deadline is not None
                        else None
                    ),
                    open_breaches=sum(r.result is DecisionResult.BREACHED for r in records),
                )
            )
        return out

    @api.get("/complaints/{complaint_id}", operation_id="getComplaint", tags=["complaints"])
    def get_complaint(complaint_id: str, principal: Reader, as_of: AsOf = None) -> ComplaintDetail:
        """One complaint: facts, deadlines, breaches, required actions and chain status."""
        return detail(complaint_id, _as_of(principal, as_of, now))

    @api.get("/complaints/{complaint_id}/closure", operation_id="checkClosure", tags=["complaints"])
    def check_closure(
        complaint_id: str,
        principal: Reader,
        unit: Annotated[str, Query(min_length=1, description="Unit that would close it.")],
        as_of: AsOf = None,
    ) -> ClosureCheck:
        """Whether ``unit`` may close the complaint now, with every reason it may not."""
        at = _as_of(principal, as_of, now)
        facts = fold_events(complaint_id, _known(require_known(complaint_id), at))
        gate = can_close(facts, Actor(actor_id=principal.actor_id, unit=unit))
        return ClosureCheck(complaint_id=complaint_id, unit=unit, gate=gate, allowed=gate.allowed)

    @api.get(
        "/complaints/{complaint_id}/decisions",
        operation_id="listDecisions",
        tags=["decisions"],
    )
    def list_decisions(complaint_id: str, principal: Reader, as_of: AsOf = None) -> DecisionChain:
        """The complaint's stored, hash-chained decision records and their verification."""
        at = _as_of(principal, as_of, now)
        require_known(complaint_id)
        chain = _chain_upto(store.decisions(complaint_id), at)
        return DecisionChain(complaint_id=complaint_id, records=chain, chain=verify_chain(chain))

    @api.get(
        "/complaints/{complaint_id}/decisions/{obligation_id}",
        operation_id="getDecision",
        tags=["decisions"],
    )
    def get_decision(
        complaint_id: str, obligation_id: str, principal: Reader, as_of: AsOf = None
    ) -> DecisionReplay:
        """The latest stored decision record for one obligation on one complaint."""
        at = _as_of(principal, as_of, now)
        chain = _chain_upto(store.decisions(complaint_id), at)
        hits = [i for i, r in enumerate(chain) if r.obligation_id == obligation_id]
        if not hits:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"no decision for {obligation_id} on {complaint_id}"
            )
        return DecisionReplay(record=chain[hits[-1]], position=hits[-1], chain=verify_chain(chain))

    @api.get("/decisions/{decision_id}/explain", operation_id="explainDecision", tags=["decisions"])
    def explain_decision(decision_id: str, principal: Reader) -> Explanation:
        """A stored decision rendered as text from the record itself."""
        record = store.decision(decision_id)
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown decision {decision_id}")
        chain = store.decisions(record.complaint_id)
        position = next(i for i, r in enumerate(chain) if r.hash == decision_id)
        status_: ChainStatus = verify_chain(chain[: position + 1])
        return Explanation(
            decision_id=decision_id,
            complaint_id=record.complaint_id,
            obligation_id=record.obligation_id,
            position=position,
            chain=status_,
            lines=render_explanation(record),
        )

    @api.get("/obligations", operation_id="listObligations", tags=["rules"])
    def list_obligations(principal: Reader) -> list[Obligation]:
        """Every obligation in the loaded rule pack."""
        return list(ctx.obligations)

    @api.get("/board/deadlines", operation_id="boardDeadlines", tags=["board"])
    def board_deadlines(
        principal: Reader,
        within_days: Annotated[int, Query(ge=0, le=366)] = 7,
        as_of: AsOf = None,
    ) -> list[ForecastItem]:
        """Running deadlines due within ``within_days`` calendar days, soonest first."""
        at = _as_of(principal, as_of, now)
        records: list[DecisionRecord] = []
        for cid in store.complaint_ids():
            events = _known(store.events(cid), at)
            if events:
                records.extend(evaluate_stored(events, ctx, cid, at))
        return forecast_records(records, at, within_days)

    @api.get("/review-tasks", operation_id="listReviewTasks", tags=["review"])
    def list_review_tasks(
        principal: Reader,
        complaint_id: str | None = None,
        task_status: Annotated[ReviewStatus | None, Query(alias="status")] = None,
    ) -> list[ReviewTask]:
        """Human-review tasks, optionally for one complaint or one status."""
        return store.review_tasks(complaint_id, task_status)


app = create_app()
"""The process-wide app, configured from the environment."""
