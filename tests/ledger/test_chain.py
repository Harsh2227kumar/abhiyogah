"""Canonical JSON, record hashes and sealing a batch of decision records."""

import hashlib
import itertools
import json

import pytest

from abhiyogah.domain.decision import GENESIS_HASH, DecisionResult, verify_chain
from abhiyogah.ledger import LedgerError, canonical_json, chain_head, record_hash, seal_chain
from tests.domain.test_decision import make_record


def test_canonical_json_is_sorted_compact_and_excludes_hash() -> None:
    """Keys are sorted, there is no whitespace and the hash field is left out."""
    record = make_record().seal()
    text = canonical_json(record)
    data = json.loads(text)
    assert "hash" not in data
    assert list(data) == sorted(data)
    assert text == json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_canonical_json_is_stable_across_round_trips() -> None:
    """Parsing a record back from JSON gives the same canonical bytes."""
    record = make_record()
    again = type(record).model_validate_json(record.model_dump_json())
    assert canonical_json(again) == canonical_json(record)


def test_record_hash_is_sha256_of_prev_hash_and_canonical_json() -> None:
    """The documented formula, computed by hand."""
    prev = "a" * 64
    record = make_record()
    chained = record.model_copy(update={"prev_hash": prev})
    expected = hashlib.sha256((prev + canonical_json(chained)).encode("utf-8")).hexdigest()
    assert record_hash(prev, record) == expected
    assert record.seal(prev).hash == expected


def test_seal_chain_links_each_record_to_the_one_before() -> None:
    """Each record's prev_hash is the previous record's hash, and the chain verifies."""
    batch = [make_record(), make_record(DecisionResult.RUNNING), make_record()]
    sealed = seal_chain(batch)
    assert sealed[0].prev_hash == GENESIS_HASH
    for before, after in itertools.pairwise(sealed):
        assert after.prev_hash == before.hash
    assert verify_chain(sealed)
    assert chain_head(sealed) == sealed[-1].hash


def test_seal_chain_continues_after_an_existing_head() -> None:
    """A second batch appended onto the first verifies as one chain."""
    first = seal_chain([make_record()])
    second = seal_chain([make_record(DecisionResult.RUNNING)], chain_head(first))
    assert verify_chain(first + second)


def test_chain_head_of_empty_chain_is_genesis() -> None:
    """An empty chain starts from the genesis hash."""
    assert chain_head([]) == GENESIS_HASH


def test_chain_head_refuses_unsealed_records() -> None:
    """A chain whose last record has no hash has no head."""
    with pytest.raises(LedgerError, match="not sealed"):
        chain_head([make_record()])


def test_seal_chain_refuses_already_sealed_records() -> None:
    """Re-sealing would silently rewrite evidence; it is refused."""
    with pytest.raises(LedgerError, match="already sealed"):
        seal_chain([make_record().seal()])
