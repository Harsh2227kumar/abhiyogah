"""Money as integer paise. Never use floats for amounts; format as ₹ only at the edges."""

from typing import NewType

__all__ = ["PAISE_PER_RUPEE", "Paise", "format_inr", "rupees"]

Paise = NewType("Paise", int)
"""An amount in paise (1 rupee = 100 paise)."""

PAISE_PER_RUPEE = 100


def rupees(n: int) -> Paise:
    """Convert a whole-rupee amount to paise."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"rupees() takes an int, got {type(n).__name__}")
    return Paise(n * PAISE_PER_RUPEE)


def _group_indian(digits: str) -> str:
    """Group a digit string the Indian way: last three digits, then pairs (12,34,567)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join([*pairs, tail])


def format_inr(p: Paise) -> str:
    """Format paise as rupees with Indian digit grouping, for example ``₹1,73,00,000.00``."""
    sign = "-" if p < 0 else ""
    whole, frac = divmod(abs(p), PAISE_PER_RUPEE)
    return f"{sign}₹{_group_indian(str(whole))}.{frac:02d}"
