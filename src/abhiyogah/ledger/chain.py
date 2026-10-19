"""Hash-chaining decision records: canonical JSON, record hashes and sealing a batch.

The serialisation and hash live on ``DecisionRecord`` (``abhiyogah.domain.decision``); this module
is the ledger's view of them, so storage and the API never compute a hash any other way:

- ``canonical_json(record)`` is every field except ``hash``, keys sorted, no whitespace, UTF-8.
- ``record_hash(prev_hash, record)`` is ``sha256(prev_hash + canonical_json(record))``.

A complaint's records form one chain. ``seal_chain`` appends a batch after a known head, sealing
each record onto the previous one, and never changes a record that is already sealed elsewhere.
"""

import hashlib
from collections.abc import Sequence

from abhiyogah.domain.decision import GENESIS_HASH, DecisionRecord
from abhiyogah.ledger.errors import LedgerError

__all__ = ["canonical_json", "chain_head", "record_hash", "seal_chain"]


def canonical_json(record: DecisionRecord) -> str:
    """Deterministic JSON of every field except ``hash`` (sorted keys, no whitespace)."""
    return record.canonical_json()


def record_hash(prev_hash: str, record: DecisionRecord) -> str:
    """``sha256(prev_hash + canonical_json)`` of ``record`` as if chained after ``prev_hash``."""
    chained = record.model_copy(update={"prev_hash": prev_hash, "hash": None})
    payload = (prev_hash + canonical_json(chained)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def chain_head(records: Sequence[DecisionRecord]) -> str:
    """The hash the next record must chain onto: the last record's hash, or the genesis hash."""
    if not records:
        return GENESIS_HASH
    last = records[-1].hash
    if last is None:
        raise LedgerError(f"record for {records[-1].obligation_id} is not sealed")
    return last


def seal_chain(
    records: Sequence[DecisionRecord], prev_hash: str = GENESIS_HASH
) -> list[DecisionRecord]:
    """Seal ``records`` in order, the first onto ``prev_hash`` and each next onto the one before."""
    sealed: list[DecisionRecord] = []
    head = prev_hash
    for record in records:
        if record.hash is not None:
            raise LedgerError(f"record for {record.obligation_id} is already sealed")
        out = record.seal(head)
        assert out.hash is not None  # noqa: S101 - seal always sets the hash
        sealed.append(out)
        head = out.hash
    return sealed
