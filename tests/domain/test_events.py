"""ComplaintEvent and Provenance validation."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance, TextSpan
from tests.domain.factories import HUMAN, LLM, event, utc


def test_event_round_trips_through_json() -> None:
    """An event survives JSON serialisation unchanged."""
    ev = event(1, EventType.OUTCOME_SET, utc(2026, 8, 1), {"outcome": "WHOLLY_REJECTED"}, LLM)
    assert ComplaintEvent.model_validate_json(ev.model_dump_json()) == ev
    assert ev.source is FactSource.LLM


def test_naive_datetime_is_rejected() -> None:
    """Datetimes must be timezone-aware."""
    with pytest.raises(ValidationError):
        ComplaintEvent(
            event_id="EV-1",
            complaint_id="CMP-1",
            type=EventType.BANK_RECEIVED,
            occurred_at=datetime(2026, 8, 1),  # noqa: DTZ001
            recorded_at=utc(2026, 8, 1),
            provenance=HUMAN,
        )


def test_events_are_immutable() -> None:
    """Evidence cannot be edited in place."""
    ev = event(1, EventType.BANK_RECEIVED, utc(2026, 8, 1))
    with pytest.raises(ValidationError):
        ev.type = EventType.ACKNOWLEDGED  # type: ignore[misc]


def test_llm_provenance_needs_model_and_prompt() -> None:
    """LLM facts must name the model and prompt version."""
    with pytest.raises(ValidationError):
        Provenance(source=FactSource.LLM, model="m")


@pytest.mark.parametrize("source", [FactSource.HUMAN, FactSource.SYSTEM])
def test_human_and_system_provenance_need_actor(source: FactSource) -> None:
    """Human and system facts must name an actor."""
    with pytest.raises(ValidationError):
        Provenance(source=source)


def test_span_end_not_before_start() -> None:
    """A span cannot end before it starts."""
    with pytest.raises(ValidationError):
        TextSpan(document_ref="d", start=5, end=4)


def test_required_event_types_exist() -> None:
    """Every event named in the task contract exists."""
    required = [
        "BANK_RECEIVED",
        "ACKNOWLEDGED",
        "INFO_REQUESTED",
        "OUTCOME_SET",
        "IO_REFERRED",
        "IO_DECIDED",
        "FINAL_REPLY_SENT",
        "CUSTOMER_REPORTED",
        "ALERT_RECEIVED",
        "SHADOW_CREDITED",
        "REVERSAL_POSTED",
        "LIABILITY_DETERMINED",
        "RBI_RECEIVED",
        "RBIO_DIRECTION_RECEIVED",
        "WRITTEN_RESPONSE_FILED",
        "AWARD_RECEIVED",
        "ACCEPTANCE_LETTER_RECEIVED",
        "COMPLIANCE_INTIMATED",
        "APPEAL_FILED",
        "ALL_DOCUMENTS_RECEIVED",
        "CLAIM_SETTLED",
        "FULL_REPAYMENT",
        "DOCUMENTS_RELEASED",
    ]
    assert set(required) <= {e.value for e in EventType}
