"""Typed errors raised by the ledger."""

__all__ = ["LedgerError"]


class LedgerError(Exception):
    """A record cannot be chained as asked (unsealed head, record already sealed)."""
