"""Every rule-pack scenario, evaluated on the real bank calendar, matches exactly.

Loads the pack from ``rules/obligations/`` and every ``rules/scenarios/*.yaml`` (files starting
with ``_`` excepted), runs the evaluator through ``tests/scenarios/runner.py`` and fails on any
difference in results, deadlines, breaches, paise, required actions or outputs. ``make rules`` runs
it.
"""

from functools import cache
from pathlib import Path

import pytest

from abhiyogah.calendar import load_bank_calendar
from abhiyogah.calendar.bank import HolidaysBankCalendar
from abhiyogah.registry.loader import Registry, load_registry
from tests.scenarios.runner import load_scenario, run_scenario, scenario_files

RULES = Path(__file__).parents[2] / "rules"
SCENARIOS = scenario_files(RULES / "scenarios")


@cache
def pack() -> Registry:
    """The rule pack, loaded once."""
    return load_registry(RULES / "obligations")


@cache
def calendar() -> HolidaysBankCalendar:
    """The bank calendar from the overlay data, loaded once."""
    return load_bank_calendar()


def test_scenarios_exist() -> None:
    """The suite is not vacuous."""
    assert len(SCENARIOS) > 1


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario(path: Path) -> None:
    """The engine's records match the scenario's expectations exactly."""
    outcome = run_scenario(load_scenario(path), pack(), calendar())
    assert outcome.mismatches == [], "\n".join(outcome.mismatches)
