"""Synthetic event builders for domain tests. No real customer data."""

from datetime import UTC, datetime, timedelta

from pydantic import JsonValue

from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance, TextSpan

HUMAN = Provenance(source=FactSource.HUMAN, actor="officer-001")
SYSTEM = Provenance(source=FactSource.SYSTEM, actor="cbs-feed")
LLM = Provenance(
    source=FactSource.LLM,
    model="test-model",
    prompt_version="extract-v1",
    span=TextSpan(document_ref="doc-1", start=0, end=10),
)


def event(
    n: int,
    type_: EventType,
    occurred: datetime,
    payload: dict[str, JsonValue] | None = None,
    provenance: Provenance = HUMAN,
    complaint_id: str = "CMP-TEST-1",
) -> ComplaintEvent:
    """Build an event recorded one second after it occurred."""
    return ComplaintEvent(
        event_id=f"EV-{n}",
        complaint_id=complaint_id,
        type=type_,
        occurred_at=occurred,
        recorded_at=occurred + timedelta(seconds=1),
        payload=payload or {},
        provenance=provenance,
    )


def utc(y: int, m: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    """A timezone-aware UTC datetime."""
    return datetime(y, m, d, h, mi, tzinfo=UTC)
