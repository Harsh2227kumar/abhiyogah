"""Typed exceptions raised by the obligation registry."""

from pathlib import Path

__all__ = [
    "DuplicateObligationError",
    "NoParameterInForce",
    "ObligationFileError",
    "RegistryError",
    "UnknownParameterError",
]


class RegistryError(Exception):
    """Base class for every registry error."""


class ObligationFileError(RegistryError):
    """An obligation file could not be read, parsed or validated."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


class DuplicateObligationError(RegistryError):
    """Two obligation files declare the same ``obligation_id``."""

    def __init__(self, obligation_id: str, first: Path, second: Path) -> None:
        super().__init__(f"duplicate obligation_id {obligation_id!r} in {first} and {second}")
        self.obligation_id = obligation_id
        self.first = first
        self.second = second


class UnknownParameterError(RegistryError, KeyError):
    """An obligation has no parameter of the requested name."""


class NoParameterInForce(RegistryError, LookupError):  # noqa: N818 - name fixed by the task file
    """A parameter has no value whose effective date is on or before the anchor date."""
