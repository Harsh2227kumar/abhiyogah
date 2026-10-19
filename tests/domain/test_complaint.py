"""Folding ComplaintEvents into ComplaintFacts."""

from datetime import date, timedelta

import pytest
from pydantic import JsonValue

from abhiyogah.domain.complaint import ComplaintFacts, fold_events
from abhiyogah.domain.enums import (
    Appellant,
    Channel,
    FactSource,
    IssueType,
    LiabilityFault,
    Outcome,
)
from abhiyogah.domain.errors import FactFoldError
from abhiyogah.domain.events import EventType, Provenance
from tests.domain.factories import HUMAN, LLM, SYSTEM, event, utc

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


def test_rule_pack_facts_fold_from_payloads() -> None:
    """The facts requested in issue #20 fold from payloads with their types."""
    events = [
        event(
            1,
            EventType.FACTS_RECORDED,
            utc(2026, 8, 1, 6),
            {
                "issue_type": "UNAUTHORISED_TRANSACTION",
                "channel": "AEPS_BENEFICIARY",
                "exclusion_category": "14_5_c",
                "handling_unit": "BR-0001",
                "closing_unit": "GRC-TEST",
            },
        ),
        event(2, EventType.IO_DECIDED, utc(2026, 8, 2, 6), {"io_upheld": True}),
        event(
            3,
            EventType.FACTS_RECORDED,
            utc(2026, 8, 3, 6),
            {"reply_elements": ["ELEMENT_B", "ELEMENT_A"], "liability_fault": "THIRD_PARTY"},
        ),
        event(4, EventType.APPEAL_FILED, utc(2026, 8, 4, 6), {"appellant": "BANK"}),
    ]
    facts = fold_events("CMP-TEST-1", events)
    assert facts.issue_type is not None
    assert facts.issue_type.value is IssueType.UNAUTHORISED_TRANSACTION
    assert facts.channel is not None
    assert facts.channel.value is Channel.AEPS_BENEFICIARY
    assert facts.exclusion_category is not None
    assert facts.exclusion_category.value == "14_5_c"
    assert facts.handling_unit is not None
    assert facts.handling_unit.value == "BR-0001"
    assert facts.closing_unit is not None
    assert facts.closing_unit.value == "GRC-TEST"
    assert facts.io_upheld is not None
    assert facts.io_upheld.value is True
    assert facts.io_upheld.event_id == "EV-2"
    assert facts.reply_elements is not None
    assert facts.reply_elements.value == ["ELEMENT_B", "ELEMENT_A"]
    assert facts.liability_fault is not None
    assert facts.liability_fault.value is LiabilityFault.THIRD_PARTY
    assert facts.appellant is not None
    assert facts.appellant.value is Appellant.BANK
    assert facts.appeal_filed_date is not None


def test_senior_reviewed_sets_senior_review_date() -> None:
    """SENIOR_REVIEWED sets senior_review_date from its IST occurred date (A15)."""
    facts = fold_events("CMP-TEST-1", [event(1, EventType.SENIOR_REVIEWED, utc(2026, 8, 11, 19))])
    assert facts.senior_review_date is not None
    assert facts.senior_review_date.value == date(2026, 8, 12)


@pytest.mark.parametrize("bad", ["14_5_f", "14(5)(a)", "a"])
def test_exclusion_category_must_be_a_cl_14_5_limb(bad: str) -> None:
    """Only 14_5_a to 14_5_e are accepted."""
    with pytest.raises(FactFoldError):
        fold_events(
            "CMP-TEST-1",
            [event(1, EventType.FACTS_RECORDED, utc(2026, 8, 1), {"exclusion_category": bad})],
        )


@pytest.mark.parametrize("provenance", [LLM, SYSTEM])
def test_liability_fault_only_from_a_human(provenance: Provenance) -> None:
    """An LLM or system feed never sets liability_fault (hard rule 4)."""
    payload: dict[str, JsonValue] = {"liability_fault": "CUSTOMER"}
    with pytest.raises(FactFoldError, match="HUMAN"):
        fold_events(
            "CMP-TEST-1",
            [event(1, EventType.FACTS_RECORDED, utc(2026, 8, 1), payload, provenance)],
        )
    ok = fold_events(
        "CMP-TEST-1",
        [event(1, EventType.FACTS_RECORDED, utc(2026, 8, 1), payload, HUMAN)],
    )
    assert ok.liability_fault is not None
