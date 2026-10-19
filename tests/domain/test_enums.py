"""Enum values match their names so YAML and JSON use the code's spelling."""

from enum import StrEnum

import pytest

from abhiyogah.domain import enums

ENUMS: list[type[StrEnum]] = [
    enums.AccountType,
    enums.Appellant,
    enums.BasisStatus,
    enums.Channel,
    enums.DayBasis,
    enums.Deontic,
    enums.EntityType,
    enums.FactSource,
    enums.IssueType,
    enums.LiabilityFault,
    enums.Outcome,
    enums.RuleStatus,
    enums.Verification,
]


@pytest.mark.parametrize("enum_cls", ENUMS)
def test_values_equal_names(enum_cls: type[StrEnum]) -> None:
    """Every member's value is its UPPER_SNAKE name."""
    for member in enum_cls:
        assert member.value == member.name
        assert member.name.isupper()


def test_outcome_has_exactly_three_states() -> None:
    """IO Directions cl. 14(2) allows only three outcomes."""
    assert len(enums.Outcome) == 3


def test_aeps_is_split_into_its_two_annex_rows() -> None:
    """The TAT annex has separate AePS merchant and beneficiary rows (issue #20)."""
    names = {c.value for c in enums.Channel}
    assert {"AEPS_MERCHANT", "AEPS_BENEFICIARY"} <= names
    assert "AEPS" not in names
