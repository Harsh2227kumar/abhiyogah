"""MCP tools over an in-process API holding the synthetic UPI demo complaint."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from abhiyogah.api.app import create_app
from abhiyogah.api.settings import Settings
from abhiyogah.mcp.tools import EngineTools
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext
from tests.api.conftest import KEYS, READER, WRITER, Clock
from tests.api.test_end_to_end import CID, CTX, EVENTS, REJECTED
from tests.evaluator.test_determinations import P, clockless

REPLY = clockless(
    "IO-CB-2026-14-11-12",
    trigger={"event": "FINAL_REPLY_SENT"},
    anchor="final_reply_date",
    parameters={"required_elements": {"2026-01-14": {"value": ["B", "A"], **P}}},
)
DEMO_CTX = EngineContext(
    obligations=[*CTX.obligations, REPLY], calendar=CTX.calendar, profile=CTX.profile
)
REPLIED = {
    "event_id": "UPI-5",
    "type": "FINAL_REPLY_SENT",
    "occurred_at": "2026-08-11T11:00:00+05:30",
    "payload": {"reply_elements": ["A"]},
}


@dataclass
class Demo:
    """The API (as a client and an app) and its clock, with the demo complaint posted."""

    app: FastAPI
    client: TestClient
    clock: Clock

    def tools(self, headers: dict[str, str] = READER) -> EngineTools:
        """MCP tools over this app, in-process, with the given key."""
        transport = httpx.ASGITransport(app=self.app)
        return EngineTools.over(transport, headers["X-API-Key"], "http://test")


@pytest.fixture
def demo() -> Iterator[Demo]:
    """The demo complaint, rejected on 10 Aug and replied to (one element short) on 11 Aug."""
    clock = Clock(datetime(2026, 8, 3, 6, tzinfo=UTC))
    app = create_app(settings=Settings(api_keys=KEYS), store=MemoryStore(), ctx=DEMO_CTX, now=clock)
    with TestClient(app) as client:
        for at, events in (
            (datetime(2026, 8, 3, 6, tzinfo=UTC), EVENTS),
            (datetime(2026, 8, 10, 6, tzinfo=UTC), [REJECTED]),
            (datetime(2026, 8, 11, 6, tzinfo=UTC), [REPLIED]),
        ):
            clock.at = at
            res = client.post(f"/complaints/{CID}/events", json={"events": events}, headers=WRITER)
            assert res.status_code == 201, res.text
        clock.at = datetime(2026, 8, 12, 6, tzinfo=UTC)
        yield Demo(app, client, clock)
