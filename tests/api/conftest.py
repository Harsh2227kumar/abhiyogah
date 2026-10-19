"""An API wired to an in-memory store, test obligations and a controllable clock."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from abhiyogah.api.app import create_app
from abhiyogah.api.settings import Settings
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext
from tests.clocks.fakes import FakeCalendar
from tests.evaluator.builders import ordinary_limb, tat_limb
from tests.evaluator.test_evaluate import PROFILE

READER = {"X-API-Key": "reader-key-0123456789"}
WRITER = {"X-API-Key": "writer-key-0123456789"}
ADMIN = {"X-API-Key": "admin-key-01234567890"}
KEYS = ";".join(
    [
        "viewer-1:reader:reader-key-0123456789",
        "officer-1:writer:writer-key-0123456789",
        "admin-1:admin:admin-key-01234567890",
    ]
)
CTX = EngineContext(
    obligations=[ordinary_limb(), tat_limb()], calendar=FakeCalendar(), profile=PROFILE
)


@dataclass
class Clock:
    """A settable wall clock."""

    at: datetime

    def __call__(self) -> datetime:
        """The current instant."""
        return self.at


@dataclass
class Api:
    """The client plus the parts behind it."""

    client: TestClient
    store: MemoryStore
    clock: Clock


@pytest.fixture
def api() -> Api:
    """A fresh API at 10 Aug 2026 12:00 UTC."""
    store = MemoryStore()
    clock = Clock(datetime(2026, 8, 10, 12, tzinfo=UTC))
    app = create_app(settings=Settings(api_keys=KEYS), store=store, ctx=CTX, now=clock)
    return Api(TestClient(app), store, clock)
