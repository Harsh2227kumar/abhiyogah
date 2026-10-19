"""The plan's end-to-end demo (docs/plan.md, "End-to-end demo script") on the real start-up path.

A synthetic UPI fraud complaint is posted to the API one business event at a time while the wall
clock moves forward. The engine is built the way the API and worker build it in production: the rule
pack is loaded from YAML files and the bank calendar is the real one (``load_bank_calendar``). Then:

1. deadlines appear: shadow credit (B6) and, once the complaint is rejected, the IO referral (A13);
   the liability tier (B5) is determined once a person records whose fault it was;
2. time travel past day 20 shows the IO breach, and the scheduler sweep records it;
3. auto-escalation: the complaint carries a ``REFER_TO_IO`` action due on the A13 date;
4. the stored decision is clause-cited, explains itself, and replays to the same record.

The MCP step (an agent gets the same result) waits on stream 07; the real-rule-pack version waits on
PR #16. Both are open items in tasks/08-integrator.md. Until then the rules come from
``tests/e2e/rulepack/`` (unchanged DRAFT copies, see its ``_README.md``).

Hand check (home branch MH; 2nd/4th Saturdays and Sundays closed; 15 Aug 2026 is Independence Day):

- B5: working days after the alert on Mon 3 Aug up to the report on Mon 10 Aug are 4-7 Aug and
  10 Aug (Sat 8 Aug is the 2nd Saturday): 5, so the tier is LIMITED (4-7) and the liability is
  min(Rs 8,000, Rs 10,000 savings cap) = 800000 paise.
- B6: 10 working days after Mon 10 Aug: 11-14, 17-21 and 24 Aug (Sat 15 Aug is a holiday and Sat
  22 Aug the 4th Saturday), so due Mon 24 Aug; credited on 21 Aug, on time.
- A13(b): bank receipt 10 Aug + 20 calendar days = 30 Aug; not referred by 1 Sep, so 2 days late.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from abhiyogah.api.app import create_app
from abhiyogah.api.rulepack import load_obligations
from abhiyogah.api.settings import Settings
from abhiyogah.calendar import load_bank_calendar
from abhiyogah.domain.enums import EntityType
from abhiyogah.evaluator import EntityProfile
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext, evaluate_stored
from abhiyogah.worker.schedule import sweep
from abhiyogah.workflow import REFER_TO_IO

RULES = Path(__file__).parent / "rulepack"
WRITER = {"X-API-Key": "demo-writer-key-0123456789"}
ADMIN = {"X-API-Key": "demo-admin-key-01234567890"}
KEYS = "officer-demo:writer:demo-writer-key-0123456789;admin-demo:admin:demo-admin-key-01234567890"
PROFILE = EntityProfile(
    entity_type=EntityType.COMMERCIAL_BANK,
    outlets=120,  # synthetic bank, above the IO Directions' outlet threshold
    outlets_as_on=date(2025, 3, 31),
    home_branch_state="MH",
)
CID = "CMP-DEMO-UPI-1"
A13 = "IO-CB-2026-14-1-b"
B5 = "RBCCB-2025-67-71"
B6 = "RBCCB-2025-72"

EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "DEMO-1",
        "type": "ALERT_RECEIVED",
        "occurred_at": "2026-08-03T10:00:00+05:30",
        "source": "SYSTEM",
        "payload": {
            "transaction_date_t": "2026-08-03",
            "channel": "UPI_P2P",
            "account_type": "OTHER_SAVINGS",
            "amount_paise": 800000,
        },
    },
    {
        "event_id": "DEMO-2",
        "type": "CUSTOMER_REPORTED",
        "occurred_at": "2026-08-10T09:00:00+05:30",
        "payload": {"issue_type": "UNAUTHORISED_TRANSACTION"},
    },
    {
        "event_id": "DEMO-3",
        "type": "BANK_RECEIVED",
        "occurred_at": "2026-08-10T09:05:00+05:30",
        "payload": {"handling_unit": "BR-DEMO-01"},
    },
    {
        "event_id": "DEMO-4",
        "type": "FACTS_RECORDED",
        "occurred_at": "2026-08-10T16:00:00+05:30",
        "payload": {"liability_fault": "THIRD_PARTY"},
    },
    {
        "event_id": "DEMO-5",
        "type": "OUTCOME_SET",
        "occurred_at": "2026-08-20T11:00:00+05:30",
        "payload": {"outcome": "WHOLLY_REJECTED"},
    },
    {
        "event_id": "DEMO-6",
        "type": "SHADOW_CREDITED",
        "occurred_at": "2026-08-21T12:00:00+05:30",
    },
]


@dataclass
class Clock:
    """A settable wall clock."""

    at: datetime

    def __call__(self) -> datetime:
        """The current instant."""
        return self.at


@dataclass
class Demo:
    """The API client plus the parts behind it."""

    client: TestClient
    store: MemoryStore
    ctx: EngineContext
    clock: Clock

    def post(self, event: dict[str, Any]) -> None:
        """Move the clock to just after the event happened, then record it."""
        self.clock.at = datetime.fromisoformat(event["occurred_at"]).astimezone(UTC) + timedelta(
            minutes=1
        )
        res = self.client.post(
            f"/complaints/{CID}/events", json={"events": [event]}, headers=WRITER
        )
        assert res.status_code == 201, res.text
        assert res.json()["evaluation_error"] is None

    def complaint(self, as_of: str | None = None) -> dict[str, Any]:
        """The complaint now, or at ``as_of`` (admin time travel)."""
        params = {"as_of": as_of} if as_of else {}
        res = self.client.get(f"/complaints/{CID}", params=params, headers=ADMIN)
        assert res.status_code == 200, res.text
        body: dict[str, Any] = res.json()
        return body


def results(body: dict[str, Any]) -> dict[str, str]:
    """obligation_id -> result."""
    return {d["obligation_id"]: d["result"] for d in body["decisions"]}


def due(body: dict[str, Any]) -> dict[str, str]:
    """obligation_id -> due date, for computed deadlines."""
    return {d["obligation_id"]: d["deadline"]["due_date"] for d in body["deadlines"]}


def actions(body: dict[str, Any]) -> set[tuple[str, str | None]]:
    """(action code, due date) of every required action."""
    return {(a["action"]["action"], a["action"]["due_date"]) for a in body["required_actions"]}


@pytest.fixture
def demo() -> Demo:
    """The API wired like production (YAML rule pack, real calendar) on an in-memory store."""
    ctx = EngineContext(
        obligations=load_obligations(RULES), calendar=load_bank_calendar(), profile=PROFILE
    )
    assert {o.obligation_id for o in ctx.obligations} >= {A13, B5, B6}
    assert all(o.status == "DRAFT" and o.signed_off_by is None for o in ctx.obligations)
    store = MemoryStore()
    clock = Clock(datetime(2026, 8, 1, tzinfo=UTC))
    app = create_app(settings=Settings(api_keys=KEYS), store=store, ctx=ctx, now=clock)
    return Demo(TestClient(app), store, ctx, clock)


def test_demo_upi_fraud_complaint(demo: Demo) -> None:
    """Deadlines, liability tier, time travel past day 20, escalation, a cited replayable trace."""
    # 1. Alert and report: the shadow-credit clock (B6) starts.
    for event in EVENTS[:3]:
        demo.post(event)
    body = demo.complaint()
    assert due(body) == {B6: "2026-08-24"}
    assert results(body)[B5] == "NOT_TRIGGERED"  # nobody has recorded whose fault it was yet
    assert actions(body) == {("SHADOW_CREDIT", "2026-08-24")}

    # A person records the fault: the liability tier (B5) is determined.
    demo.post(EVENTS[3])
    tier = next(d for d in demo.complaint()["decisions"] if d["obligation_id"] == B5)
    assert tier["result"] == "DETERMINED"
    assert tier["outputs"] == {
        "delay_working_days": 5,
        "liability_tier": "LIMITED",
        "customer_liability_paise": 800000,
    }

    # Rejected: the IO referral clock (A13, 20 days from bank receipt) applies.
    demo.post(EVENTS[4])
    body = demo.complaint()
    assert due(body) == {B6: "2026-08-24", A13: "2026-08-30"}
    assert (REFER_TO_IO, "2026-08-30") in actions(body)

    # Shadow credit on 21 Aug: B6 stops on time and its action goes away.
    demo.post(EVENTS[5])
    body = demo.complaint()
    assert results(body)[B6] == "STOPPED_ON_TIME"
    assert actions(body) == {(REFER_TO_IO, "2026-08-30")}

    # 2. Time travel past day 20: nothing new happened, but A13 is now breached.
    travel = demo.complaint(as_of="2026-09-01T12:00:00+05:30")
    assert results(travel)[A13] == "BREACHED"
    assert [b["breach"] for b in travel["breaches"]] == [
        {"obligation_id": A13, "due_date": "2026-08-30", "stop_date": None, "days_late": 2}
    ]

    # 3. Auto-escalation: the scheduler records the breach; the referral is still required.
    demo.clock.at = datetime(2026, 9, 1, 6, 30, tzinfo=UTC)
    appended = [r for res in sweep(demo.store, demo.ctx, demo.clock.at) for r in res.appended]
    assert [(r.obligation_id, r.result) for r in appended] == [(A13, "BREACHED")]
    assert (REFER_TO_IO, "2026-08-30") in actions(demo.complaint())

    # 4. The stored decision cites its clause and parameter, explains itself and replays.
    res = demo.client.get(f"/complaints/{CID}/decisions/{A13}", headers=ADMIN).json()
    record = res["record"]
    assert res["chain"]["verified"] is True
    assert record["clause"] == "14(1)(b)"
    assert [(p["name"], p["value"], p["reference"]) for p in record["parameters"]] == [
        ("max_days", 20, "cl. 14(1)(b)")
    ]
    assert {f["name"] for f in record["input_facts"]} >= {"bank_receipt_date", "outcome"}
    lines = demo.client.get(f"/decisions/{record['hash']}/explain", headers=ADMIN).json()["lines"]
    text = "\n".join(lines)
    assert "14(1)(b)" in text
    assert "Breach" in text

    stored = demo.store.decisions(CID)[-1]
    replayed = next(
        r
        for r in evaluate_stored(demo.store.events(CID), demo.ctx, CID, stored.as_of)
        if r.obligation_id == A13
    )
    assert (
        replayed.canonical_json()
        == stored.model_copy(update={"prev_hash": replayed.prev_hash}).canonical_json()
    )
