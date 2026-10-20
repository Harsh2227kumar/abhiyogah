"""The REST API over an in-memory store: events, evaluation, time travel, ledger and gates."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.routing import APIRoute

from abhiyogah.api.app import create_app
from abhiyogah.api.settings import Settings
from abhiyogah.workflow import REFER_TO_IO
from tests.api.conftest import ADMIN, CTX, READER, WRITER, Api

CID = "CMP-API-1"
EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "API-1",
        "type": "BANK_RECEIVED",
        "occurred_at": "2026-08-03T05:30:00Z",
        "payload": {"handling_unit": "BRANCH-042"},
    },
    {
        "event_id": "API-2",
        "type": "OUTCOME_SET",
        "occurred_at": "2026-08-10T05:30:00Z",
        "payload": {"outcome": "WHOLLY_REJECTED"},
    },
]


def post(api: Api, events: list[dict[str, Any]] = EVENTS, cid: str = CID) -> Any:
    """Post events as the writer."""
    return api.client.post(f"/complaints/{cid}/events", json={"events": events}, headers=WRITER)


def test_posting_events_records_them_and_appends_decisions(api: Api) -> None:
    """New events are stored with the server's recorded_at and the writer as actor."""
    res = post(api)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["accepted"] == ["API-1", "API-2"]
    assert body["decisions_appended"] == 2
    (first, _) = api.store.events(CID)
    assert first.recorded_at == api.clock.at
    assert first.provenance.actor == "officer-1"


def test_complaint_shows_io_deadline_and_required_referral(api: Api) -> None:
    """Receipt 3 Aug + 20 days: refer to the IO by 23 Aug (A13)."""
    post(api)
    res = api.client.get(f"/complaints/{CID}", headers=READER)
    assert res.status_code == 200, res.text
    body = res.json()
    deadline = next(d for d in body["deadlines"] if d["obligation_id"] == "IO-CB-2026-14-1-b")
    assert deadline["deadline"]["due_date"] == "2026-08-23"
    assert deadline["result"] == "RUNNING"
    assert body["breaches"] == []
    actions = [a["action"] for a in body["required_actions"]]
    assert {"action": REFER_TO_IO, "due_date": "2026-08-23"}.items() <= actions[0].items()
    assert body["chain"]["verified"] is True
    assert body["facts"]["outcome"]["value"] == "WHOLLY_REJECTED"


def test_time_travel_past_day_20_shows_the_breach(api: Api) -> None:
    """Admin as_of 25 Aug: two days late; the referral is still required."""
    post(api)
    res = api.client.get(
        f"/complaints/{CID}", params={"as_of": "2026-08-25T12:00:00+05:30"}, headers=ADMIN
    )
    body = res.json()
    (breach,) = body["breaches"]
    assert breach["breach"]["due_date"] == "2026-08-23"
    assert breach["breach"]["days_late"] == 2
    assert body["required_actions"][0]["action"]["action"] == REFER_TO_IO


def test_time_travel_into_the_past_hides_later_events(api: Api) -> None:
    """Receipt recorded 4 Aug, outcome 10 Aug: as of 6 Aug only the receipt is known."""
    api.clock.at = datetime(2026, 8, 4, 12, tzinfo=UTC)
    post(api, EVENTS[:1])
    api.clock.at = datetime(2026, 8, 10, 12, tzinfo=UTC)
    post(api, EVENTS[1:])
    body = api.client.get(
        f"/complaints/{CID}", params={"as_of": "2026-08-06T00:00:00Z"}, headers=ADMIN
    ).json()
    assert [e["event_id"] for e in body["events"]] == ["API-1"]
    assert body["facts"]["outcome"] is None
    assert body["chain"]["length"] == 2  # the receipt-time records only
    early = api.client.get(
        f"/complaints/{CID}", params={"as_of": "2026-08-01T00:00:00Z"}, headers=ADMIN
    )
    assert early.status_code == 404


@pytest.mark.parametrize("headers", [READER, WRITER])
def test_as_of_is_admin_only(api: Api, headers: dict[str, str]) -> None:
    """Time travel needs ADMIN."""
    post(api)
    res = api.client.get(
        f"/complaints/{CID}", params={"as_of": "2026-08-25T00:00:00Z"}, headers=headers
    )
    assert res.status_code == 403


def test_reads_never_write(api: Api) -> None:
    """Time-travel reads leave the ledger alone."""
    post(api)
    before = api.store.decisions(CID)
    api.client.get(f"/complaints/{CID}", params={"as_of": "2026-09-30T00:00:00Z"}, headers=ADMIN)
    api.client.get("/complaints", headers=READER)
    assert api.store.decisions(CID) == before


def test_decisions_are_chained_and_explained(api: Api) -> None:
    """The stored chain verifies; each record is explained from itself."""
    post(api)
    chain = api.client.get(f"/complaints/{CID}/decisions", headers=READER).json()
    assert chain["chain"] == {
        "verified": True,
        "length": 2,
        "broken_at": None,
        "reason": None,
        "head": chain["records"][-1]["hash"],
    }
    record = chain["records"][-1]
    res = api.client.get(f"/decisions/{record['hash']}/explain", headers=READER)
    assert res.status_code == 200
    text = "\n".join(res.json()["lines"])
    assert record["obligation_id"] in text
    assert record["hash"] in text


def test_get_decision_returns_latest_record_for_an_obligation(api: Api) -> None:
    """The console's decision replay route."""
    post(api)
    res = api.client.get(f"/complaints/{CID}/decisions/IO-CB-2026-14-1-b", headers=READER)
    assert res.status_code == 200
    body = res.json()
    assert body["record"]["obligation_id"] == "IO-CB-2026-14-1-b"
    assert body["chain"]["verified"] is True
    missing = api.client.get(f"/complaints/{CID}/decisions/NOPE-2026-1", headers=READER)
    assert missing.status_code == 404


def test_resending_events_is_idempotent(api: Api) -> None:
    """Same events again: nothing new stored, no new decisions."""
    post(api)
    api.clock.at = datetime(2026, 8, 10, 13, tzinfo=UTC)
    body = post(api).json()
    assert body["accepted"] == []
    assert body["already_recorded"] == ["API-1", "API-2"]
    assert body["decisions_appended"] == 0


def test_reusing_an_event_id_is_a_conflict(api: Api) -> None:
    """Evidence is never overwritten."""
    post(api)
    changed = [{**EVENTS[1], "payload": {"outcome": "FULLY_RESOLVED"}}]
    assert post(api, changed).status_code == 409


def test_only_result_changes_append_decisions(api: Api) -> None:
    """A new event that changes nothing material appends no record."""
    post(api)
    comm = {
        "event_id": "API-3",
        "type": "BANK_COMMUNICATION_SENT",
        "occurred_at": "2026-08-10T06:00:00Z",
    }
    assert post(api, [comm]).json()["decisions_appended"] == 0
    referred = {"event_id": "API-4", "type": "IO_REFERRED", "occurred_at": "2026-08-10T07:00:00Z"}
    assert post(api, [referred]).json()["decisions_appended"] >= 1


@pytest.mark.parametrize(
    ("event", "fragment"),
    [
        (
            {"event_id": "X-1", "type": "OUTCOME_SET", "occurred_at": "2026-08-09T00:00:00Z"},
            "outcome",
        ),
        (
            {"event_id": "X-2", "type": "BANK_RECEIVED", "occurred_at": "2026-09-01T00:00:00Z"},
            "future",
        ),
        (
            {
                "event_id": "X-3",
                "type": "BANK_RECEIVED",
                "occurred_at": "2026-08-01T00:00:00Z",
                "source": "LLM",
            },
            "model",
        ),
        (
            {
                "event_id": "X-4",
                "type": "FACTS_RECORDED",
                "occurred_at": "2026-08-01T00:00:00Z",
                "source": "SYSTEM",
                "payload": {"liability_fault": "CUSTOMER"},
            },
            "HUMAN",
        ),
    ],
)
def test_invalid_events_are_refused_and_not_stored(
    api: Api, event: dict[str, Any], fragment: str
) -> None:
    """Bad payloads, future events, incomplete LLM provenance, non-human liability: 422."""
    res = post(api, [event])
    assert res.status_code == 422
    assert fragment in res.text
    assert api.store.events(CID) == []


def test_naive_occurred_at_is_refused(api: Api) -> None:
    """Datetimes must carry an offset."""
    event = {"event_id": "X-5", "type": "BANK_RECEIVED", "occurred_at": "2026-08-01T00:00:00"}
    assert post(api, [event]).status_code == 422


def test_dismissive_finding_opens_a_review_task(api: Api) -> None:
    """A 'not a complaint' finding goes to a person; an 'is a complaint' one does not."""
    post(api)
    finding = {
        "finding_id": "PF-1",
        "kind": "NOT_A_COMPLAINT",
        "model": "test-model",
        "prompt_version": "classify-v1",
    }
    res = api.client.post(f"/complaints/{CID}/findings", json=finding, headers=WRITER)
    assert res.status_code == 201
    assert res.json()["kind"] == "NOT_A_COMPLAINT"
    ok = {**finding, "finding_id": "PF-2", "kind": "IS_COMPLAINT"}
    assert api.client.post(f"/complaints/{CID}/findings", json=ok, headers=WRITER).json() is None
    tasks = api.client.get("/review-tasks", params={"status": "OPEN"}, headers=READER).json()
    assert [t["task_id"] for t in tasks] == ["RT-NOT_A_COMPLAINT-PF-1"]
    detail = api.client.get(f"/complaints/{CID}", headers=READER).json()
    assert [t["task_id"] for t in detail["review_tasks"]] == ["RT-NOT_A_COMPLAINT-PF-1"]


def test_list_complaints_and_board(api: Api) -> None:
    """The board lists the IO deadline 13 days out; within 7 days it is not due yet."""
    post(api)
    (row,) = api.client.get("/complaints", headers=READER).json()
    assert row["complaint_id"] == CID
    assert row["next_deadline"]["due_date"] == "2026-08-23"
    assert row["open_breaches"] == 0
    assert api.client.get("/board/deadlines", headers=READER).json() == []
    board = api.client.get("/board/deadlines", params={"within_days": 14}, headers=READER).json()
    assert [(b["obligation_id"], b["calendar_days_left"]) for b in board] == [
        ("IO-CB-2026-14-1-b", 13)
    ]


def test_obligations_are_listed(api: Api) -> None:
    """The loaded rule pack."""
    ids = [o["obligation_id"] for o in api.client.get("/obligations", headers=READER).json()]
    assert ids == ["IO-CB-2026-14-1-b", "IO-CB-2026-14-1-a"]


def test_closure_check_reports_reasons(api: Api) -> None:
    """The handling branch may not close; another unit is told what is missing."""
    post(api)
    same = api.client.get(
        f"/complaints/{CID}/closure", params={"unit": "BRANCH-042"}, headers=READER
    ).json()
    assert same["allowed"] is False
    codes = [r["code"] for r in same["gate"]["reasons"]]
    assert codes == ["SAME_UNIT_CLOSURE", "SENIOR_REVIEW_MISSING", "IO_DECISION_MISSING"]


def test_unknown_complaint_and_decision_are_404(api: Api) -> None:
    """Missing things are 404, not empty 200s."""
    assert api.client.get("/complaints/NOPE", headers=READER).status_code == 404
    assert api.client.get(f"/decisions/{'0' * 64}/explain", headers=READER).status_code == 404


def test_no_route_works_without_a_key() -> None:
    """Every route but /health refuses anonymous callers, writes included."""
    app = create_app(settings=Settings(api_keys=""), ctx=CTX)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    writes = [r for r in routes if set(r.methods or ()) - {"GET", "HEAD"}]
    assert writes, "expected write routes"
    for route in routes:
        path = route.path.replace("{complaint_id}", "C").replace("{obligation_id}", "O")
        path = path.replace("{decision_id}", "D")
        for method in route.methods or ():
            res = client.request(method, path, json={})
            expected = 200 if route.path == "/health" else 401
            assert res.status_code == expected, (method, route.path)


def test_module_app_starts_from_the_environment() -> None:
    """``abhiyogah.api.app:app`` imports and answers /health."""
    from fastapi.testclient import TestClient

    from abhiyogah.api.app import app

    assert TestClient(app).get("/health").json() == {"status": "ok"}


def open_task(api: Api) -> str:
    """Post events and a dismissive finding; return the review task's ID."""
    post(api)
    finding = {
        "finding_id": "PF-9",
        "kind": "NO_DEFICIENCY",
        "model": "test-model",
        "prompt_version": "classify-v1",
    }
    res = api.client.post(f"/complaints/{CID}/findings", json=finding, headers=WRITER)
    task_id: str = res.json()["task_id"]
    return task_id


def decision(event_id: str, source: str = "HUMAN") -> dict[str, Any]:
    """A FACTS_RECORDED event recording a person's review."""
    return {
        "event_id": event_id,
        "type": "FACTS_RECORDED",
        "occurred_at": "2026-08-10T11:00:00Z",
        "source": source,
        "payload": {},
    }


def test_review_task_is_closed_by_a_human_event(api: Api) -> None:
    """A person's event on the same complaint closes the task, once."""
    task_id = open_task(api)
    post(api, [decision("REV-1")])
    res = api.client.post(
        f"/review-tasks/{task_id}/close", json={"event_id": "REV-1"}, headers=WRITER
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "DONE"
    assert res.json()["closed_by_event_id"] == "REV-1"
    again = api.client.post(
        f"/review-tasks/{task_id}/close", json={"event_id": "REV-1"}, headers=WRITER
    )
    assert again.status_code == 409
    open_ = api.client.get("/review-tasks", params={"status": "OPEN"}, headers=READER).json()
    assert open_ == []


def test_review_task_cannot_be_closed_by_a_system_event_or_another_complaint(api: Api) -> None:
    """Hard rule 4: a feed or a model never settles a review; evidence must be on this complaint."""
    task_id = open_task(api)
    post(api, [decision("REV-SYS", source="SYSTEM")])
    post(api, [decision("REV-OTHER")], cid="CMP-OTHER")
    for event_id, fragment in [("REV-SYS", "person"), ("REV-OTHER", "not on complaint")]:
        res = api.client.post(
            f"/review-tasks/{task_id}/close", json={"event_id": event_id}, headers=WRITER
        )
        assert res.status_code == 422
        assert fragment in res.text
    assert (
        api.client.post(
            f"/review-tasks/{task_id}/close", json={"event_id": "REV-SYS"}, headers=READER
        ).status_code
        == 403
    )
    assert (
        api.client.post(
            "/review-tasks/RT-NOPE/close", json={"event_id": "REV-SYS"}, headers=WRITER
        ).status_code
        == 404
    )


def test_review_task_cannot_be_closed_by_an_earlier_event(api: Api) -> None:
    """The decision is recorded after the task was opened."""
    api.clock.at = datetime(2026, 8, 10, 11, tzinfo=UTC)
    post(api, [decision("REV-EARLY")])
    api.clock.at = datetime(2026, 8, 10, 12, tzinfo=UTC)
    task_id = open_task(api)
    res = api.client.post(
        f"/review-tasks/{task_id}/close", json={"event_id": "REV-EARLY"}, headers=WRITER
    )
    assert res.status_code == 422
    assert "before the task" in res.text
