"""Decision records: the replayable, hash-chained output of every obligation evaluation.

One ``DecisionRecord`` is written per obligation evaluated on a complaint (report section "Every
decision leaves a record that can be replayed"). It holds everything needed to reproduce and explain
the result: the obligation version and clause, the anchor date that selected the parameter version,
each input fact with its provenance, the per-condition trace, the computed deadline, the calendar
version, the result, any outputs the obligation determined (``outputs``) and any compensation with
its formula. Explanations are rendered from these records, never regenerated.

Records are chained: ``hash`` is the SHA-256 of ``prev_hash`` plus the record's canonical JSON
(``canonical_json``), so any edit to a past record breaks every later hash. Use ``seal`` to compute
the hash and ``verify_chain`` to check a sequence.
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from abhiyogah.domain.enums import BasisStatus, DayBasis, Verification
from abhiyogah.domain.events import EventType, Provenance
from abhiyogah.domain.money import Paise

__all__ = [
    "GENESIS_HASH",
    "Breach",
    "Compensation",
    "ConditionTrace",
    "Deadline",
    "DecisionRecord",
    "DecisionResult",
    "InputFact",
    "ParameterUse",
    "RequiredAction",
    "verify_chain",
]

GENESIS_HASH = "0" * 64
"""``prev_hash`` of the first record in a chain."""


class DecisionResult(StrEnum):
    """Outcome of evaluating one obligation on one complaint at ``as_of``."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    """The entity profile or validity dates exclude this obligation."""
    NOT_TRIGGERED = "NOT_TRIGGERED"
    """The trigger event or condition has not occurred."""
    INSUFFICIENT_FACTS = "INSUFFICIENT_FACTS"
    """A fact the obligation needs is unknown; nothing was assumed."""
    RUNNING = "RUNNING"
    STOPPED_ON_TIME = "STOPPED_ON_TIME"
    STOPPED_LATE = "STOPPED_LATE"
    BREACHED = "BREACHED"
    """The deadline passed at ``as_of`` without the stop event."""
    DETERMINED = "DETERMINED"
    """A clock-less obligation (router, classification, check, tier) produced its outputs."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class InputFact(_Frozen):
    """One fact the evaluation read, with where it came from."""

    name: str
    value: JsonValue
    provenance: Provenance
    event_id: str | None = None


class ParameterUse(_Frozen):
    """A dated rule parameter resolved for this evaluation."""

    name: str
    value: JsonValue
    effective_date: date
    reference: str
    verification: Verification


class ConditionTrace(_Frozen):
    """One condition checked, in order, and its result."""

    condition: str = Field(description="What was checked, e.g. 'outcome in [...]'.")
    result: bool
    detail: str = ""


class Deadline(_Frozen):
    """A computed deadline; ``due_date`` is the last IST day on which stopping is on time."""

    due_date: date
    basis: DayBasis
    basis_status: BasisStatus
    start_event: EventType
    stop_event: EventType | None
    start_date: date | None = None
    duration_days: int | None = Field(default=None, ge=0)
    rule: str = Field(default="", description="How it was derived, e.g. 'start + 20d'.")


class Breach(_Frozen):
    """A deadline missed: no stop by ``due_date``, or a stop after it."""

    obligation_id: str
    due_date: date
    stop_date: date | None = Field(default=None, description="When the stop event came, if late.")
    days_late: int = Field(ge=1, description="Days past due_date at stop_date or as_of.")


class Compensation(_Frozen):
    """Money owed, with the formula and inputs that produced it."""

    amount_paise: Paise = Field(ge=0)
    formula: str = Field(description="E.g. '100 x max(0, R - (T + n))' rupees.")
    inputs: dict[str, JsonValue] = Field(default_factory=dict)


class RequiredAction(_Frozen):
    """Something the bank must do next, with its due date."""

    action: str = Field(description="UPPER_SNAKE action code, e.g. 'REFER_TO_IO'.")
    due_date: date | None = None
    reason: str = ""


class DecisionRecord(_Frozen):
    """The replayable record of one obligation evaluation. See the module docstring."""

    complaint_id: str
    obligation_id: str
    obligation_version: str = Field(description="Rule-pack version or file hash of the obligation.")
    clause: str
    anchor_date: date | None = Field(description="Date used to select parameter versions.")
    as_of: AwareDatetime
    input_facts: list[InputFact] = Field(default_factory=list)
    parameters: list[ParameterUse] = Field(default_factory=list)
    condition_trace: list[ConditionTrace] = Field(default_factory=list)
    deadline: Deadline | None = None
    calendar_version: str | None = None
    result: DecisionResult
    breach: Breach | None = None
    compensation: Compensation | None = None
    required_actions: list[RequiredAction] = Field(default_factory=list)
    outputs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Values the obligation determined, by output name (e.g. 'scheme').",
    )
    prev_hash: str = Field(default=GENESIS_HASH, pattern=r"^[0-9a-f]{64}$")
    hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def canonical_json(self) -> str:
        """Deterministic JSON of every field except ``hash`` (sorted keys, no whitespace)."""
        data = self.model_dump(mode="json", exclude={"hash"})
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def compute_hash(self) -> str:
        """SHA-256 over ``prev_hash`` and the canonical JSON."""
        payload = (self.prev_hash + self.canonical_json()).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def seal(self, prev_hash: str = GENESIS_HASH) -> Self:
        """Return a copy chained after ``prev_hash`` with its ``hash`` set."""
        chained = self.model_copy(update={"prev_hash": prev_hash, "hash": None})
        return chained.model_copy(update={"hash": chained.compute_hash()})


def verify_chain(records: Sequence[DecisionRecord], start: str = GENESIS_HASH) -> bool:
    """True if every record is sealed, links to its predecessor and has an untampered hash."""
    prev = start
    for record in records:
        if record.prev_hash != prev or record.hash is None or record.hash != record.compute_hash():
            return False
        prev = record.hash
    return True
