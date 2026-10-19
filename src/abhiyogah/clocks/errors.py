"""Typed exceptions raised by the clock engine."""

from abhiyogah.domain.errors import DomainError

__all__ = ["ClockError", "ClockSpecError", "MissingFactError"]


class ClockError(DomainError):
    """A clock cannot be built or read (inconsistent dates, open pause without ``as_of``, ...)."""


class ClockSpecError(ClockError):
    """An obligation's clock spec cannot be executed (e.g. a stop event with no date fact)."""


class MissingFactError(ClockError):
    """A fact the clock needs is unknown. The evaluator reports ``INSUFFICIENT_FACTS``."""

    def __init__(self, fact: str) -> None:
        super().__init__(f"fact {fact!r} is not known")
        self.fact = fact
