"""Workflow gates: three-state outcome, IO auto-escalation and senior review."""

from abhiyogah.workflow.closure import outcome_gate
from abhiyogah.workflow.gates import GateReason, GateResult
from abhiyogah.workflow.routing import (
    DEFAULT_ROUTE,
    EXCLUSION_ROUTES,
    ExclusionRoute,
    IoRoute,
    route_for,
)

__all__ = [
    "DEFAULT_ROUTE",
    "EXCLUSION_ROUTES",
    "ExclusionRoute",
    "GateReason",
    "GateResult",
    "IoRoute",
    "outcome_gate",
    "route_for",
]
