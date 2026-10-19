"""Paise helpers: integer arithmetic and Indian formatting."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from abhiyogah.domain.money import Paise, format_inr, rupees


def test_rupees_to_paise() -> None:
    """One rupee is 100 paise."""
    assert rupees(100) == 10_000


@pytest.mark.parametrize("bad", [1.5, True, "100"])
def test_rupees_rejects_non_int(bad: object) -> None:
    """Floats, bools and strings are refused."""
    with pytest.raises(TypeError):
        rupees(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0.00"),
        (5, "₹0.05"),
        (10_000, "₹100.00"),
        (50_000_00, "₹50,000.00"),
        (12_34_567_89, "₹12,34,567.89"),
        (1_73_00_000_00, "₹1,73,00,000.00"),
        (-2_500_00, "-₹2,500.00"),
    ],
)
def test_format_inr(paise: int, text: str) -> None:
    """Amounts use Indian lakh/crore grouping and two decimals."""
    assert format_inr(Paise(paise)) == text


@given(st.integers(min_value=-(10**15), max_value=10**15))
def test_format_inr_round_trips(p: int) -> None:
    """Stripping the symbol and commas recovers the paise exactly."""
    text = format_inr(Paise(p)).replace("₹", "").replace(",", "")
    whole, frac = text.lstrip("-").split(".")
    value = int(whole) * 100 + int(frac)
    assert (-value if text.startswith("-") else value) == p
