"""The shape every per-day compensation shares: ``amount_per_day x days late``.

Failed transactions (₹100/day, B1), property documents (₹5,000/day, C3), deceased lockers
(₹5,000/day, C2), card closure (₹500/day) and credit information (₹100/day, B12) all reduce to it.
The per-day amount always comes from the rule pack.
"""

from pydantic import JsonValue

from abhiyogah.calculators.errors import CalculatorError
from abhiyogah.domain.decision import Compensation
from abhiyogah.domain.money import Paise

__all__ = ["per_day_compensation"]


def per_day_compensation(
    per_day_paise: int,
    days_late: int,
    formula: str,
    inputs: dict[str, JsonValue] | None = None,
) -> Compensation:
    """``per_day_paise x max(0, days_late)`` with the formula and inputs recorded."""
    if per_day_paise < 0:
        raise CalculatorError(f"per-day amount must be >= 0, got {per_day_paise}")
    days = max(0, days_late)
    return Compensation(
        amount_paise=Paise(per_day_paise * days),
        formula=formula,
        inputs={"per_day_paise": per_day_paise, "days_late": days, **(inputs or {})},
    )
