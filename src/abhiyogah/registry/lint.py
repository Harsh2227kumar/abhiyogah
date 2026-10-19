"""Policy linter for the rule pack (``make rules``).

The schema checks structure; this module checks the policies in CLAUDE.md and ``rules/README.md``:

- every obligation cites a clause and a source URL;
- ``IN_FORCE`` needs ``verification: PRIMARY_TEXT_READ`` and ``signed_off_by`` (hard rule 1);
- no clock has a pause rule (hard rule 3, open question Q3);
- every dated parameter value has a reference;
- the file is named ``<obligation_id>.yaml`` and no two files share an ID or overlap in validity;
- ``overridden_by`` names known obligations and ``tests`` names existing scenario files;
- every scenario names only obligations that exist;
- every parameter's ``open_question`` is a row of ``docs/open-questions.md`` naming the obligation
  (checked when that file sits next to the rules directory).

Run as ``python -m abhiyogah.registry.lint <rules-dir>``; exits 1 when any issue is found.
"""

import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from abhiyogah.domain.enums import RuleStatus, Verification
from abhiyogah.registry.errors import ObligationFileError
from abhiyogah.registry.loader import load_obligation, obligation_files
from abhiyogah.registry.schema import Obligation

__all__ = ["LintIssue", "lint_rules", "main"]


@dataclass(frozen=True, slots=True)
class LintIssue:
    """One problem found in a rule-pack file."""

    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def _blank(value: object) -> bool:
    """True when a required text value is missing or only whitespace."""
    return value is None or (isinstance(value, str) and not value.strip())


def _raw_checks(path: Path, data: dict[str, Any]) -> list[LintIssue]:
    """Policy checks on the raw mapping, so they report even when the schema refuses the file."""
    issues: list[LintIssue] = []
    for key in ("clause", "source_url"):
        if _blank(data.get(key)):
            issues.append(LintIssue(path, f"missing {key}"))
    if data.get("status") == RuleStatus.IN_FORCE and (
        data.get("verification") != Verification.PRIMARY_TEXT_READ
        or _blank(data.get("signed_off_by"))
    ):
        issues.append(
            LintIssue(path, "IN_FORCE needs verification PRIMARY_TEXT_READ and signed_off_by")
        )
    clock = data.get("clock")
    if isinstance(clock, dict) and clock.get("pause") is not None:
        issues.append(
            LintIssue(path, "clock.pause must be null (pause semantics not researched, Q3)")
        )
    parameters = data.get("parameters") or {}
    if isinstance(parameters, dict):
        for name, history in parameters.items():
            for effective, entry in (history or {}).items():
                if not isinstance(entry, dict) or _blank(entry.get("reference")):
                    issues.append(
                        LintIssue(path, f"parameter {name} @ {effective} has no reference")
                    )
    return issues


def _overlaps(a: Obligation, b: Obligation) -> bool:
    """True when the validity periods of ``a`` and ``b`` share at least one day."""
    a_end = a.valid_to or date.max
    b_end = b.valid_to or date.max
    return a.valid_from <= b_end and b.valid_from <= a_end


def _scenario_issues(scenarios_dir: Path, known: set[str]) -> list[LintIssue]:
    """Every scenario names only obligations that exist and matches its file name."""
    issues: list[LintIssue] = []
    if not scenarios_dir.is_dir():
        return issues
    for path in sorted(scenarios_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            issues.append(LintIssue(path, f"cannot read YAML: {exc}"))
            continue
        if not isinstance(spec, dict):
            issues.append(LintIssue(path, "top level is not a mapping"))
            continue
        if spec.get("name") != path.stem:
            issues.append(LintIssue(path, f"name {spec.get('name')!r} differs from file name"))
        for oid in spec.get("obligation_ids") or []:
            if oid not in known:
                issues.append(LintIssue(path, f"unknown obligation {oid!r}"))
    return issues


def _open_question_rows(path: Path) -> dict[str, str]:
    """Map ``Q<n>`` to its table row in ``docs/open-questions.md``."""
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 2 and cells[1].startswith("Q") and cells[1][1:].isdigit():
            rows[cells[1]] = line
    return rows


def _open_question_issues(
    questions: Path, loaded: dict[str, list[tuple[Path, Obligation]]]
) -> list[LintIssue]:
    """Every flagged parameter names an existing question whose row lists the obligation ID."""
    issues: list[LintIssue] = []
    rows = _open_question_rows(questions)
    for oid, versions in sorted(loaded.items()):
        for path, ob in versions:
            for name, history in ob.parameters.items():
                for effective, value in history.items():
                    q = value.open_question
                    if q is None:
                        continue
                    where = f"parameter {name} @ {effective.isoformat()}"
                    if q not in rows:
                        issues.append(
                            LintIssue(path, f"{where}: open question {q} not in {questions}")
                        )
                    elif oid not in rows[q]:
                        issues.append(
                            LintIssue(path, f"{where}: {questions} row {q} does not list {oid}")
                        )
    return issues


def lint_rules(rules_dir: Path) -> list[LintIssue]:
    """Lint ``<rules_dir>/obligations`` and ``<rules_dir>/scenarios``; return every issue found."""
    obligations_dir = rules_dir / "obligations"
    scenarios_dir = rules_dir / "scenarios"
    issues: list[LintIssue] = []
    loaded: dict[str, list[tuple[Path, Obligation]]] = defaultdict(list)

    files = obligation_files(obligations_dir) if obligations_dir.is_dir() else []
    for path in files:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            issues.append(LintIssue(path, f"cannot read YAML: {exc}"))
            continue
        if not isinstance(raw, dict):
            issues.append(LintIssue(path, "top level is not a mapping"))
            continue
        raw_issues = _raw_checks(path, raw)
        issues.extend(raw_issues)
        try:
            ob = load_obligation(path)
        except ObligationFileError as exc:
            if not raw_issues:
                issues.append(LintIssue(path, f"schema: {exc.reason}"))
            continue
        if path.stem != ob.obligation_id:
            issues.append(LintIssue(path, f"file must be named {ob.obligation_id}.yaml"))
        loaded[ob.obligation_id].append((path, ob))

    known = set(loaded)
    for oid, versions in sorted(loaded.items()):
        for i, (path, ob) in enumerate(versions):
            for other_path, other in versions[:i]:
                kind = "overlapping validity periods" if _overlaps(ob, other) else "duplicate"
                issues.append(LintIssue(path, f"{kind} for {oid} (also in {other_path})"))
            for target in ob.overridden_by:
                if target not in known:
                    issues.append(
                        LintIssue(path, f"overridden_by names unknown obligation {target!r}")
                    )
            for test in ob.tests:
                if not (scenarios_dir / test).is_file():
                    issues.append(
                        LintIssue(path, f"test file {test!r} not found in {scenarios_dir}")
                    )

    issues.extend(_scenario_issues(scenarios_dir, known))
    questions = rules_dir.parent / "docs" / "open-questions.md"
    if questions.is_file():
        issues.extend(_open_question_issues(questions, loaded))
    return issues


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: print every issue and return 1 if there were any."""
    args = sys.argv[1:] if argv is None else argv
    rules_dir = Path(args[0]) if args else Path("rules")
    issues = lint_rules(rules_dir)
    for issue in issues:
        print(issue)
    count = (
        len(obligation_files(rules_dir / "obligations"))
        if (rules_dir / "obligations").is_dir()
        else 0
    )
    print(f"rules: {count} obligation file(s), {len(issues)} issue(s)")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
