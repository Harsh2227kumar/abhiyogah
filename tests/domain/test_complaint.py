"""Folding ComplaintEvents into ComplaintFacts."""

from datetime import date, timedelta

import pytest

from abhiyogah.domain.complaint import ComplaintFacts, fold_events
from abhiyogah.domain.enums import Channel, FactSource, Outcome
from abhiyogah.domain.errors import FactFoldError
from abhiyogah.domain.events import EventType
from tests.domain.factories import LLM, SYSTEM, event, utc

CID = "CMP-TEST-1"


def test_no_events_gives_empty_facts() -> None:
    """With no events, nothing is known."""
    facts = fold_events(CID, [])
    assert facts == ComplaintFacts(complaint_id=CID)


def test_dates_use_ist_calendar_day() -> None:
    """20:00 UTC on 31 Jul is 1 Aug in Asia/Kolkata."""
    facts = fold_events(CID, [event(1, EventType.BANK_RECEIVED, utc(2026, 7, 31, 20))])
    assert facts.bank_receipt_date is not None
    assert facts.bank_receipt_date.value == date(2026, 8, 1)
    assert facts.bank_receipt_date.event_id == "EV-1"


def test_outcome_and_payload_facts_carry_provenance() -> None:
    """Payload keys that name facts are folded with the event's provenance."""
    events = [
        event(1, EventType.BANK_RECEIVED, utc(2026, 8, 1), {"channel": "UPI_P2P"}, SYSTEM),
        event(2, EventType.OUTCOME_SET, utc(2026, 8, 5), {"outcome": "WHOLLY_REJECTED"}),
        event(3, EventType.FACTS_RECORDED, utc(2026, 8, 2), {"amount_paise": 250_000}, LLM),
    ]
    facts = fold_events(CID, events)
    assert facts.channel is not None
    assert facts.channel.value is Channel.UPI_P2P
    assert facts.channel.provenance.source is FactSource.SYSTEM
    assert facts.outcome is not None
    assert facts.outcome.value is Outcome.WHOLLY_REJECTED
    assert facts.outcome_date is not None
    assert facts.outcome_date.value == date(2026, 8, 5)
    assert facts.amount_paise is not None
    assert facts.amount_paise.value == 250_000
    assert facts.amount_paise.provenance.model == "test-model"


def test_later_recorded_event_corrects_earlier() -> None:
    """A correction is a newer event; the newest recorded value wins."""
    first = event(1, EventType.FACTS_RECORDED, utc(2026, 8, 1), {"channel": "IMPS"})
    second = event(2, EventType.FACTS_RECORDED, utc(2026, 8, 3), {"channel": "UPI_P2P"})
    facts = fold_events(CID, [second, first])
    assert facts.channel is not None
    assert facts.channel.value is Channel.UPI_P2P


def test_known_at_replays_the_past() -> None:
    """Events recorded after known_at are invisible."""
    events = [
        event(1, EventType.BANK_RECEIVED, utc(2026, 8, 1)),
        event(2, EventType.IO_REFERRED, utc(2026, 8, 15)),
    ]
    facts = fold_events(CID, events, known_at=utc(2026, 8, 10))
    assert facts.bank_receipt_date is not None
    assert facts.io_referred_date is None


def test_last_bank_communication_keeps_latest_date() -> None:
    """The A3 anchor is the latest bank communication, whatever the recording order."""
    late = event(1, EventType.BANK_COMMUNICATION_SENT, utc(2026, 8, 20))
    early = event(2, EventType.FINAL_REPLY_SENT, utc(2026, 8, 10))
    early = early.model_copy(update={"recorded_at": utc(2026, 8, 25)})
    facts = fold_events(CID, [late, early])
    assert facts.last_bank_communication_date is not None
    assert facts.last_bank_communication_date.value == date(2026, 8, 20)
    assert facts.final_reply_date is not None
    assert facts.final_reply_date.value == date(2026, 8, 10)


def test_outcome_set_requires_outcome() -> None:
    """OUTCOME_SET without an outcome is malformed."""
    with pytest.raises(FactFoldError):
        fold_events(CID, [event(1, EventType.OUTCOME_SET, utc(2026, 8, 1))])


def test_bad_fact_value_is_rejected() -> None:
    """A payload value of the wrong type raises a typed error."""
    with pytest.raises(FactFoldError):
        fold_events(CID, [event(1, EventType.FACTS_RECORDED, utc(2026, 8, 1), {"channel": "FAX"})])


def test_other_complaints_events_are_rejected() -> None:
    """Events from another complaint are an error, not silently mixed in."""
    other = event(1, EventType.BANK_RECEIVED, utc(2026, 8, 1), complaint_id="CMP-OTHER")
    with pytest.raises(FactFoldError):
        fold_events(CID, [other])


def test_unknown_payload_keys_are_ignored() -> None:
    """Payload keys that are not facts stay on the event only."""
    ev = event(1, EventType.ACKNOWLEDGED, utc(2026, 8, 1), {"note": "ack sent by SMS"})
    facts = fold_events(CID, [ev])
    assert facts.acknowledged_date is not None
    assert facts.acknowledged_date.recorded_at == utc(2026, 8, 1) + timedelta(seconds=1)
