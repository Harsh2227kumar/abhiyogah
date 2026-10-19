"""The plan's end-to-end demo, as an API client. Started by ``scripts/demo.sh``; stdlib only.

Posts a synthetic UPI fraud complaint dated relative to today, so the API (which refuses events in
the future and reads facts bitemporally) accepts it at any time, then:

1. shows the deadlines (shadow credit B6, IO referral A13) and the liability tier (B5);
2. time-travels past day 20 after bank receipt: the IO referral is breached and still required;
3. prints the clause-cited explanation of the stored A13 decision.

Settings come from the environment: ``ABHIYOGAH_DEMO_API_URL`` (default ``http://localhost:8000``),
``ABHIYOGAH_DEMO_WRITER_KEY`` and ``ABHIYOGAH_DEMO_ADMIN_KEY``.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
A13 = "IO-CB-2026-14-1-b"
B5 = "RBCCB-2025-67-71"


class Api:
    """A minimal JSON client for the engine API."""

    def __init__(self, base: str, writer_key: str, admin_key: str) -> None:
        """Remember the base URL and the two demo keys."""
        if urllib.parse.urlsplit(base).scheme not in ("http", "https"):
            raise SystemExit(f"ABHIYOGAH_DEMO_API_URL must be http(s): {base}")
        self.base = base.rstrip("/")
        self.writer_key = writer_key
        self.admin_key = admin_key

    def call(self, method: str, path: str, body: object = None, key: str | None = None) -> Any:
        """Send one request and return the decoded JSON body; exit on an HTTP error."""
        req = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            self.base + path,
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-API-Key": key or self.admin_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310
                return json.loads(res.read() or b"null")
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"{method} {path} failed: {exc.code} {exc.read().decode()}") from exc

    def wait_healthy(self, seconds: int = 300) -> None:
        """Poll /health until the API answers (it installs its dependencies on first start)."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                if self.call("GET", "/health") == {"status": "ok"}:
                    return
            except (urllib.error.URLError, ConnectionError, SystemExit):
                pass
            time.sleep(3)
        raise SystemExit(f"the API at {self.base} did not become healthy in {seconds}s")


def at(day: date, hour: int, minute: int = 0) -> str:
    """An ISO instant on ``day`` at ``hour:minute`` IST."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST).isoformat()


def events(today: date) -> list[dict[str, Any]]:
    """The demo complaint's business events, all in the past. Synthetic data only."""
    alert, report, outcome = today - timedelta(14), today - timedelta(7), today - timedelta(2)
    return [
        {
            "event_id": "DEMO-1",
            "type": "ALERT_RECEIVED",
            "occurred_at": at(alert, 10),
            "source": "SYSTEM",
            "payload": {
                "transaction_date_t": alert.isoformat(),
                "channel": "UPI_P2P",
                "account_type": "OTHER_SAVINGS",
                "amount_paise": 800000,
            },
        },
        {
            "event_id": "DEMO-2",
            "type": "CUSTOMER_REPORTED",
            "occurred_at": at(report, 9),
            "payload": {"issue_type": "UNAUTHORISED_TRANSACTION"},
        },
        {
            "event_id": "DEMO-3",
            "type": "BANK_RECEIVED",
            "occurred_at": at(report, 9, 5),
            "payload": {"handling_unit": "BR-DEMO-01"},
        },
        {
            "event_id": "DEMO-4",
            "type": "FACTS_RECORDED",
            "occurred_at": at(report, 16),
            "payload": {"liability_fault": "THIRD_PARTY"},
        },
        {
            "event_id": "DEMO-5",
            "type": "OUTCOME_SET",
            "occurred_at": at(outcome, 11),
            "payload": {"outcome": "WHOLLY_REJECTED"},
        },
    ]


def show(title: str, body: dict[str, Any]) -> None:
    """Print a complaint's deadlines, breaches, outputs and required actions."""
    print(f"\n--- {title} (as of {body['as_of']})")
    for d in body["deadlines"]:
        dl = d["deadline"]
        print(
            f"  deadline  {d['obligation_id']:<20} cl. {d['clause']:<22} due {dl['due_date']}"
            f"  {d['result']}  ({dl['basis']}, {dl['rule']})"
        )
    for r in body["decisions"]:
        if r["outputs"]:
            print(f"  output    {r['obligation_id']:<20} {json.dumps(r['outputs'])}")
    for b in body["breaches"]:
        br = b["breach"]
        print(
            f"  BREACH    {br['obligation_id']:<20} cl. {b['clause']:<22} due {br['due_date']}"
            f"  {br['days_late']} day(s) late"
        )
    for a in body["required_actions"]:
        act = a["action"]
        print(f"  action    {act['action']:<20} due {act['due_date']}  {act['reason']}")


def main() -> None:
    """Run the demo."""
    api = Api(
        os.environ.get("ABHIYOGAH_DEMO_API_URL", "http://localhost:8000"),
        os.environ["ABHIYOGAH_DEMO_WRITER_KEY"],
        os.environ["ABHIYOGAH_DEMO_ADMIN_KEY"],
    )
    api.wait_healthy()
    today = datetime.now(IST).date()
    cid = f"CMP-DEMO-{datetime.now(IST):%Y%m%d%H%M%S}"
    evs = events(today)
    print(f"==> Posting synthetic UPI fraud complaint {cid}")
    res = api.call("POST", f"/complaints/{cid}/events", {"events": evs}, key=api.writer_key)
    print(f"    accepted {len(res['accepted'])} events, {res['decisions_appended']} decisions")
    if res.get("evaluation_error"):
        raise SystemExit(f"engine error: {res['evaluation_error']}")

    show("Now", api.call("GET", f"/complaints/{cid}"))
    if not any(r["obligation_id"] == B5 for r in api.call("GET", "/obligations")):
        print("  (no B5 obligation in this rule pack: no liability tier)")

    receipt = date.fromisoformat(evs[2]["occurred_at"][:10])
    travel = at(receipt + timedelta(22), 12)
    query = urllib.parse.urlencode({"as_of": travel})
    show("Time travel past day 20", api.call("GET", f"/complaints/{cid}?{query}"))

    stored = api.call("GET", f"/complaints/{cid}/decisions/{A13}")
    explain = api.call("GET", f"/decisions/{stored['record']['hash']}/explain")
    print(f"\n--- Stored decision {A13} (chain verified: {explain['chain']['verified']})")
    for line in explain["lines"]:
        print(f"  {line}")
    print("\nThe MCP step (an agent gets the same result) follows once stream 07 lands.")


if __name__ == "__main__":
    try:
        main()
    except KeyError as exc:
        sys.exit(f"missing setting {exc}; start the demo with scripts/demo.sh")
