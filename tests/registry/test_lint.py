"""registry.lint: policy checks over the rule pack."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from abhiyogah.registry.lint import lint_rules, main
from tests.registry.conftest import MINIMAL

RULES = Path(__file__).parents[2] / "rules"


def write_pack(
    root: Path, *obligations: dict[str, Any], scenarios: dict[str, Any] | None = None
) -> Path:
    """Write obligations (MINIMAL plus overrides; ``_file`` sets the file name) and scenarios."""
    (root / "obligations").mkdir()
    (root / "scenarios").mkdir()
    for overrides in obligations:
        data = {**MINIMAL, **overrides}
        name = data.pop("_file", data["obligation_id"])
        (root / "obligations" / f"{name}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    for name, spec in (scenarios or {}).items():
        (root / "scenarios" / f"{name}.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    return root


def messages(root: Path) -> list[str]:
    """The lint messages for the pack under ``root``."""
    return [issue.message for issue in lint_rules(root)]


def test_clean_pack_has_no_issues(tmp_path: Path) -> None:
    """MINIMAL is a clean DRAFT obligation."""
    assert messages(write_pack(tmp_path, {})) == []


@pytest.mark.parametrize("key", ["clause", "source_url"])
def test_missing_citation(tmp_path: Path, key: str) -> None:
    """An obligation without a clause or source URL is refused."""
    assert f"missing {key}" in messages(write_pack(tmp_path, {key: " "}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "IN_FORCE", "verification": "PRIMARY_TEXT_READ"},
        {"status": "IN_FORCE", "verification": "SECONDARY_ONLY", "signed_off_by": "owner"},
    ],
)
def test_in_force_needs_primary_text_and_sign_off(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    """Hard rule 1: IN_FORCE without sign-off or primary text is refused."""
    found = messages(write_pack(tmp_path, overrides))
    assert "IN_FORCE needs verification PRIMARY_TEXT_READ and signed_off_by" in found


def test_overlapping_validity(tmp_path: Path) -> None:
    """Two versions of the same obligation may not be valid on the same day."""
    root = write_pack(
        tmp_path,
        {"_file": "a", "valid_from": "2026-01-01"},
        {"_file": "b", "valid_from": "2026-06-01"},
    )
    assert any(m.startswith("overlapping validity periods for TEST-2026-1") for m in messages(root))


def test_same_id_without_overlap_is_still_a_duplicate(tmp_path: Path) -> None:
    """The loader refuses duplicate IDs, so disjoint versions are reported too."""
    root = write_pack(
        tmp_path,
        {"_file": "a", "valid_from": "2026-01-01", "valid_to": "2026-05-31"},
        {"_file": "b", "valid_from": "2026-06-01"},
    )
    assert any(m.startswith("duplicate for TEST-2026-1") for m in messages(root))


def test_unknown_overridden_by(tmp_path: Path) -> None:
    """overridden_by must point to an obligation in the pack."""
    found = messages(write_pack(tmp_path, {"overridden_by": ["TEST-2026-9"]}))
    assert "overridden_by names unknown obligation 'TEST-2026-9'" in found


def test_missing_test_file(tmp_path: Path) -> None:
    """Every listed scenario file must exist."""
    found = messages(write_pack(tmp_path, {"tests": ["nope.yaml"]}))
    assert any(m.startswith("test file 'nope.yaml' not found") for m in found)


def test_pause_is_refused(tmp_path: Path) -> None:
    """Hard rule 3: no obligation may pause its clock."""
    clock = {
        **MINIMAL["clock"],
        "pause": {"on": "INFO_REQUESTED", "resume": "FACTS_RECORDED", "open_question": "Q3"},
    }
    found = messages(write_pack(tmp_path, {"clock": clock}))
    assert any(m.startswith("clock.pause must be null") for m in found)


def test_parameter_without_reference(tmp_path: Path) -> None:
    """Every dated parameter value cites its source."""
    params = {
        "max_days": {"2026-01-01": {"value": 30, "reference": "", "verification": "UNVERIFIED"}}
    }
    found = messages(write_pack(tmp_path, {"parameters": params}))
    assert "parameter max_days @ 2026-01-01 has no reference" in found


def test_file_name_must_match_id(tmp_path: Path) -> None:
    """The file is named <obligation_id>.yaml."""
    found = messages(write_pack(tmp_path, {"_file": "other"}))
    assert "file must be named TEST-2026-1.yaml" in found


def test_scenario_names_unknown_obligation(tmp_path: Path) -> None:
    """A scenario may only evaluate obligations that exist."""
    spec = {"name": "s1", "obligation_ids": ["TEST-2026-1", "TEST-2026-2"]}
    found = messages(write_pack(tmp_path, {}, scenarios={"s1": spec}))
    assert found == ["unknown obligation 'TEST-2026-2'"]


def test_schema_error_is_reported(tmp_path: Path) -> None:
    """A file the schema refuses is a lint issue, not a crash."""
    found = messages(write_pack(tmp_path, {"deontic": "SHOULD"}))
    assert len(found) == 1
    assert found[0].startswith("schema:")


def test_main_exit_codes(tmp_path: Path) -> None:
    """The CLI exits 0 on a clean pack and 1 otherwise."""
    ok, bad = tmp_path / "ok", tmp_path / "bad"
    ok.mkdir()
    bad.mkdir()
    assert main([str(write_pack(ok, {}))]) == 0
    assert main([str(write_pack(bad, {"clause": ""}))]) == 1


def test_rule_pack_is_clean() -> None:
    """The real rule pack lints clean."""
    assert [str(i) for i in lint_rules(RULES)] == []


def write_questions(root: Path, row: str) -> None:
    """Write a docs/open-questions.md with one table row next to ``root/rules``."""
    (root / "docs").mkdir()
    table = "| # | Question | Why | Affects | Status |\n|---|---|---|---|---|\n" + row + "\n"
    (root / "docs" / "open-questions.md").write_text(table, encoding="utf-8")


def flagged(question: str) -> dict[str, Any]:
    """MINIMAL's parameter flagged with ``question``."""
    value = {
        "value": 30,
        "reference": "cl. 1",
        "verification": "UNVERIFIED",
        "open_question": question,
    }
    return {"parameters": {"max_days": {"2026-01-01": value}}}


def test_open_question_must_exist(tmp_path: Path) -> None:
    """A flagged parameter must name a question in docs/open-questions.md."""
    write_questions(tmp_path, "| Q1 | q | w | TEST-2026-1 | Open |")
    rules = tmp_path / "rules"
    rules.mkdir()
    found = messages(write_pack(rules, flagged("Q9")))
    assert len(found) == 1
    assert "open question Q9 not in" in found[0]


def test_open_question_row_must_list_obligation(tmp_path: Path) -> None:
    """The question's row must name the obligation that it flags."""
    write_questions(tmp_path, "| Q1 | q | w | OTHER-2026-1 | Open |")
    rules = tmp_path / "rules"
    rules.mkdir()
    found = messages(write_pack(rules, flagged("Q1")))
    assert len(found) == 1
    assert "row Q1 does not list TEST-2026-1" in found[0]


def test_open_question_listed_is_clean(tmp_path: Path) -> None:
    """A question row that names the obligation passes."""
    write_questions(tmp_path, "| Q1 | q | w | A2: TEST-2026-1 | Open |")
    rules = tmp_path / "rules"
    rules.mkdir()
    assert messages(write_pack(rules, flagged("Q1"))) == []
