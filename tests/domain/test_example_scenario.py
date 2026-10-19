"""The foundation's example scenario parses into domain events and its hand check adds up."""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from abhiyogah.domain.complaint import fold_events
from abhiyogah.domain.enums import FactSource, Outcome
from abhiyogah.domain.events import ComplaintEvent, Provenance
from abhiyogah.domain.tz import ist_date

SCENARIO = Path(__file__).parents[2] / "rules" / "scenarios" / "io_20d_ordinary_breach.yaml"


def to_events(spec: dict[str, Any]) -> list[ComplaintEvent]:
    """Build events the way rules/scenarios/_schema.md says the runner does."""
    name = spec["name"]
    events = []
    for i, raw in enumerate(spec["events"], start=1):
        source = FactSource(raw.get("source", "SYSTEM"))
        provenance = (
            Provenance(source=source, model="scenario", prompt_version="scenario")
            if source is FactSource.LLM
            else Provenance(source=source, actor="scenario")
        )
        events.append(
            ComplaintEvent(
                event_id=f"{name}-{i}",
                complaint_id=f"SCN-{name}",
                type=raw["type"],
                occurred_at=raw["occurred_at"],
                recorded_at=raw.get("recorded_at", raw["occurred_at"]),
                payload=raw.get("payload", {}),
                provenance=provenance,
            )
        )
    return events


def test_example_scenario_folds_and_hand_check_holds() -> None:
    """Receipt 3 Aug + 20 calendar days = 23 Aug; as_of 25 Aug is 2 days late."""
    spec = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    assert spec["name"] == SCENARIO.stem
    facts = fold_events(f"SCN-{spec['name']}", to_events(spec))
    assert facts.bank_receipt_date is not None
    assert facts.outcome is not None
    assert facts.outcome.value is Outcome.WHOLLY_REJECTED
    assert facts.io_referred_date is None

    (deadline,) = spec["expect"]["deadlines"]
    (breach,) = spec["expect"]["breaches"]
    due = facts.bank_receipt_date.value + timedelta(days=20)
    as_of = spec["as_of"]
    assert isinstance(as_of, datetime)
    assert due == deadline["due_date"] == breach["due_date"] == date(2026, 8, 23)
    assert (ist_date(as_of) - due).days == breach["days_late"] == 2
