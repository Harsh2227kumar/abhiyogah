"""Typed errors raised by the store."""

__all__ = [
    "EvidenceConflictError",
    "ReviewTaskClosedError",
    "StoreError",
    "UnknownReviewTaskError",
]


class StoreError(Exception):
    """Base class for store errors."""


class EvidenceConflictError(StoreError):
    """An event ID or task ID is reused with different content; evidence is never overwritten."""


class UnknownReviewTaskError(StoreError):
    """No review task has this ID."""


class ReviewTaskClosedError(StoreError):
    """The review task is already closed; a task closes once."""
