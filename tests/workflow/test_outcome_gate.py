"""Three-state outcome gate (report row A14, IO Directions 2026 cl. 14(2))."""

import pytest

from abhiyogah.domain.enums import Outcome
from abhiyogah.workflow import outcome_gate
from tests.workflow.builders import RECEIVED, exclusion, facts, outcome


def test_closing_without_an_outcome_is_refused() -> None:
    """No outcome recorded: the gate refuses and cites cl. 14(2)."""
    result = outcome_gate(facts(RECEIVED))
    assert not result.allowed
    (reason,) = result.reasons
    assert reason.code == "OUTCOME_NOT_SET"
    assert "14(2)" in reason.clause
    for o in Outcome:
        assert o.value in reason.message


@pytest.mark.parametrize("value", [o.value for o in Outcome])
def test_each_of_the_three_outcomes_passes(value: str) -> None:
    """Any of the three allowed outcomes opens the gate."""
    assert outcome_gate(facts(RECEIVED, outcome(value))).allowed


@pytest.mark.parametrize("limb", ["14_5_c", "14_5_d", "14_5_e"])
def test_out_of_purview_limbs_are_exempt(limb: str) -> None:
    """Report row A14: cl. 14(5)(c)-(e) complaints close without a three-state outcome."""
    assert outcome_gate(facts(RECEIVED, exclusion(limb))).allowed


@pytest.mark.parametrize("limb", ["14_5_a", "14_5_b"])
def test_forwarded_limbs_still_need_an_outcome(limb: str) -> None:
    """Limbs (a) and (b) are not out of purview; the three-state rule still applies."""
    assert not outcome_gate(facts(RECEIVED, exclusion(limb))).allowed
