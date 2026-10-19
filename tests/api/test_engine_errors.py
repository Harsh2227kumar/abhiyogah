"""When the engine cannot evaluate (a rule-pack bug), evidence is kept and errors are explicit."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from abhiyogah.api.app import create_app
from abhiyogah.api.settings import Settings
from abhiyogah.domain.events import EventType
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext
from abhiyogah.worker.schedule import sweep
from tests.api.conftest import CTX, KEYS, READER, WRITER, Clock
from tests.api.test_api import CID, EVENTS
from tests.evaluator.builders import obligation
from tests.workflow.builders import RECEIVED

BROKEN = EngineContext(
    obligations=[obligation(parameters={})],  # a clock without any duration parameter
    calendar=CTX.calendar,
    profile=CTX.profile,
)
NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def test_events_are_kept_when_evaluation_fails() -> None:
    """201 with the engine's error; the events are stored; reads say what failed."""
    store = MemoryStore()
    client = TestClient(
        create_app(settings=Settings(api_keys=KEYS), store=store, ctx=BROKEN, now=Clock(NOW))
    )
    res = client.post(f"/complaints/{CID}/events", json={"events": EVENTS}, headers=WRITER)
    assert res.status_code == 201
    body = res.json()
    assert body["accepted"] == ["API-1", "API-2"]
    assert "max_days" in body["evaluation_error"]
    assert len(store.events(CID)) == 2
    read = client.get(f"/complaints/{CID}", headers=READER)
    assert read.status_code == 500
    assert read.json()["detail"].startswith("the engine could not evaluate")


def test_sweep_continues_past_a_failing_complaint() -> None:
    """One broken complaint is reported; the others are still re-evaluated."""
    store = MemoryStore()
    store.append_events([RECEIVED])  # not triggered: evaluates fine
    rejected = RECEIVED.model_copy(
        update={
            "event_id": "WF-X",
            "complaint_id": "CMP-WF-0",
            "type": EventType.OUTCOME_SET,
            "payload": {"outcome": "WHOLLY_REJECTED"},
        }
    )
    receipt = RECEIVED.model_copy(update={"event_id": "WF-Y", "complaint_id": "CMP-WF-0"})
    store.append_events([receipt, rejected])
    results = {r.complaint_id: r for r in sweep(store, BROKEN, NOW)}
    assert results["CMP-WF-0"].error is not None
    assert results["CMP-WF-1"].error is None
    assert len(results["CMP-WF-1"].appended) == 1
