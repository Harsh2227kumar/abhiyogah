"""Shared helpers for registry tests: a minimal valid obligation and a file writer."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

MINIMAL: dict[str, Any] = {
    "obligation_id": "TEST-2026-1",
    "deontic": "OBLIGATION",
    "subject": "bank",
    "instrument": "Synthetic test instrument",
    "clause": "1",
    "source_url": "https://example.org/instrument.pdf",
    "applies_to": {"entity_type": "COMMERCIAL_BANK"},
    "trigger": {"event": "BANK_RECEIVED"},
    "clock": {
        "start": "BANK_RECEIVED",
        "stop": "FINAL_REPLY_SENT",
        "basis": "CALENDAR",
        "basis_status": "INFERRED",
    },
    "parameters": {
        "max_days": {
            "2026-01-01": {"value": 30, "reference": "cl. 1", "verification": "PRIMARY_TEXT_READ"}
        }
    },
    "valid_from": "2026-01-01",
    "status": "DRAFT",
    "verification": "PRIMARY_TEXT_READ",
}

type WriteObligation = Callable[..., Path]


@pytest.fixture
def write_obligation(tmp_path: Path) -> WriteObligation:
    """Write MINIMAL (with overrides) to ``tmp_path/<file_name or obligation_id>.yaml``."""

    def write(file_name: str | None = None, **overrides: Any) -> Path:
        data = {**MINIMAL, **overrides}
        path = tmp_path / f"{file_name or data['obligation_id']}.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return path

    return write
