"""DecisionRecord round-tripping and hash chaining."""

from datetime import date

import pytest
from pydantic import ValidationError

from abhiyogah.domain.decision import (
    GENESIS_HASH,
    Breach,
    Compensation,
    ConditionTrace,
    Deadline,
    DecisionRecord,
    DecisionResult,
    InputFact,
    ParameterUse,
    RequiredAction,
    verify_chain,
)
from abhiyogah.domain.enums import BasisStatus, DayBasis, Verification
from abhiyogah.domain.events import EventType
from abhiyogah.domain.money import Paise
from tests.domain.factories import HUMAN, utc


def make_record(result: DecisionResult = DecisionResult.BREACHED) -> DecisionRecord:
    """A fully populated synthetic record (values are test data, not rule values)."""
    return DecisionRecord(
        complaint_id="CMP-TEST-1",
        obligation_id="IO-CB-2026-14-1-b",
        obligation_version="test-v1",
        clause="14(1)(b)",
        anchor_date=date(2026, 8, 1),
        as_of=utc(2026, 8, 25),
        input_facts=[
            InputFact(
                name="bank_receipt_date", value="2026-08-01", provenance=HUMAN, event_id="EV-1"
            )
        ],
        parameters=[
            ParameterUse(
                name="max_days",
                value=20,
                effective_date=date(2026, 1, 14),
                reference="cl. 14(1)(b)",
                verification=Verification.PRIMARY_TEXT_READ,
            )
        ],
        condition_trace=[
            ConditionTrace(
                condition="outcome in [PARTIALLY_RESOLVED, WHOLLY_REJECTED]", result=True
            )
        ],
        deadline=Deadline(
            due_date=date(2026, 8, 21),
            basis=DayBasis.CALENDAR,
            basis_status=BasisStatus.INFERRED,
            start_event=EventType.BANK_RECEIVED,
            stop_event=EventType.IO_REFERRED,
            start_date=date(2026, 8, 1),
            duration_days=20,
            rule="start + max_days",
        ),
        calendar_version="test-calendar",
        result=result,
        breach=Breach(obligation_id="IO-CB-2026-14-1-b", due_date=date(2026, 8, 21), days_late=4),
        compensation=Compensation(amount_paise=Paise(0), formula="none"),
        required_actions=[RequiredAction(action="REFER_TO_IO", reason="overdue")],
    )


def test_round_trips_through_json() -> None:
    """A sealed record survives JSON serialisation unchanged and still verifies."""
    record = make_record().seal()
    again = DecisionRecord.model_validate_json(record.model_dump_json())
    assert again == record
    assert again.hash == again.compute_hash()


def test_canonical_json_is_stable() -> None:
    """Two identical records give byte-identical canonical JSON and hash."""
    assert make_record().canonical_json() == make_record().canonical_json()
    assert make_record().seal().hash == make_record().seal().hash


def test_chain_verifies_and_detects_tampering() -> None:
    """Editing any sealed record breaks the chain."""
    first = make_record().seal()
    assert first.hash is not None
    second = make_record(DecisionResult.RUNNING).seal(first.hash)
    assert first.prev_hash == GENESIS_HASH
    assert verify_chain([first, second])

    tampered = first.model_copy(update={"result": DecisionResult.STOPPED_ON_TIME})
    assert not verify_chain([tampered, second])
    assert not verify_chain([second, first])
    assert not verify_chain([make_record()])  # unsealed


def test_negative_compensation_is_rejected() -> None:
    """Compensation is never negative."""
    with pytest.raises(ValidationError):
        Compensation(amount_paise=Paise(-1), formula="x")


def test_determined_result_has_no_deadline_or_breach() -> None:
    """A clock-less obligation can end DETERMINED without a deadline (issue #20)."""
    record = make_record(DecisionResult.DETERMINED).model_copy(
        update={"deadline": None, "breach": None, "compensation": None}
    )
    assert DecisionRecord.model_validate_json(record.model_dump_json()) == record
    assert record.result.value == "DETERMINED"


def test_outputs_default_to_empty() -> None:
    """A record that determined nothing has no outputs (issue #25)."""
    assert make_record().outputs == {}


def test_outputs_round_trip_and_are_hashed() -> None:
    """Outputs survive JSON, are covered by the hash and do not depend on key order."""
    base = make_record(DecisionResult.DETERMINED)
    record = base.model_copy(
        update={"outputs": {"reply_complete": False, "missing_elements": ["B", "A"]}}
    ).seal()
    assert DecisionRecord.model_validate_json(record.model_dump_json()) == record
    reordered = base.model_copy(
        update={"outputs": {"missing_elements": ["B", "A"], "reply_complete": False}}
    ).seal()
    assert reordered.hash == record.hash
    assert record.hash != base.seal().hash
    assert verify_chain([record])
    tampered = record.model_copy(update={"outputs": {"reply_complete": True}})
    assert not verify_chain([tampered])
