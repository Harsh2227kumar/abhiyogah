"""registry.resolve: the dated parameter resolver."""

from datetime import date
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from abhiyogah.registry.errors import NoParameterInForce, UnknownParameterError
from abhiyogah.registry.resolve import parameter_at
from abhiyogah.registry.schema import Obligation
from tests.registry.conftest import MINIMAL


def with_history(history: dict[str, Any]) -> Obligation:
    """MINIMAL with ``max_days`` replaced by ``history`` (effective date -> value)."""
    values = {
        d: {"value": v, "reference": "cl. 1", "verification": "PRIMARY_TEXT_READ"}
        for d, v in history.items()
    }
    return Obligation.model_validate({**MINIMAL, "parameters": {"max_days": values}})


def test_latest_effective_on_or_before_anchor() -> None:
    """The value whose effective date is the latest one not after the anchor wins."""
    ob = with_history({"2021-11-12": 365, "2026-07-01": 90})
    assert parameter_at(ob, "max_days", date(2026, 6, 30)).value == 365
    assert parameter_at(ob, "max_days", date(2026, 7, 1)).value == 90
    assert parameter_at(ob, "max_days", date(2027, 1, 1)).value == 90


def test_before_first_effective_date_raises() -> None:
    """No value is in force before the first effective date; no fallback to a later one."""
    ob = with_history({"2026-07-01": 90})
    with pytest.raises(NoParameterInForce, match="2026-06-30"):
        parameter_at(ob, "max_days", date(2026, 6, 30))


def test_unknown_parameter_raises() -> None:
    """Asking for a parameter the obligation does not have is a typed error."""
    with pytest.raises(UnknownParameterError):
        parameter_at(with_history({"2026-01-01": 1}), "cap_paise", date(2026, 1, 1))


@given(
    st.lists(st.dates(), min_size=1, max_size=6, unique=True),
    st.dates(),
)
def test_matches_brute_force(dates: list[date], anchor: date) -> None:
    """Resolution picks the nearest effective date on or before the anchor."""
    ob = with_history({d.isoformat(): i for i, d in enumerate(dates)})
    earlier = [d for d in dates if d <= anchor]
    if not earlier:
        with pytest.raises(NoParameterInForce):
            parameter_at(ob, "max_days", anchor)
        return
    got = parameter_at(ob, "max_days", anchor)
    nearest = max(earlier)
    assert got.value == dates.index(nearest)
