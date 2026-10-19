"""Typed exceptions raised by the evaluator."""

from abhiyogah.domain.errors import DomainError

__all__ = ["ConditionSyntaxError", "EvaluationError", "ParameterError"]


class EvaluationError(DomainError):
    """The rule pack or the inputs cannot be evaluated (a rule-pack bug, not a missing fact)."""


class ConditionSyntaxError(EvaluationError):
    """A trigger condition is outside the supported condition grammar."""


class ParameterError(EvaluationError):
    """An obligation's parameters do not form a supported duration or have the wrong type."""
