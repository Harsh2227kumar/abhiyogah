"""Exclusion routing table (report row A16) is complete and data-driven."""

from abhiyogah.domain.complaint import ExclusionCategory
from abhiyogah.workflow import DEFAULT_ROUTE, EXCLUSION_ROUTES, IoRoute, route_for
from tests.workflow.builders import RECEIVED, exclusion, facts


def test_every_limb_has_a_route() -> None:
    """All five cl. 14(5) limbs are in the table, keyed by their own category."""
    assert sorted(EXCLUSION_ROUTES) == [f"14_5_{x}" for x in "abcde"]
    for key, route in EXCLUSION_ROUTES.items():
        assert route.category == key
        assert "14(5)" in route.clause


def test_route_for_reads_the_exclusion_fact() -> None:
    """No exclusion fact gives the default route; a limb gives its row."""
    assert route_for(facts(RECEIVED)) is DEFAULT_ROUTE
    category: ExclusionCategory = "14_5_d"
    assert route_for(facts(RECEIVED, exclusion(category))) is EXCLUSION_ROUTES[category]


def test_only_out_of_purview_limbs_go_to_a_person() -> None:
    """(a) and (b) are forwarded on an adverse outcome; (c)-(e) need a human decision."""
    routes = {k: r.io_route for k, r in EXCLUSION_ROUTES.items()}
    assert routes == {
        "14_5_a": IoRoute.FORWARD_IF_ADVERSE,
        "14_5_b": IoRoute.FORWARD_IF_ADVERSE,
        "14_5_c": IoRoute.HUMAN_REVIEW,
        "14_5_d": IoRoute.HUMAN_REVIEW,
        "14_5_e": IoRoute.HUMAN_REVIEW,
    }
