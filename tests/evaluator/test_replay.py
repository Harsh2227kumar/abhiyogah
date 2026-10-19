"""Replay: the same events at the same as_of always give byte-identical records."""

import random
from datetime import date

from abhiyogah.domain.decision import verify_chain
from abhiyogah.domain.events import ComplaintEvent, EventType
from abhiyogah.evaluator import evaluate
from abhiyogah.registry.schema import Obligation
from tests.evaluator.builders import ordinary_limb, tat_limb
from tests.evaluator.test_evaluate import CAL, PROFILE, RECEIVED, REJECTED, a2_like, at, ev

EVENTS = [
    RECEIVED,
    REJECTED,
    ev(3, EventType.BANK_COMMUNICATION_SENT, date(2026, 8, 12)),
    ev(4, EventType.IO_REFERRED, date(2026, 8, 26)),
]
OBLIGATIONS = [ordinary_limb(), tat_limb(), a2_like()]
AS_OF = at(date(2026, 9, 10), 18)


def run(
    events: list[ComplaintEvent] = EVENTS, obligations: list[Obligation] = OBLIGATIONS
) -> list[str]:
    """Evaluate and return each record's canonical JSON."""
    records = evaluate(events, obligations, CAL, AS_OF, profile=PROFILE)
    return [r.canonical_json() for r in records]


def test_same_inputs_give_byte_identical_records() -> None:
    """Two evaluations of the same inputs serialise to the same bytes."""
    assert run() == run()


def test_input_order_does_not_matter() -> None:
    """Shuffling events and obligations does not change a single byte."""
    expected = run()
    rng = random.Random(20261019)  # noqa: S311 - deterministic shuffle, not crypto
    for _ in range(10):
        events = EVENTS[:]
        obligations = OBLIGATIONS[:]
        rng.shuffle(events)
        rng.shuffle(obligations)
        assert run(events, obligations) == expected


def test_sealed_chains_are_identical_and_verify() -> None:
    """Sealing the replayed records gives the same hashes, and the chain verifies."""

    def sealed() -> list[str]:
        prev = "0" * 64
        out = []
        records = evaluate(EVENTS, OBLIGATIONS, CAL, AS_OF, profile=PROFILE)
        chain = []
        for r in records:
            s = r.seal(prev)
            chain.append(s)
            assert s.hash is not None
            prev = s.hash
            out.append(s.hash)
        assert verify_chain(chain)
        return out

    assert sealed() == sealed()


def test_later_recorded_events_do_not_change_past_replay() -> None:
    """An event recorded after as_of leaves the as_of replay unchanged."""
    late = ev(5, EventType.FINAL_REPLY_SENT, date(2026, 9, 20))
    assert run([*EVENTS, late]) == run()
