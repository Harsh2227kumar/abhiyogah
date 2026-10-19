"""verify_chain pinpoints the first broken link when a record is tampered with."""

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from abhiyogah.domain.decision import DecisionRecord, DecisionResult, RequiredAction
from abhiyogah.domain.decision import verify_chain as domain_verify
from abhiyogah.ledger import ChainBreak, seal_chain, verify_chain
from tests.domain.test_decision import make_record

RESULTS = [DecisionResult.BREACHED, DecisionResult.RUNNING, DecisionResult.STOPPED_ON_TIME]


def chain(n: int = 5) -> list[DecisionRecord]:
    """A sealed chain of ``n`` synthetic records."""
    return seal_chain([make_record(RESULTS[i % len(RESULTS)]) for i in range(n)])


def test_intact_chain_verifies() -> None:
    """An untouched chain verifies and reports its head."""
    records = chain()
    status = verify_chain(records)
    assert status.verified
    assert status.length == 5
    assert status.broken_at is None
    assert status.reason is None
    assert status.head == records[-1].hash


def test_empty_chain_verifies() -> None:
    """Nothing to break."""
    status = verify_chain([])
    assert status.verified
    assert status.length == 0


def test_edited_record_is_pinpointed() -> None:
    """Changing a field without resealing breaks that record's hash."""
    records = chain()
    records[2] = records[2].model_copy(update={"result": DecisionResult.NOT_TRIGGERED})
    status = verify_chain(records)
    assert not status.verified
    assert status.broken_at == 2
    assert status.reason is ChainBreak.HASH_MISMATCH
    assert status.head == records[1].hash


def test_edited_and_resealed_record_breaks_the_next_link() -> None:
    """Resealing a tampered record moves the break to the record after it."""
    records = chain()
    tampered = records[1].model_copy(
        update={"required_actions": [RequiredAction(action="NOTHING", due_date=date(2026, 9, 1))]}
    )
    records[1] = tampered.model_copy(update={"hash": None}).seal(records[1].prev_hash)
    status = verify_chain(records)
    assert status.broken_at == 2
    assert status.reason is ChainBreak.PREV_HASH_MISMATCH


def test_removed_record_is_pinpointed() -> None:
    """Deleting a record from the middle breaks the link at its successor."""
    records = chain()
    del records[3]
    status = verify_chain(records)
    assert status.broken_at == 3
    assert status.reason is ChainBreak.PREV_HASH_MISMATCH


def test_reordered_records_are_pinpointed() -> None:
    """Swapping two records breaks the chain at the first of them."""
    records = chain()
    records[0], records[1] = records[1], records[0]
    status = verify_chain(records)
    assert status.broken_at == 0
    assert status.reason is ChainBreak.PREV_HASH_MISMATCH


def test_unsealed_record_is_pinpointed() -> None:
    """A record without a hash cannot be verified."""
    records = [*chain(2), make_record()]
    status = verify_chain(records)
    assert status.broken_at == 2
    assert status.reason is ChainBreak.UNSEALED


def test_wrong_start_breaks_at_the_first_record() -> None:
    """A chain continued from a different head fails at its first record."""
    status = verify_chain(chain(), start="f" * 64)
    assert status.broken_at == 0
    assert status.reason is ChainBreak.PREV_HASH_MISMATCH


@given(n=st.integers(min_value=1, max_value=8), data=st.data())
def test_any_single_edit_is_found_at_its_index(n: int, data: st.DataObject) -> None:
    """Whichever record is edited, the break is reported exactly there and agrees with domain."""
    records = chain(n)
    i = data.draw(st.integers(min_value=0, max_value=n - 1))
    records[i] = records[i].model_copy(update={"clause": records[i].clause + " (edited)"})
    status = verify_chain(records)
    assert status.broken_at == i
    assert status.reason is ChainBreak.HASH_MISMATCH
    assert domain_verify(records) is False
