"""Workflow gate results: whether an action is allowed, and every reason it is not.

Gates never raise for a business refusal; they return a ``GateResult`` whose reasons cite the clause
that refuses, so the API can show the officer what is missing. Typed exceptions are for bad input.
"""

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["GateReason", "GateResult"]


class GateReason(BaseModel):
    """One reason an action is refused, with the clause behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(description="UPPER_SNAKE reason code, e.g. 'OUTCOME_NOT_SET'.")
    message: str
    clause: str = Field(description="Instrument and clause, e.g. 'IO Directions 2026 cl. 14(2)'.")


class GateResult(BaseModel):
    """``allowed`` is true exactly when there are no reasons."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reasons: list[GateReason] = Field(default_factory=list)

    @property
    def allowed(self) -> bool:
        """True when nothing refuses the action."""
        return not self.reasons

    def __add__(self, other: "GateResult") -> "GateResult":
        """Combine two gates: the action needs both to pass."""
        return GateResult(reasons=[*self.reasons, *other.reasons])
