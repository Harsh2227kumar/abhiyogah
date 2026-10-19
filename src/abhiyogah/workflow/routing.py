"""Exclusion routing (report row A16, IO Directions 2026 cl. 14(5)) as data, not code branches.

Each cl. 14(5) limb maps to a route: whether the three-state outcome rule of cl. 14(2) applies
(report row A14 exempts out-of-purview limbs (c)-(e)) and how an adverse outcome reaches the IO.
Report row A16 says limbs (a) and (b) are still forwarded to the IO if the outcome is partial or
rejected. For (c)-(e) it says only "IO decides; out-of-purview returned", which does not settle
whether the bank forwards them, so those limbs route to human review until the owner decides
(issue #26).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.enums import Verification

__all__ = ["DEFAULT_ROUTE", "EXCLUSION_ROUTES", "ExclusionRoute", "IoRoute", "route_for"]

CLAUSE_14_5 = "IO Directions 2026 cl. 14(5)"


class IoRoute(StrEnum):
    """How a partially resolved or wholly rejected complaint reaches the IO."""

    FORWARD_IF_ADVERSE = "FORWARD_IF_ADVERSE"
    """Auto-escalate to the IO (report row A13)."""
    HUMAN_REVIEW = "HUMAN_REVIEW"
    """The report does not settle the route; a person decides."""


class ExclusionRoute(BaseModel):
    """Routing for one cl. 14(5) limb, or for a complaint with no exclusion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str | None = Field(description="'14_5_a' to '14_5_e', or None for no exclusion.")
    three_state_exempt: bool = Field(description="Exempt from the cl. 14(2) three-state rule.")
    io_route: IoRoute
    clause: str
    verification: Verification
    note: str = ""


DEFAULT_ROUTE = ExclusionRoute(
    category=None,
    three_state_exempt=False,
    io_route=IoRoute.FORWARD_IF_ADVERSE,
    clause="IO Directions 2026 cl. 14(1)-(2)",
    verification=Verification.PRIMARY_TEXT_READ,
    note="Report rows A13 and A14.",
)
"""A complaint outside every cl. 14(5) limb."""

_FORWARDED = "Still forwarded to the IO if partial or rejected (report row A16)."
_OUT_OF_PURVIEW = (
    "Out of purview: exempt from the three-state rule (report row A14); whether the bank forwards "
    "it to the IO is not settled by report row A16, so a person decides."
)

EXCLUSION_ROUTES: dict[str, ExclusionRoute] = {
    "14_5_a": ExclusionRoute(
        category="14_5_a",
        three_state_exempt=False,
        io_route=IoRoute.FORWARD_IF_ADVERSE,
        clause=f"{CLAUSE_14_5}(a)",
        verification=Verification.PRIMARY_TEXT_READ,
        note=_FORWARDED,
    ),
    "14_5_b": ExclusionRoute(
        category="14_5_b",
        three_state_exempt=False,
        io_route=IoRoute.FORWARD_IF_ADVERSE,
        clause=f"{CLAUSE_14_5}(b)",
        verification=Verification.PRIMARY_TEXT_READ,
        note=_FORWARDED,
    ),
    **{
        f"14_5_{limb}": ExclusionRoute(
            category=f"14_5_{limb}",
            three_state_exempt=True,
            io_route=IoRoute.HUMAN_REVIEW,
            clause=f"{CLAUSE_14_5}({limb}); cl. 14(2)",
            verification=Verification.PRIMARY_TEXT_READ,
            note=_OUT_OF_PURVIEW,
        )
        for limb in "cde"
    },
}
"""Routes by cl. 14(5) limb (report rows A14 and A16)."""


def route_for(facts: ComplaintFacts) -> ExclusionRoute:
    """The route for this complaint's exclusion category, or the default route."""
    if facts.exclusion_category is None:
        return DEFAULT_ROUTE
    return EXCLUSION_ROUTES[facts.exclusion_category.value]
