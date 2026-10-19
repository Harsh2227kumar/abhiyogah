"""Business events on a complaint, and the provenance every fact carries.

Events are append-only evidence (CLAUDE.md hard rules 6 and 7). Each event records both when it
happened in the business (``occurred_at``) and when the system learned of it (``recorded_at``), so
the store is bitemporal and evaluations can be replayed as of any moment. A correction is a new
event, never an edit of an old one.
"""

from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from abhiyogah.domain.enums import FactSource

__all__ = ["ComplaintEvent", "EventType", "Provenance", "TextSpan"]


class EventType(StrEnum):
    """Business event types (report architecture diagram [3] and clock table)."""

    # Bank-stage lifecycle (RB-IOS 2026, IO Directions 2026)
    BANK_RECEIVED = "BANK_RECEIVED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INFO_REQUESTED = "INFO_REQUESTED"
    OUTCOME_SET = "OUTCOME_SET"
    IO_REFERRED = "IO_REFERRED"
    IO_DECIDED = "IO_DECIDED"
    FINAL_REPLY_SENT = "FINAL_REPLY_SENT"
    BANK_COMMUNICATION_SENT = "BANK_COMMUNICATION_SENT"
    """Any bank communication to the complainant; the latest one feeds the A3 filing window."""
    CUSTOMER_DISSATISFIED = "CUSTOMER_DISSATISFIED"
    """Complainant states dissatisfaction with the bank's reply (A2)."""

    # Unauthorised transactions and failed transactions (RBC-CB paras 66-73, TAT circular)
    CUSTOMER_REPORTED = "CUSTOMER_REPORTED"
    ALERT_RECEIVED = "ALERT_RECEIVED"
    SHADOW_CREDITED = "SHADOW_CREDITED"
    REVERSAL_POSTED = "REVERSAL_POSTED"
    LIABILITY_DETERMINED = "LIABILITY_DETERMINED"

    # Ombudsman stage (RB-IOS 2026)
    RBI_RECEIVED = "RBI_RECEIVED"
    RBIO_DIRECTION_RECEIVED = "RBIO_DIRECTION_RECEIVED"
    WRITTEN_RESPONSE_FILED = "WRITTEN_RESPONSE_FILED"
    AWARD_RECEIVED = "AWARD_RECEIVED"
    ACCEPTANCE_LETTER_RECEIVED = "ACCEPTANCE_LETTER_RECEIVED"
    COMPLIANCE_INTIMATED = "COMPLIANCE_INTIMATED"
    APPEAL_FILED = "APPEAL_FILED"

    # Service events (RBC-CB Table C)
    ALL_DOCUMENTS_RECEIVED = "ALL_DOCUMENTS_RECEIVED"
    CLAIM_SETTLED = "CLAIM_SETTLED"
    FULL_REPAYMENT = "FULL_REPAYMENT"
    DOCUMENTS_RELEASED = "DOCUMENTS_RELEASED"

    # Facts about the complaint that are not lifecycle steps
    FACTS_RECORDED = "FACTS_RECORDED"
    """Asserts or corrects complaint facts (channel, amount, T, ...) carried in the payload."""


class TextSpan(BaseModel):
    """A character span in a source document that an extracted fact came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_ref: str = Field(min_length=1, description="ID or URI of the source text (masked).")
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        """A span must not end before it starts."""
        if self.end < self.start:
            raise ValueError("span end is before start")
        return self


class Provenance(BaseModel):
    """Where a fact came from: a person or system (``actor``), or an LLM (model, prompt, span)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: FactSource
    actor: str | None = Field(default=None, description="User or system ID for HUMAN/SYSTEM.")
    model: str | None = Field(default=None, description="Model identifier for LLM facts.")
    prompt_version: str | None = None
    span: TextSpan | None = None

    @model_validator(mode="after")
    def _complete(self) -> Self:
        """HUMAN/SYSTEM facts name an actor; LLM facts name the model and prompt version."""
        if self.source is FactSource.LLM:
            if not self.model or not self.prompt_version:
                raise ValueError("LLM provenance needs model and prompt_version")
        elif not self.actor:
            raise ValueError(f"{self.source} provenance needs an actor")
        return self


class ComplaintEvent(BaseModel):
    """One append-only business event on a complaint.

    ``occurred_at`` is business time (when it happened); ``recorded_at`` is system time (when the
    engine learned of it). Both must be timezone-aware. ``payload`` holds event-specific facts, for
    example ``{"outcome": "WHOLLY_REJECTED"}`` on ``OUTCOME_SET``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    complaint_id: str = Field(min_length=1)
    type: EventType
    occurred_at: AwareDatetime
    recorded_at: AwareDatetime
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    provenance: Provenance

    @property
    def source(self) -> FactSource:
        """Who asserted this event (shortcut for ``provenance.source``)."""
        return self.provenance.source
