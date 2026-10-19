"""RBI-native complaint facts, derived by folding a complaint's business events.

``ComplaintFacts`` is the data dictionary the evaluator reads. Every field is optional (a fact may
not be known yet) and every known value is a ``Fact`` that carries its provenance and the event it
came from, so a decision record can cite exactly which evidence it used.

Folding rules (see ``fold_events``):

1. Only events recorded at or before ``known_at`` count (bitemporal replay); the rest are ignored.
2. Events are applied in ``(recorded_at, occurred_at, event_id)`` order, so a later-recorded event
   corrects an earlier one. Nothing is edited; the correction is just a newer fact.
3. Lifecycle events set a date fact from ``occurred_at``, converted to the Asia/Kolkata date
   (``EVENT_DATE_FACTS``). ``last_bank_communication_date`` keeps the latest such date instead.
4. Any payload key equal to a ``ComplaintFacts`` field name sets that fact, on any event type
   (``FACTS_RECORDED`` exists for facts that arrive on their own). Other payload keys are ignored.
5. ``OUTCOME_SET`` must carry ``payload["outcome"]``.
"""

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from abhiyogah.domain.enums import AccountType, Channel, EntityType, Outcome
from abhiyogah.domain.errors import FactFoldError
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance
from abhiyogah.domain.money import Paise
from abhiyogah.domain.tz import ist_date

__all__ = ["EVENT_DATE_FACTS", "ComplaintFacts", "Fact", "fold_events"]


class Fact[T](BaseModel):
    """A known value plus where it came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: T
    provenance: Provenance
    event_id: str = Field(description="The event that asserted this value.")
    recorded_at: AwareDatetime = Field(description="When the engine learned this value.")


class ComplaintFacts(BaseModel):
    """What the engine knows about one complaint. Dates are Asia/Kolkata calendar dates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    complaint_id: str

    # Bank stage
    bank_receipt_date: Fact[date] | None = None
    acknowledged_date: Fact[date] | None = None
    info_requested_date: Fact[date] | None = None
    outcome: Fact[Outcome] | None = None
    outcome_date: Fact[date] | None = None
    io_referred_date: Fact[date] | None = None
    io_decided_date: Fact[date] | None = None
    final_reply_date: Fact[date] | None = None
    last_bank_communication_date: Fact[date] | None = None
    customer_dissatisfied_date: Fact[date] | None = None

    # Ombudsman stage
    rbi_receipt_date: Fact[date] | None = None
    rbio_direction_date: Fact[date] | None = None
    written_response_date: Fact[date] | None = None
    award_received_date: Fact[date] | None = None
    acceptance_letter_date: Fact[date] | None = None
    compliance_intimated_date: Fact[date] | None = None
    appeal_filed_date: Fact[date] | None = None

    # Transactions, unauthorised and failed (RBC-CB paras 66-73, TAT circular)
    transaction_date_t: Fact[date] | None = None
    reversal_date_r: Fact[date] | None = None
    alert_received_date: Fact[date] | None = None
    customer_reported_date: Fact[date] | None = None
    shadow_credit_date: Fact[date] | None = None
    liability_determined_date: Fact[date] | None = None
    channel: Fact[Channel] | None = None
    account_type: Fact[AccountType] | None = None
    amount_paise: Fact[Paise] | None = None

    # Service events (RBC-CB Table C)
    all_documents_received_date: Fact[date] | None = None
    claim_settled_date: Fact[date] | None = None
    full_repayment_date: Fact[date] | None = None
    documents_released_date: Fact[date] | None = None

    # Profile and external inputs
    home_branch_state: Fact[str] | None = Field(
        default=None, description="Home branch state as an ISO 3166-2:IN code without 'IN-'."
    )
    entity_type: Fact[EntityType] | None = None
    external_tat_days: Fact[int] | None = Field(
        default=None, description="RBI/NPCI/card-network TAT in days, when one applies (A2, A13)."
    )


EVENT_DATE_FACTS: dict[EventType, str] = {
    EventType.BANK_RECEIVED: "bank_receipt_date",
    EventType.ACKNOWLEDGED: "acknowledged_date",
    EventType.INFO_REQUESTED: "info_requested_date",
    EventType.OUTCOME_SET: "outcome_date",
    EventType.IO_REFERRED: "io_referred_date",
    EventType.IO_DECIDED: "io_decided_date",
    EventType.FINAL_REPLY_SENT: "final_reply_date",
    EventType.CUSTOMER_DISSATISFIED: "customer_dissatisfied_date",
    EventType.RBI_RECEIVED: "rbi_receipt_date",
    EventType.RBIO_DIRECTION_RECEIVED: "rbio_direction_date",
    EventType.WRITTEN_RESPONSE_FILED: "written_response_date",
    EventType.AWARD_RECEIVED: "award_received_date",
    EventType.ACCEPTANCE_LETTER_RECEIVED: "acceptance_letter_date",
    EventType.COMPLIANCE_INTIMATED: "compliance_intimated_date",
    EventType.APPEAL_FILED: "appeal_filed_date",
    EventType.REVERSAL_POSTED: "reversal_date_r",
    EventType.ALERT_RECEIVED: "alert_received_date",
    EventType.CUSTOMER_REPORTED: "customer_reported_date",
    EventType.SHADOW_CREDITED: "shadow_credit_date",
    EventType.LIABILITY_DETERMINED: "liability_determined_date",
    EventType.ALL_DOCUMENTS_RECEIVED: "all_documents_received_date",
    EventType.CLAIM_SETTLED: "claim_settled_date",
    EventType.FULL_REPAYMENT: "full_repayment_date",
    EventType.DOCUMENTS_RELEASED: "documents_released_date",
}
"""Which date fact each lifecycle event sets from its ``occurred_at``."""

_BANK_COMMUNICATIONS = frozenset({EventType.BANK_COMMUNICATION_SENT, EventType.FINAL_REPLY_SENT})

_FACT_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    name: TypeAdapter(info.annotation)
    for name, info in ComplaintFacts.model_fields.items()
    if name != "complaint_id" and info.annotation is not None
}


def _make_fact(name: str, value: object, ev: ComplaintEvent) -> Fact[Any]:
    """Validate ``value`` against the field's type and wrap it with the event's provenance."""
    try:
        fact = _FACT_ADAPTERS[name].validate_python(
            {
                "value": value,
                "provenance": ev.provenance,
                "event_id": ev.event_id,
                "recorded_at": ev.recorded_at,
            }
        )
    except ValidationError as exc:
        raise FactFoldError(f"event {ev.event_id}: bad value for {name!r}: {value!r}") from exc
    if not isinstance(fact, Fact):
        raise FactFoldError(f"event {ev.event_id}: {name!r} cannot be null")
    return fact


def fold_events(
    complaint_id: str,
    events: Iterable[ComplaintEvent],
    known_at: datetime | None = None,
) -> ComplaintFacts:
    """Fold a complaint's events into ``ComplaintFacts`` as known at ``known_at`` (default: all)."""
    selected: list[ComplaintEvent] = []
    for ev in events:
        if ev.complaint_id != complaint_id:
            raise FactFoldError(f"event {ev.event_id} belongs to complaint {ev.complaint_id}")
        if known_at is None or ev.recorded_at <= known_at:
            selected.append(ev)
    selected.sort(key=lambda e: (e.recorded_at, e.occurred_at, e.event_id))

    facts: dict[str, Fact[Any]] = {}
    for ev in selected:
        day = ist_date(ev.occurred_at)
        date_field = EVENT_DATE_FACTS.get(ev.type)
        if date_field is not None:
            facts[date_field] = _make_fact(date_field, day, ev)
        if ev.type in _BANK_COMMUNICATIONS:
            prev = facts.get("last_bank_communication_date")
            if prev is None or day >= prev.value:
                facts["last_bank_communication_date"] = _make_fact(
                    "last_bank_communication_date", day, ev
                )
        if ev.type is EventType.OUTCOME_SET and "outcome" not in ev.payload:
            raise FactFoldError(f"event {ev.event_id}: OUTCOME_SET needs payload['outcome']")
        for key, value in ev.payload.items():
            if key in _FACT_ADAPTERS:
                facts[key] = _make_fact(key, value, ev)

    return ComplaintFacts.model_validate({"complaint_id": complaint_id, **facts})
