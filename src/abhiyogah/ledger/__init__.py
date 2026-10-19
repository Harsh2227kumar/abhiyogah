"""Append-only, hash-chained decision-record ledger."""

from abhiyogah.ledger.chain import canonical_json, chain_head, record_hash, seal_chain
from abhiyogah.ledger.errors import LedgerError
from abhiyogah.ledger.explain import render_explanation
from abhiyogah.ledger.verify import ChainBreak, ChainStatus, verify_chain

__all__ = [
    "ChainBreak",
    "ChainStatus",
    "LedgerError",
    "canonical_json",
    "chain_head",
    "record_hash",
    "render_explanation",
    "seal_chain",
    "verify_chain",
]
