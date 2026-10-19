"""The scenario runner itself, against the example scenario and a test copy of its obligation.

The full suite over every ``rules/scenarios/*.yaml`` (``test_scenarios.py``) needs the rule pack's
loader and the bank calendar, which arrive with the rule-pack (#16) and calendar (#14) PRs.
"""

import copy
from pathlib import Path
from typing import Any

from abhiyogah.domain.decision import DecisionResult
from tests.clocks.fakes import FakeCalendar
from tests.evaluator.builders import obligation
from tests.scenarios.runner import load_scenario, run_scenario, scenario_events, scenario_files

SCENARIOS = Path(__file__).parents[2] / "rules" / "scenarios"
EXAMPLE = SCENARIOS / "io_20d_ordinary_breach.yaml"
PACK = {"IO-CB-2026-14-1-b": obligation()}
CAL = FakeCalendar()


def example() -> dict[str, Any]:
    """A fresh copy of the example scenario."""
    return copy.deepcopy(load_scenario(EXAMPLE))


def test_scenario_files_skip_underscore_files() -> None:
    """_schema.md and other _ files are not scenarios."""
    names = [p.name for p in scenario_files(SCENARIOS)]
    assert "io_20d_ordinary_breach.yaml" in names
    assert not any(n.startswith("_") for n in names)


def test_events_follow_the_schema() -> None:
    """IDs, complaint ID and provenance as rules/scenarios/_schema.md prescribes."""
    events = scenario_events(example())
    assert [e.event_id for e in events][:2] == [
        "io_20d_ordinary_breach-1",
        "io_20d_ordinary_breach-2",
    ]
    assert {e.complaint_id for e in events} == {"SCN-io_20d_ordinary_breach"}
    assert events[2].provenance.actor == "scenario"
    assert events[0].recorded_at == events[0].occurred_at


def test_example_scenario_passes() -> None:
    """The foundation's example scenario matches exactly."""
    outcome = run_scenario(example(), PACK, CAL)
    assert outcome.mismatches == []
    (record,) = outcome.records
    assert record.result is DecisionResult.BREACHED


def test_results_key_is_checked() -> None:
    """A wrong expected result is reported."""
    spec = example()
    spec["expect"]["results"] = {"IO-CB-2026-14-1-b": "RUNNING"}
    (line,) = run_scenario(spec, PACK, CAL).mismatches
    assert line == "results: IO-CB-2026-14-1-b expected RUNNING, got BREACHED"


def test_missing_and_extra_entries_are_reported() -> None:
    """Set comparisons report both missing and unexpected entries."""
    spec = example()
    spec["expect"]["breaches"] = []
    spec["expect"]["required_actions"].append(
        {"obligation_id": "IO-CB-2026-14-1-b", "action": "SEND_FINAL_REPLY"}
    )
    spec["expect"]["compensation_paise"] = {"IO-CB-2026-14-1-b": 100}
    mismatches = run_scenario(spec, PACK, CAL).mismatches
    assert any(m.startswith("breaches: unexpected") for m in mismatches)
    assert any(m.startswith("required_actions: missing") for m in mismatches)
    assert any(m.startswith("compensation_paise: missing") for m in mismatches)


def test_wrong_due_date_is_reported() -> None:
    """Deadlines compare exactly."""
    spec = example()
    spec["expect"]["deadlines"][0]["due_date"] = "2026-08-24"
    assert any("deadlines: missing" in m for m in run_scenario(spec, PACK, CAL).mismatches)


def test_missing_obligation_fails_not_skips() -> None:
    """A scenario naming an obligation that isn't in the pack fails."""
    outcome = run_scenario(example(), {}, CAL)
    assert outcome.mismatches == ["obligation not in the rule pack: IO-CB-2026-14-1-b"]


def test_outputs_compare_exactly() -> None:
    """An expected output the engine did not produce is reported, as is a stray obligation ID."""
    spec = example()
    spec["expect"]["outputs"] = {"IO-CB-2026-14-1-b": {"x": True}, "OTHER-1": {}}
    mismatches = run_scenario(spec, PACK, CAL).mismatches
    assert mismatches == [
        "outputs: IO-CB-2026-14-1-b expected {'x': True}, got {}",
        "outputs: OTHER-1 is not in obligation_ids",
    ]
