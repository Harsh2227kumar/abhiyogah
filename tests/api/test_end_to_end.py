"""End to end over the API: a synthetic UPI fraud complaint from first report to IO breach.

Obligations are test fixtures shaped like the rule pack's (A13 limbs; a shadow-credit clock like
RBCCB-2025-72 with report row B6's 10 working days). The same walk against the merged rule pack,
including the liability tier, is the last item of tasks/04-platform.md.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from abhiyogah.api.app import create_app
from abhiyogah.api.settings import Settings
from abhiyogah.domain.events import EventType
from abhiyogah.evaluator.actions import action_code
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext
from abhiyogah.worker.schedule import sweep
from abhiyogah.workflow import REFER_TO_IO
from tests.api.conftest import ADMIN, KEYS, READER, WRITER, Clock
from tests.clocks.fakes import FakeCalendar
from tests.evaluator.builders import obligation, ordinary_limb, tat_limb
from tests.evaluator.test_evaluate import PROFILE

SHADOW = obligation(
    obligation_id="RBCCB-2025-72",
    instrument="RBI (Commercial Banks – Responsible Business Conduct) Directions, 2025",
    clause="para 72",
    applies_to={"entity_type": "COMMERCIAL_BANK"},
    trigger={
        "event": "CUSTOMER_REPORTED",
        "condition": "issue_type in [UNAUTHORISED_TRANSACTION]",
    },
    clock={
        "start": "CUSTOMER_REPORTED",
        "stop": "SHADOW_CREDITED",
        "basis": "WORKING",
        "basis_status": "EXPLICIT",
    },
    parameters={
        "max_days": {
            "2025-11-28": {
                "value": 10,
                "reference": "para 72 (report row B6)",
                "verification": "PRIMARY_TEXT_READ",
            }
        }
    },
    valid_from="2025-11-28",
)
CTX = EngineContext(
    obligations=[ordinary_limb(), tat_limb(), SHADOW], calendar=FakeCalendar(), profile=PROFILE
)
CID = "CMP-UPI-DEMO-1"
EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "UPI-1",
        "type": "ALERT_RECEIVED",
        "occurred_at": "2026-08-01T10:00:00+05:30",
        "source": "SYSTEM",
        "payload": {
            "transaction_date_t": "2026-08-01",
            "channel": "UPI_P2P",
            "account_type": "OTHER_SAVINGS",
            "amount_paise": 1250000,
        },
    },
    {
        "event_id": "UPI-2",
        "type": "CUSTOMER_REPORTED",
        "occurred_at": "2026-08-03T09:00:00+05:30",
        "payload": {"issue_type": "UNAUTHORISED_TRANSACTION"},
    },
    {
        "event_id": "UPI-3",
        "type": "BANK_RECEIVED",
        "occurred_at": "2026-08-03T09:05:00+05:30",
        "payload": {"handling_unit": "BRANCH-042"},
    },
]
REJECTED = {
    "event_id": "UPI-4",
    "type": "OUTCOME_SET",
    "occurred_at": "2026-08-10T11:00:00+05:30",
    "payload": {"outcome": "WHOLLY_REJECTED"},
}


def deadlines(body: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """obligation_id -> (due_date, result)."""
    return {d["obligation_id"]: (d["deadline"]["due_date"], d["result"]) for d in body["deadlines"]}


def test_upi_fraud_complaint_end_to_end() -> None:
    """Post, reject, time-travel past day 20: breach and IO referral appear; the chain verifies."""
    store = MemoryStore()
    clock = Clock(datetime(2026, 8, 3, 6, tzinfo=UTC))
    client = TestClient(
        create_app(settings=Settings(api_keys=KEYS), store=store, ctx=CTX, now=clock)
    )

    res = client.post(f"/complaints/{CID}/events", json={"events": EVENTS}, headers=WRITER)
    assert res.status_code == 201, res.text
    body = client.get(f"/complaints/{CID}", headers=READER).json()
    # Shadow credit: reported Mon 3 Aug + 10 working days (Sundays closed) = Fri 14 Aug.
    assert deadlines(body)["RBCCB-2025-72"] == ("2026-08-14", "RUNNING")
    assert "IO-CB-2026-14-1-b" not in deadlines(body)  # no adverse outcome yet

    clock.at = datetime(2026, 8, 10, 6, tzinfo=UTC)
    res = client.post(f"/complaints/{CID}/events", json={"events": [REJECTED]}, headers=WRITER)
    assert res.json()["decisions_appended"] >= 1
    body = client.get(f"/complaints/{CID}", headers=READER).json()
    assert deadlines(body)["IO-CB-2026-14-1-b"] == ("2026-08-23", "RUNNING")
    assert body["required_actions"][0]["action"]["action"] == action_code(EventType.SHADOW_CREDITED)

    # The scheduler runs on 25 Aug; the admin time-travels to the same day.
    clock.at = datetime(2026, 8, 25, 6, tzinfo=UTC)
    assert sum(len(r.appended) for r in sweep(store, CTX, clock.at)) == 2
    travel = client.get(
        f"/complaints/{CID}", params={"as_of": "2026-08-25T12:00:00+05:30"}, headers=ADMIN
    ).json()
    breaches = {b["breach"]["obligation_id"]: b["breach"]["days_late"] for b in travel["breaches"]}
    assert breaches == {"IO-CB-2026-14-1-b": 2, "RBCCB-2025-72": 11}
    actions = {(a["action"]["action"], a["action"]["due_date"]) for a in travel["required_actions"]}
    assert (REFER_TO_IO, "2026-08-23") in actions

    chain = client.get(f"/complaints/{CID}/decisions", headers=READER).json()
    assert chain["chain"]["verified"] is True
    assert chain["chain"]["length"] == len(chain["records"]) >= 6
    last = chain["records"][-1]
    lines = client.get(f"/decisions/{last['hash']}/explain", headers=READER).json()["lines"]
    assert any("Breach:" in line for line in lines)
