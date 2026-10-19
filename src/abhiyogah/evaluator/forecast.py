"""Breach forecasting: which running deadlines fall due within a horizon.

The horizon is an operational look-ahead in calendar days counted from the ``as_of`` date, not a
regulatory duration. Only clocks that are still ``RUNNING`` are listed; breached ones are already
breaches.
"""

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from abhiyogah.clocks import BankCalendar
from abhiyogah.domain.decision import DecisionRecord, DecisionResult, RequiredAction
from abhiyogah.domain.enums import DayBasis
from abhiyogah.domain.events import ComplaintEvent
from abhiyogah.domain.tz import ist_date
from abhiyogah.evaluator.engine import evaluate
from abhiyogah.evaluator.errors import EvaluationError
from abhiyogah.evaluator.profile import EntityProfile
from abhiyogah.registry.schema import Obligation

__all__ = ["ForecastItem", "forecast", "forecast_records"]


class ForecastItem(BaseModel):
    """A running deadline that falls due within the horizon."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    complaint_id: str
    obligation_id: str
    clause: str
    due_date: date
    basis: DayBasis
    calendar_days_left: int = Field(ge=0, description="due_date - as_of date, in calendar days.")
    required_actions: list[RequiredAction] = Field(default_factory=list)


def forecast_records(
    records: Iterable[DecisionRecord], as_of: datetime, horizon_days: int
) -> list[ForecastItem]:
    """Running deadlines due on or before ``as_of`` date + ``horizon_days``, soonest first."""
    if horizon_days < 0:
        raise EvaluationError(f"horizon_days must be >= 0, got {horizon_days}")
    today = ist_date(as_of)
    until = today + timedelta(days=horizon_days)
    items = [
        ForecastItem(
            complaint_id=r.complaint_id,
            obligation_id=r.obligation_id,
            clause=r.clause,
            due_date=r.deadline.due_date,
            basis=r.deadline.basis,
            calendar_days_left=(r.deadline.due_date - today).days,
            required_actions=r.required_actions,
        )
        for r in records
        if r.result is DecisionResult.RUNNING
        and r.deadline is not None
        and today <= r.deadline.due_date <= until
    ]
    return sorted(items, key=lambda i: (i.due_date, i.complaint_id, i.obligation_id))


def forecast(
    complaint_events: Sequence[ComplaintEvent],
    obligations: Sequence[Obligation],
    calendar: BankCalendar,
    as_of: datetime,
    horizon_days: int,
    *,
    profile: EntityProfile,
    complaint_id: str | None = None,
) -> list[ForecastItem]:
    """Evaluate one complaint at ``as_of`` and list the deadlines due within ``horizon_days``."""
    records = evaluate(
        complaint_events, obligations, calendar, as_of, profile=profile, complaint_id=complaint_id
    )
    return forecast_records(records, as_of, horizon_days)
