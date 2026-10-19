"""Property tests: folding is deterministic and replayable."""

import random
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from abhiyogah.domain.complaint import fold_events
from abhiyogah.domain.decision import DecisionRecord, DecisionResult
from abhiyogah.domain.events import ComplaintEvent, EventType
from tests.domain.factories import event

CID = "CMP-TEST-1"
BASE = datetime(2026, 7, 1, tzinfo=UTC)

event_specs = st.lists(
    st.tuples(
        st.sampled_from([e for e in EventType if e is not EventType.OUTCOME_SET]),
        st.integers(min_value=0, max_value=60 * 24 * 90),
    ),
    max_size=12,
)


def build(specs: list[tuple[EventType, int]]) -> list[ComplaintEvent]:
    """Events at BASE + minutes, with unique IDs."""
    return [event(i, t, BASE + timedelta(minutes=m)) for i, (t, m) in enumerate(specs)]


@given(event_specs, st.randoms(use_true_random=False))
def test_fold_ignores_input_order(specs: list[tuple[EventType, int]], rnd: random.Random) -> None:
    """Shuffling the event list never changes the facts."""
    events = build(specs)
    shuffled = list(events)
    rnd.shuffle(shuffled)
    assert fold_events(CID, events) == fold_events(CID, shuffled)


@given(event_specs, st.integers(min_value=0, max_value=60 * 24 * 90))
def test_known_at_equals_folding_the_prefix(specs: list[tuple[EventType, int]], cut: int) -> None:
    """Folding as of a moment equals folding only the events recorded by then."""
    events = build(specs)
    known_at = BASE + timedelta(minutes=cut)
    prefix = [e for e in events if e.recorded_at <= known_at]
    assert fold_events(CID, events, known_at=known_at) == fold_events(CID, prefix)


@given(st.sampled_from(list(DecisionResult)), st.integers(min_value=0, max_value=365))
def test_decision_record_round_trips(result: DecisionResult, offset: int) -> None:
    """Any sealed record survives JSON and keeps a valid hash."""
    record = DecisionRecord(
        complaint_id=CID,
        obligation_id="TEST-2026-1",
        obligation_version="v",
        clause="1",
        anchor_date=(BASE + timedelta(days=offset)).date(),
        as_of=BASE + timedelta(days=offset),
        result=result,
        input_facts=[],
    ).seal()
    again = DecisionRecord.model_validate_json(record.model_dump_json())
    assert again == record
    assert again.compute_hash() == record.hash
