"""Typed exceptions raised by the domain layer."""

__all__ = ["DomainError", "FactFoldError", "NaiveDatetimeError"]


class DomainError(Exception):
    """Base class for every domain-layer error."""


class FactFoldError(DomainError):
    """An event could not be folded into complaint facts (missing or malformed payload)."""


class NaiveDatetimeError(DomainError, ValueError):
    """A datetime without a time zone reached code that needs an aware one."""
