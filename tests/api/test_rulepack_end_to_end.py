"""Definition of done: the UPI fraud demo through the API against the real rule pack.

Loads every obligation in ``rules/obligations`` (all DRAFT) with the real bank calendar, posts a
synthetic unauthorised-UPI complaint and checks what tasks/04-platform.md asks for: the IO
deadline, the shadow-credit deadline and the liability tier; then time travel past day 20 shows
the breach and the required IO referral, and the decision chain verifies. Dates are hand-checked
in the comments; no value here is new, each comes from the obligation files.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from abhiyogah.api.app import create_app
from abhiyogah.api.rulepack import load_obligations
from abhiyogah.api.settings import Settings
from abhiyogah.calendar import load_bank_calendar
from abhiyogah.evaluator import EntityProfile
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext
from abhiyogah.worker.schedule import sweep
from abhiyogah.workflow import REFER_TO_IO
from tests.api.conftest import ADMIN, KEYS, READER, WRITER, Clock
from tests.api.test_end_to_end import CID, EVENTS, REJECTED

RULES = Path(__file__).parents[2] / "rules" / "obligations"
PROFILE = EntityProfile.model_validate(
    {
        "entity_type": "COMMERCIAL_BANK",
        "outlets": 120,
        "outlets_as_on": "2025-03-31",
        "home_branch_state": "MH",
    }
)
FAULT: dict[str, Any] = {
    "event_id": "UPI-5",
    "type": "FACTS_RECORDED",
    "occurred_at": "2026-08-03T10:00:00+05:30",
    "payload": {"liability_fault": "THIRD_PARTY"},
}


def by_id(items: list[dict[str, Any]], key: str = "obligation_id") -> dict[str, dict[str, Any]]:
    """Index API items by obligation ID."""
    return {i[key]: i for i in items}


def test_upi_fraud_demo_against_the_rule_pack() -> None:
    """IO deadline, shadow credit, liability tier; day-25 breach and IO referral; chain verifies."""
    ctx = EngineContext(load_obligations(RULES), load_bank_calendar(), PROFILE)
    assert len(ctx.obligations) >= 20
    store = MemoryStore()
    clock = Clock(datetime(2026, 8, 3, 6, tzinfo=UTC))
    client = TestClient(
        create_app(settings=Settings(api_keys=KEYS), store=store, ctx=ctx, now=clock)
    )

    posted = client.post(
        f"/complaints/{CID}/events", json={"events": [*EVENTS, FAULT]}, headers=WRITER
    ).json()
    assert posted["evaluation_error"] is None
    body = client.get(f"/complaints/{CID}", headers=READER).json()
    deadlines = by_id(body["deadlines"])
    # Shadow credit (RBCCB-2025-72, 10 working days): reported Mon 3 Aug; closed in MH on the
    # 2nd Saturday (8 Aug), Sundays and 15 Aug, so the 10th working day is Mon 17 Aug.
    assert deadlines["RBCCB-2025-72"]["deadline"]["due_date"] == "2026-08-17"
    # Liability tier (RBCCB-2025-67-71): third-party fault reported 1 working day after the alert.
    tier = by_id(body["decisions"])["RBCCB-2025-67-71"]
    assert tier["result"] == "DETERMINED"
    assert tier["outputs"]["liability_tier"] == "ZERO"
    assert tier["outputs"]["customer_liability_paise"] == 0

    clock.at = datetime(2026, 8, 10, 6, tzinfo=UTC)
    client.post(f"/complaints/{CID}/events", json={"events": [REJECTED]}, headers=WRITER)
    body = client.get(f"/complaints/{CID}", headers=READER).json()
    # IO referral (IO-CB-2026-14-1-b): receipt 3 Aug + 20 calendar days = 23 Aug.
    io = by_id(body["deadlines"])["IO-CB-2026-14-1-b"]
    assert (io["deadline"]["due_date"], io["result"]) == ("2026-08-23", "RUNNING")

    clock.at = datetime(2026, 8, 25, 6, tzinfo=UTC)
    sweep(store, ctx, clock.at)
    travel = client.get(
        f"/complaints/{CID}", params={"as_of": "2026-08-25T12:00:00+05:30"}, headers=ADMIN
    ).json()
    breaches = {b["breach"]["obligation_id"]: b["breach"]["days_late"] for b in travel["breaches"]}
    assert breaches["IO-CB-2026-14-1-b"] == 2
    assert breaches["RBCCB-2025-72"] == 8
    actions = {(a["action"]["action"], a["action"]["due_date"]) for a in travel["required_actions"]}
    assert (REFER_TO_IO, "2026-08-23") in actions

    chain = client.get(f"/complaints/{CID}/decisions", headers=READER).json()
    assert chain["chain"]["verified"] is True
    assert chain["chain"]["length"] == len(chain["records"]) > 20
