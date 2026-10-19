"""registry.loader: loading the rule pack."""

from pathlib import Path

import pytest

from abhiyogah.registry.errors import DuplicateObligationError, ObligationFileError
from abhiyogah.registry.loader import load_obligation, load_registry
from tests.registry.conftest import WriteObligation

RULES = Path(__file__).parents[2] / "rules" / "obligations"


def test_loads_every_file_keyed_by_id(write_obligation: WriteObligation, tmp_path: Path) -> None:
    """Each file becomes one entry keyed by its obligation_id."""
    write_obligation(obligation_id="TEST-2026-1")
    write_obligation(obligation_id="TEST-2026-2")
    registry = load_registry(tmp_path)
    assert sorted(registry) == ["TEST-2026-1", "TEST-2026-2"]


def test_duplicate_id_is_an_error(write_obligation: WriteObligation, tmp_path: Path) -> None:
    """Two files declaring the same obligation_id are refused."""
    write_obligation(file_name="a", obligation_id="TEST-2026-1")
    write_obligation(file_name="b", obligation_id="TEST-2026-1")
    with pytest.raises(DuplicateObligationError, match="TEST-2026-1"):
        load_registry(tmp_path)


def test_underscore_files_are_skipped(write_obligation: WriteObligation, tmp_path: Path) -> None:
    """Notes and templates named _*.yaml are not obligations."""
    (tmp_path / "_template.yaml").write_text("not: an obligation\n", encoding="utf-8")
    write_obligation()
    assert list(load_registry(tmp_path)) == ["TEST-2026-1"]


def test_invalid_file_names_the_path(write_obligation: WriteObligation) -> None:
    """A schema violation is reported with the offending file."""
    path = write_obligation(deontic="SHOULD")
    with pytest.raises(ObligationFileError) as info:
        load_obligation(path)
    assert info.value.path == path


def test_non_mapping_and_bad_yaml_are_errors(tmp_path: Path) -> None:
    """A YAML list or unparsable text is not an obligation."""
    listed = tmp_path / "list.yaml"
    listed.write_text("- 1\n", encoding="utf-8")
    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [\n", encoding="utf-8")
    for path in (listed, broken):
        with pytest.raises(ObligationFileError):
            load_obligation(path)


def test_rule_pack_loads() -> None:
    """The real rule pack loads (empty until the first obligation lands)."""
    if RULES.is_dir():
        load_registry(RULES)
