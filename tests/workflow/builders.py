"""Synthetic complaint facts for workflow tests. No real customer data."""

from datetime import UTC, date, datetime, timedelta

from pydantic import JsonValue

from abhiyogah.domain.complaint import ComplaintFacts, fold_events
from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance

CID = "CMP-WF-1"
OFFICER = Provenance(source=FactSource.HUMAN, actor="officer-001")


def ev(
    n: int, type_: EventType, d: date, payload: dict[str, JsonValue] | None = None
) -> ComplaintEvent:
    """A synthetic human-entered event on ``CID``."""
    occurred = datetime(d.year, d.month, d.day, 6, tzinfo=UTC)
    return ComplaintEvent(
        event_id=f"WF-{n}",
        complaint_id=CID,
        type=type_,
        occurred_at=occurred,
        recorded_at=occurred + timedelta(minutes=1),
        payload=payload or {},
        provenance=OFFICER,
    )


def facts(*events: ComplaintEvent) -> ComplaintFacts:
    """Fold the events into facts."""
    return fold_events(CID, events)


RECEIVED = ev(1, EventType.BANK_RECEIVED, date(2026, 8, 3), {"handling_unit": "BRANCH-042"})


def outcome(value: str, n: int = 2, d: date = date(2026, 8, 10)) -> ComplaintEvent:
    """An OUTCOME_SET event."""
    return ev(n, EventType.OUTCOME_SET, d, {"outcome": value})


def exclusion(category: str, n: int = 9) -> ComplaintEvent:
    """A FACTS_RECORDED event setting the cl. 14(5) exclusion limb."""
    return ev(n, EventType.FACTS_RECORDED, date(2026, 8, 4), {"exclusion_category": category})
