"""Typed exceptions raised by the compensation calculators."""

from abhiyogah.domain.errors import DomainError

__all__ = ["CalculatorError"]


class CalculatorError(DomainError):
    """Inputs to a calculator are inconsistent (negative amounts, reversal before T, ...)."""
