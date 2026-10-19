"""The calendar version changes whenever the overlay bytes or the holidays version change."""

import re
from pathlib import Path

from abhiyogah.calendar import calendar_version, load_bank_calendar, load_overlay

TODO = "state: {s}\nyear: 2026\ntodo: source it\nholidays: []\n"


def _tree(root: Path, **states: str) -> Path:
    (root / "2026").mkdir(parents=True, exist_ok=True)
    for state, text in states.items():
        (root / "2026" / f"{state}.yaml").write_text(text, encoding="utf-8")
    return root


def test_version_format_and_stability(tmp_path: Path) -> None:
    root = _tree(tmp_path, MH=TODO.format(s="MH"))
    v = calendar_version(load_overlay(root))
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", v)
    assert calendar_version(load_overlay(root)) == v
    assert load_bank_calendar(root).version == v


def test_version_changes_with_overlay_bytes(tmp_path: Path) -> None:
    root = _tree(tmp_path, MH=TODO.format(s="MH"))
    before = calendar_version(load_overlay(root))
    _tree(root, MH="# edited comment\n" + TODO.format(s="MH"))
    assert calendar_version(load_overlay(root)) != before


def test_version_changes_with_added_file(tmp_path: Path) -> None:
    root = _tree(tmp_path, MH=TODO.format(s="MH"))
    before = calendar_version(load_overlay(root))
    _tree(root, KA=TODO.format(s="KA"))
    assert calendar_version(load_overlay(root)) != before


def test_version_changes_with_package_version(tmp_path: Path) -> None:
    overlay = load_overlay(_tree(tmp_path, MH=TODO.format(s="MH")))
    assert calendar_version(overlay, "1.0") != calendar_version(overlay, "1.1")


def test_default_calendar_loads() -> None:
    assert load_bank_calendar().version.startswith("sha256:")
