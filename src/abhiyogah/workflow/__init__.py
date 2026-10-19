"""Workflow gates: three-state outcome, IO auto-escalation and senior review."""

from abhiyogah.workflow.closure import ADVERSE_OUTCOMES, Actor, can_close, outcome_gate
from abhiyogah.workflow.gates import GateReason, GateResult
from abhiyogah.workflow.routing import (
    DEFAULT_ROUTE,
    EXCLUSION_ROUTES,
    ExclusionRoute,
    IoRoute,
    route_for,
)

__all__ = [
    "ADVERSE_OUTCOMES",
    "DEFAULT_ROUTE",
    "EXCLUSION_ROUTES",
    "Actor",
    "ExclusionRoute",
    "GateReason",
    "GateResult",
    "IoRoute",
    "can_close",
    "outcome_gate",
    "route_for",
]
