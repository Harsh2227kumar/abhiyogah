"""Typed errors raised by the store."""

__all__ = ["EvidenceConflictError", "StoreError"]


class StoreError(Exception):
    """Base class for store errors."""


class EvidenceConflictError(StoreError):
    """An event ID or task ID is reused with different content; evidence is never overwritten."""
