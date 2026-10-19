"""The rule pack's scenario files are well formed and consistent with their obligations.

The engine stream's runner checks the numbers against the evaluator. These checks only make sure
each file says what `rules/scenarios/_schema.md` requires, so a scenario cannot silently test less
than it claims.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from abhiyogah.domain.complaint import fold_events
from abhiyogah.domain.decision import DecisionResult
from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import ComplaintEvent, Provenance
from abhiyogah.domain.tz import ist_date
from abhiyogah.registry.loader import load_registry

RULES = Path(__file__).parents[2] / "rules"
SCENARIOS = sorted(p for p in (RULES / "scenarios").glob("*.yaml") if not p.name.startswith("_"))
# DETERMINED is requested as a DecisionResult member (tasks/02-rule-pack.md, Requests);
# accept it here until the domain adds it.
DETERMINED = "DETERMINED"
WITH_DEADLINE = {
    DecisionResult.RUNNING,
    DecisionResult.STOPPED_ON_TIME,
    DecisionResult.STOPPED_LATE,
    DecisionResult.BREACHED,
}


def to_events(spec: dict[str, Any]) -> list[ComplaintEvent]:
    """Build events the way the scenario runner does (rules/scenarios/_schema.md)."""
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


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario_is_consistent(path: Path) -> None:
    """Name, events, results, deadlines, breaches and obligation links all agree."""
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert spec["name"] == path.stem
    assert spec["hand_check"].strip()
    fold_events(f"SCN-{spec['name']}", to_events(spec))

    as_of = spec["as_of"]
    assert isinstance(as_of, datetime)
    assert as_of.tzinfo is not None
    expect = spec["expect"]
    ids = spec["obligation_ids"]
    results = {
        oid: r if r == DETERMINED else DecisionResult(r) for oid, r in expect["results"].items()
    }
    assert set(results) == set(ids), "expect.results must cover every obligation_id"

    deadlines = {d["obligation_id"]: d for d in expect.get("deadlines") or []}
    assert len(deadlines) == len(expect.get("deadlines") or [])
    assert set(deadlines) == {oid for oid, r in results.items() if r in WITH_DEADLINE}
    for oid, d in deadlines.items():
        assert isinstance(d["due_date"], date)
        assert DecisionResult(d["result"]) is results[oid]

    breaches = {b["obligation_id"]: b for b in expect.get("breaches") or []}
    late = {DecisionResult.STOPPED_LATE, DecisionResult.BREACHED}
    assert set(breaches) == {oid for oid, r in results.items() if r in late}
    for oid, b in breaches.items():
        assert b["due_date"] == deadlines[oid]["due_date"]
        assert b["days_late"] >= 1
        if results[oid] is DecisionResult.BREACHED:
            assert b["days_late"] == (ist_date(as_of) - b["due_date"]).days

    outputs = expect.get("outputs") or {}
    assert set(outputs) == {oid for oid, r in results.items() if r == DETERMINED}
    assert all(isinstance(v, dict) and v for v in outputs.values())

    for amount in (expect.get("compensation_paise") or {}).values():
        assert isinstance(amount, int)
        assert amount > 0

    registry = load_registry(RULES / "obligations")
    for oid in ids:
        assert path.name in registry[oid].tests, f"{oid} does not list {path.name} in tests"
