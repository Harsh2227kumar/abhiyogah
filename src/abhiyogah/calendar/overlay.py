"""Load the bank holiday overlay from ``data/calendars/<year>/<state>.yaml``.

Each file lists the Negotiable Instruments Act holidays of one state in one year and names its
source. A file nobody could source yet carries a ``todo`` note and no dates: holiday dates are never
invented (CLAUDE.md hard rule 2). Reading local files is the only I/O here; there is no network.
"""

import hashlib
from datetime import date
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Self

import yaml
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError, model_validator

from abhiyogah.calendar.bank import STATES, HolidaysBankCalendar
from abhiyogah.calendar.errors import OverlayDataError

__all__ = [
    "DEFAULT_OVERLAY_DIR",
    "Overlay",
    "OverlayFile",
    "OverlayHoliday",
    "calendar_version",
    "load_bank_calendar",
    "load_overlay",
]

DEFAULT_OVERLAY_DIR = Path(__file__).resolve().parents[3] / "data" / "calendars"
"""``data/calendars/`` in a source checkout."""


class OverlayHoliday(BaseModel):
    """One NI Act holiday in a state overlay file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    date: date
    name: str = Field(min_length=1)


class OverlayFile(BaseModel):
    """One ``data/calendars/<year>/<state>.yaml`` file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str
    year: int
    source_url: AnyHttpUrl | None = None
    todo: str | None = None
    holidays: tuple[OverlayHoliday, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        """Require a source for any dates, a todo note when unsourced, and dates inside the year."""
        if self.state not in STATES:
            raise ValueError(f"unknown state code {self.state!r}")
        if self.source_url is None and self.todo is None:
            raise ValueError("an overlay needs a source_url, or a todo note if not yet sourced")
        if self.holidays and self.source_url is None:
            raise ValueError("holiday dates need a source_url; never add unsourced dates")
        seen: set[date] = set()
        for h in self.holidays:
            if h.date.year != self.year:
                raise ValueError(f"{h.date} is outside overlay year {self.year}")
            if h.date in seen:
                raise ValueError(f"duplicate holiday {h.date}")
            seen.add(h.date)
        return self

    @property
    def sourced(self) -> bool:
        """True when the file names a source and has no outstanding todo."""
        return self.source_url is not None and self.todo is None


class Overlay(BaseModel):
    """Every overlay file under one directory, keyed by ``(state, year)``."""

    model_config = ConfigDict(frozen=True)

    files: dict[tuple[str, int], OverlayFile]
    digest: str
    """SHA-256 over every file's relative path and exact bytes, in path order."""

    def holidays(self) -> dict[tuple[str, int], frozenset[date]]:
        """Holiday dates keyed by ``(state, year)``, as ``HolidaysBankCalendar`` takes them."""
        return {key: frozenset(h.date for h in f.holidays) for key, f in self.files.items()}

    def unsourced(self) -> frozenset[tuple[str, int]]:
        """The ``(state, year)`` pairs whose overlay still needs a source."""
        return frozenset(key for key, f in self.files.items() if not f.sourced)


def load_overlay(root: Path = DEFAULT_OVERLAY_DIR) -> Overlay:
    """Read and validate every ``<year>/<state>.yaml`` file under ``root``."""
    files: dict[tuple[str, int], OverlayFile] = {}
    sha = hashlib.sha256()
    for path in sorted(root.glob("*/*.yaml")):
        files[_key(path)] = _read(path)
        data = path.read_bytes()
        rel = path.relative_to(root).as_posix().encode()
        sha.update(len(rel).to_bytes(8, "big") + rel + len(data).to_bytes(8, "big") + data)
    return Overlay(files=files, digest=sha.hexdigest())


def calendar_version(overlay: Overlay, holidays_version: str | None = None) -> str:
    """SHA-256 of the overlay digest plus the ``holidays`` package version, as ``sha256:<hex>``.

    Decision records store this so a replay can tell exactly which calendar data produced a date.
    """
    pkg = package_version("holidays") if holidays_version is None else holidays_version
    payload = f"holidays=={pkg}\noverlay={overlay.digest}\n".encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load_bank_calendar(root: Path = DEFAULT_OVERLAY_DIR) -> HolidaysBankCalendar:
    """Load the overlay under ``root`` and return a calendar stamped with its version."""
    overlay = load_overlay(root)
    return HolidaysBankCalendar(overlay.holidays(), version=calendar_version(overlay))


def _key(path: Path) -> tuple[str, int]:
    """Return ``(state, year)`` from a ``<year>/<state>.yaml`` path."""
    try:
        return path.stem, int(path.parent.name)
    except ValueError as exc:
        raise OverlayDataError(f"{path}: directory must be a year") from exc


def _read(path: Path) -> OverlayFile:
    """Parse one overlay file and check it matches its path."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        parsed = OverlayFile.model_validate(raw)
    except (yaml.YAMLError, ValidationError) as exc:
        raise OverlayDataError(f"{path}: {exc}") from exc
    if (parsed.state, parsed.year) != _key(path):
        raise OverlayDataError(f"{path}: state/year do not match the file path")
    return parsed
