"""Tests for the overlay loader and the checked-in data/calendars files."""

from pathlib import Path

import pytest

from abhiyogah.calendar import STATES, OverlayDataError
from abhiyogah.calendar.overlay import DEFAULT_OVERLAY_DIR, load_overlay

SOURCED = """\
state: MH
year: 2026
source_url: https://example.invalid/synthetic
holidays:
  - date: 2026-06-10
    name: Synthetic test closure
"""


def _write(root: Path, year: str, state: str, text: str) -> None:
    (root / year).mkdir(parents=True, exist_ok=True)
    (root / year / f"{state}.yaml").write_text(text, encoding="utf-8")


def test_checked_in_overlay_loads() -> None:
    overlay = load_overlay(DEFAULT_OVERLAY_DIR)
    assert {state for state, _ in overlay.files} == set(STATES)
    for f in overlay.files.values():
        assert f.holidays == () or f.source_url is not None


def test_sourced_file_loads(tmp_path: Path) -> None:
    _write(tmp_path, "2026", "MH", SOURCED)
    overlay = load_overlay(tmp_path)
    assert len(overlay.holidays()[("MH", 2026)]) == 1
    assert overlay.unsourced() == frozenset()


def test_todo_file_is_unsourced(tmp_path: Path) -> None:
    _write(tmp_path, "2026", "KA", "state: KA\nyear: 2026\ntodo: source it\nholidays: []\n")
    assert load_overlay(tmp_path).unsourced() == {("KA", 2026)}


@pytest.mark.parametrize(
    ("year", "state", "text"),
    [
        ("2026", "MH", "state: MH\nyear: 2026\nholidays: []\n"),
        (
            "2026",
            "MH",
            "state: MH\nyear: 2026\ntodo: x\nholidays:\n  - {date: 2026-06-10, name: x}\n",
        ),
        ("2026", "MH", SOURCED.replace("2026-06-10", "2027-06-10")),
        ("2026", "KA", SOURCED),
        ("2027", "MH", SOURCED),
        ("2026", "XX", SOURCED.replace("MH", "XX")),
        ("2026", "MH", SOURCED + "  - date: 2026-06-10\n    name: dup\n"),
        ("2026", "MH", "state: [unclosed\n"),
        ("year", "MH", SOURCED),
    ],
)
def test_bad_files_rejected(tmp_path: Path, year: str, state: str, text: str) -> None:
    _write(tmp_path, year, state, text)
    with pytest.raises(OverlayDataError):
        load_overlay(tmp_path)
