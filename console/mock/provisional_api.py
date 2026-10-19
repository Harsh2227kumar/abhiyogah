"""Provisional engine API for the console, until the platform stream publishes openapi.json.

This declares the read endpoints the console needs, with the domain and registry models on ``main``
as response types, and writes their OpenAPI document next to this file. The console's TypeScript
types are generated from that document (``pnpm openapi``), the same way they will be generated from
the real ``openapi.json``. The routes are never served; the console's mock answers them.

Run from the repository root: ``uv run python console/mock/provisional_api.py``.
"""

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.decision import DecisionRecord, DecisionResult
from abhiyogah.domain.enums import Channel
from abhiyogah.domain.events import ComplaintEvent
from abhiyogah.registry.schema import Obligation

OUT = Path(__file__).with_name("provisional.openapi.json")


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NextDeadline(_Model):
    """The earliest open deadline on a complaint."""

    obligation_id: str
    due_date: date
    result: DecisionResult


class ComplaintSummary(_Model):
    """One row of the deadline board."""

    complaint_id: str
    channel: Channel | None = None
    obligation_ids: list[str] = Field(description="Obligations evaluated on this complaint.")
    next_deadline: NextDeadline | None = None
    open_breaches: int = Field(ge=0)


class ChainStatus(_Model):
    """Whether a complaint's decision-record hash chain verifies."""

    verified: bool
    length: int = Field(ge=0)
    broken_at: int | None = Field(default=None, description="Index of the first bad record.")


class ComplaintDetail(_Model):
    """Everything the complaint view shows, as evaluated at ``as_of``."""

    complaint_id: str
    as_of: AwareDatetime
    events: list[ComplaintEvent]
    facts: ComplaintFacts
    decisions: list[DecisionRecord]
    chain: ChainStatus


class DecisionReplay(_Model):
    """One decision record and the status of the chain it belongs to."""

    record: DecisionRecord
    position: int = Field(ge=0, description="Index of the record in the complaint's chain.")
    chain: ChainStatus


app = FastAPI(title="Abhiyogah engine API (provisional, console mock)", version="0.0.0-mock")


@app.get("/complaints", operation_id="listComplaints")
def list_complaints(as_of: AwareDatetime | None = None) -> list[ComplaintSummary]:
    """Complaints with their next deadline, for the deadline board."""
    raise NotImplementedError


@app.get("/complaints/{complaint_id}", operation_id="getComplaint")
def get_complaint(complaint_id: str, as_of: AwareDatetime | None = None) -> ComplaintDetail:
    """One complaint: events, facts, decisions and chain status."""
    raise NotImplementedError


@app.get(
    "/complaints/{complaint_id}/decisions/{obligation_id}",
    operation_id="getDecision",
)
def get_decision(
    complaint_id: str, obligation_id: str, as_of: AwareDatetime | None = None
) -> DecisionReplay:
    """The latest decision record for one obligation on one complaint."""
    raise NotImplementedError


@app.get("/obligations", operation_id="listObligations")
def list_obligations() -> list[Obligation]:
    """Every obligation in the loaded rule pack."""
    raise NotImplementedError


def main() -> None:
    """Write the OpenAPI document."""
    OUT.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
