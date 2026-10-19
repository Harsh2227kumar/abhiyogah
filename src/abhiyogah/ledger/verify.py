"""Chain verification that says where a chain breaks and why.

``abhiyogah.domain.decision.verify_chain`` answers yes or no. The ledger needs more for audit and
for the API: the index of the first broken record and the kind of break, so an investigator can go
straight to the tampered or missing record. Every record after the first break is suspect too,
because its ``prev_hash`` was computed over different bytes.
"""

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from abhiyogah.domain.decision import GENESIS_HASH, DecisionRecord

__all__ = ["ChainBreak", "ChainStatus", "verify_chain"]


class ChainBreak(StrEnum):
    """Why a record does not verify."""

    UNSEALED = "UNSEALED"
    """The record has no hash."""
    PREV_HASH_MISMATCH = "PREV_HASH_MISMATCH"
    """The record does not chain onto the previous record's hash (a record removed or reordered)."""
    HASH_MISMATCH = "HASH_MISMATCH"
    """The stored hash does not match the record's content (the record was edited)."""


class ChainStatus(BaseModel):
    """Result of verifying one chain of decision records."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verified: bool
    length: int = Field(ge=0)
    broken_at: int | None = Field(default=None, description="Index of the first bad record.")
    reason: ChainBreak | None = None
    head: str = Field(description="Hash of the last verified record, or the genesis hash.")


def verify_chain(records: Sequence[DecisionRecord], start: str = GENESIS_HASH) -> ChainStatus:
    """Check every link from ``start``; report the first broken record, if any."""
    prev = start
    for index, record in enumerate(records):
        reason: ChainBreak | None = None
        if record.hash is None:
            reason = ChainBreak.UNSEALED
        elif record.prev_hash != prev:
            reason = ChainBreak.PREV_HASH_MISMATCH
        elif record.hash != record.compute_hash():
            reason = ChainBreak.HASH_MISMATCH
        if reason is not None:
            return ChainStatus(
                verified=False, length=len(records), broken_at=index, reason=reason, head=prev
            )
        assert record.hash is not None  # noqa: S101 - checked above
        prev = record.hash
    return ChainStatus(verified=True, length=len(records), head=prev)
