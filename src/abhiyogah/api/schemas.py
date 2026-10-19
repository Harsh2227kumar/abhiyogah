"""Request and response bodies. Responses reuse the domain models so the console's generated types
match the engine's own (``make openapi``)."""

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.decision import (
    Breach,
    Compensation,
    Deadline,
    DecisionRecord,
    DecisionResult,
    RequiredAction,
)
from abhiyogah.domain.enums import Channel, FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, TextSpan
from abhiyogah.ledger import ChainStatus
from abhiyogah.workflow import FindingKind, GateResult, ReviewTask

__all__ = [
    "ActionItem",
    "BreachItem",
    "ComplaintDetail",
    "ComplaintSummary",
    "DeadlineItem",
    "DecisionChain",
    "DecisionReplay",
    "EventIn",
    "EventsAccepted",
    "EventsIn",
    "Explanation",
    "FindingIn",
    "NextDeadline",
]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EventIn(_Model):
    """A business event as a client sends it. The server sets ``recorded_at`` and the actor."""

    event_id: str = Field(min_length=1, description="Client-chosen, unique; re-sending is a no-op.")
    type: EventType
    occurred_at: AwareDatetime
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    source: FactSource = FactSource.HUMAN
    model: str | None = Field(default=None, description="Model identifier, for LLM facts.")
    prompt_version: str | None = None
    span: TextSpan | None = None


class EventsIn(_Model):
    """One or more events for one complaint."""

    events: list[EventIn] = Field(min_length=1)


class EventsAccepted(_Model):
    """What a POST of events did."""

    accepted: list[str] = Field(description="Event IDs stored now.")
    already_recorded: list[str] = Field(description="Event IDs that were already stored.")
    decisions_appended: int = Field(ge=0)
    review_tasks_opened: list[str] = Field(default_factory=list)
    evaluation_error: str | None = Field(
        default=None,
        description="Set when the events were stored but the engine could not re-evaluate.",
    )


class FindingIn(_Model):
    """A perception finding (classification) about a complaint."""

    finding_id: str = Field(min_length=1)
    kind: FindingKind
    source: FactSource = FactSource.LLM
    model: str | None = None
    prompt_version: str | None = None
    span: TextSpan | None = None
    detail: str = ""


class NextDeadline(_Model):
    """The earliest open deadline on a complaint."""

    obligation_id: str
    due_date: date
    result: DecisionResult


class ComplaintSummary(_Model):
    """One row of the deadline board."""

    complaint_id: str
    channel: Channel | None = None
    obligation_ids: list[str] = Field(
        description="Obligations triggered on this complaint (applicable and triggered)."
    )
    next_deadline: NextDeadline | None = None
    open_breaches: int = Field(ge=0)


class DeadlineItem(_Model):
    """A computed deadline and the state of its clock."""

    obligation_id: str
    clause: str
    result: DecisionResult
    deadline: Deadline


class BreachItem(_Model):
    """A breach and any compensation it carries."""

    clause: str
    breach: Breach
    compensation: Compensation | None = None


class ActionItem(_Model):
    """A required action, from an obligation's clock or from a workflow gate."""

    source: str = Field(description="'EVALUATOR' or 'WORKFLOW'.")
    obligation_id: str | None = None
    action: RequiredAction


class ComplaintDetail(_Model):
    """Everything the complaint view shows, as evaluated at ``as_of``.

    ``decisions`` is the evaluation at ``as_of`` (unsealed; a read never writes). The stored,
    hash-chained records are under ``/complaints/{id}/decisions``; ``chain`` is their status.
    """

    complaint_id: str
    as_of: AwareDatetime
    events: list[ComplaintEvent]
    facts: ComplaintFacts
    decisions: list[DecisionRecord]
    deadlines: list[DeadlineItem]
    breaches: list[BreachItem]
    required_actions: list[ActionItem]
    review_tasks: list[ReviewTask]
    chain: ChainStatus


class DecisionChain(_Model):
    """A complaint's stored decision records and the status of their chain."""

    complaint_id: str
    records: list[DecisionRecord]
    chain: ChainStatus


class DecisionReplay(_Model):
    """One decision record and the status of the chain it belongs to."""

    record: DecisionRecord
    position: int = Field(ge=0, description="Index of the record in the complaint's chain.")
    chain: ChainStatus


class Explanation(_Model):
    """A stored decision rendered as text, line by line."""

    decision_id: str = Field(description="The record's hash.")
    complaint_id: str
    obligation_id: str
    position: int = Field(ge=0)
    chain: ChainStatus
    lines: list[str]


class ClosureCheck(_Model):
    """Whether a unit may close the complaint now (A14, A15)."""

    complaint_id: str
    unit: str
    gate: GateResult
    allowed: bool
