"""Scenario runner: evaluates one ``rules/scenarios/*.yaml`` file and lists every mismatch.

The file format is ``rules/scenarios/_schema.md``. ``run_scenario`` builds the events, profile and
``as_of`` exactly as the schema says, evaluates the listed obligations (plus the obligations they
name in ``overridden_by``, which the overrides need), and compares the results exactly:

- ``results``: obligation ID -> ``DecisionResult`` for every listed obligation;
- ``deadlines``, ``breaches`` and ``required_actions``: compared as sets, no missing and no extra;
- ``compensation_paise``: obligation ID -> paise owed; obligations owing nothing are left out;
- ``outputs``: obligation ID -> values, compared exactly per listed obligation (a missing key or
  obligation means no outputs).

An obligation named by a scenario but missing from the pack is a mismatch, not a skip.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from abhiyogah.clocks import BankCalendar
from abhiyogah.domain.decision import DecisionRecord
from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import ComplaintEvent, Provenance
from abhiyogah.evaluator import EntityProfile, evaluate
from abhiyogah.registry.schema import Obligation

__all__ = ["ScenarioOutcome", "load_scenario", "run_scenario", "scenario_events", "scenario_files"]


def scenario_files(directory: Path) -> list[Path]:
    """Every scenario file in ``directory``, sorted, skipping files that start with ``_``."""
    return sorted(p for p in directory.glob("*.yaml") if not p.name.startswith("_"))


def load_scenario(path: Path) -> dict[str, Any]:
    """Parse one scenario file; its ``name`` must equal the file stem."""
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or spec.get("name") != path.stem:
        raise ValueError(f"{path.name}: top level must be a mapping whose name is {path.stem!r}")
    return spec


def _aware(value: object, what: str) -> datetime:
    """A timezone-aware datetime from YAML (which parses offsets itself)."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{what} must be an ISO 8601 time with an explicit offset: {value!r}")
    return value


def scenario_events(spec: Mapping[str, Any]) -> list[ComplaintEvent]:
    """Events with the IDs, complaint ID and provenance the schema prescribes."""
    name = spec["name"]
    events = []
    for i, raw in enumerate(spec.get("events") or [], start=1):
        source = FactSource(raw.get("source", "SYSTEM"))
        provenance = (
            Provenance(source=source, model="scenario", prompt_version="scenario")
            if source is FactSource.LLM
            else Provenance(source=source, actor="scenario")
        )
        occurred = _aware(raw["occurred_at"], f"event {i} occurred_at")
        recorded = _aware(raw.get("recorded_at", occurred), f"event {i} recorded_at")
        events.append(
            ComplaintEvent(
                event_id=f"{name}-{i}",
                complaint_id=f"SCN-{name}",
                type=raw["type"],
                occurred_at=occurred,
                recorded_at=recorded,
                payload=raw.get("payload") or {},
                provenance=provenance,
            )
        )
    return events


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    """The records the engine produced and every way they differ from the expectation."""

    records: list[DecisionRecord]
    mismatches: list[str]


def _closure(ids: list[str], pack: Mapping[str, Obligation]) -> tuple[list[Obligation], list[str]]:
    """The listed obligations plus everything they name in ``overridden_by``; and missing IDs."""
    todo, seen, missing = list(ids), set[str](), []
    while todo:
        oid = todo.pop()
        if oid in seen:
            continue
        seen.add(oid)
        if oid not in pack:
            missing.append(oid)
            continue
        todo.extend(pack[oid].overridden_by)
    return [pack[o] for o in sorted(seen) if o in pack], sorted(missing)


def _compare(label: str, expected: set[Any], actual: set[Any]) -> list[str]:
    """Set comparison with readable missing/extra lines."""
    out = [f"{label}: missing {item}" for item in sorted(expected - actual, key=str)]
    out += [f"{label}: unexpected {item}" for item in sorted(actual - expected, key=str)]
    return out


def _as_date(value: object) -> date:
    """A YAML date (or ISO string) as a ``date``."""
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def run_scenario(
    spec: Mapping[str, Any], pack: Mapping[str, Obligation], calendar: BankCalendar
) -> ScenarioOutcome:
    """Evaluate one scenario and list every mismatch with its expectation."""
    ids: list[str] = list(spec["obligation_ids"])
    obligations, missing = _closure(ids, pack)
    if missing:
        return ScenarioOutcome([], [f"obligation not in the rule pack: {m}" for m in missing])
    profile = EntityProfile.model_validate(spec["entity_profile"])
    as_of = _aware(spec["as_of"], "as_of")
    records = evaluate(
        scenario_events(spec),
        obligations,
        calendar,
        as_of,
        profile=profile,
        complaint_id=f"SCN-{spec['name']}",
    )
    listed = [r for r in records if r.obligation_id in ids]
    expect: Mapping[str, Any] = spec.get("expect") or {}
    mismatches: list[str] = []

    want_results = expect.get("results")
    if want_results is not None:
        got = {r.obligation_id: r.result.value for r in listed}
        for oid in ids:
            if want_results.get(oid) != got.get(oid):
                mismatches.append(
                    f"results: {oid} expected {want_results.get(oid)}, got {got.get(oid)}"
                )

    mismatches += _compare(
        "deadlines",
        {
            (d["obligation_id"], _as_date(d["due_date"]), d["result"])
            for d in expect.get("deadlines") or []
        },
        {
            (r.obligation_id, r.deadline.due_date, r.result.value)
            for r in listed
            if r.deadline is not None
        },
    )
    mismatches += _compare(
        "breaches",
        {
            (b["obligation_id"], _as_date(b["due_date"]), b["days_late"])
            for b in expect.get("breaches") or []
        },
        {
            (r.breach.obligation_id, r.breach.due_date, r.breach.days_late)
            for r in listed
            if r.breach is not None
        },
    )
    mismatches += _compare(
        "compensation_paise",
        {(oid, int(p)) for oid, p in (expect.get("compensation_paise") or {}).items()},
        {
            (r.obligation_id, int(r.compensation.amount_paise))
            for r in listed
            if r.compensation is not None and r.compensation.amount_paise > 0
        },
    )
    mismatches += _compare(
        "required_actions",
        {(a["obligation_id"], a["action"]) for a in expect.get("required_actions") or []},
        {(r.obligation_id, a.action) for r in listed for a in r.required_actions},
    )
    want_outputs: Mapping[str, Any] = expect.get("outputs") or {}
    got_outputs = {r.obligation_id: r.outputs for r in listed}
    for oid in ids:
        want_out: dict[str, Any] = dict(want_outputs.get(oid) or {})
        got_out: dict[str, Any] = dict(got_outputs.get(oid) or {})
        if want_out != got_out:
            mismatches.append(f"outputs: {oid} expected {want_out}, got {got_out}")
    for oid in sorted(set(want_outputs) - set(ids)):
        mismatches.append(f"outputs: {oid} is not in obligation_ids")
    return ScenarioOutcome(listed, mismatches)
