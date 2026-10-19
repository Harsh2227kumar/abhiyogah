"""Build the console's mock API data by running the real evaluator over synthetic complaints.

Until the platform stream serves the engine over HTTP, the console reads ``fixtures.json`` written
here. Every deadline, breach, action and decision record in it comes from
``abhiyogah.evaluator.evaluate`` on ``main``; nothing is computed by hand. Complaints, people and
amounts are synthetic.

Obligations come from ``rules/obligations/`` once the rule pack is merged, else from the DRAFT
copies in ``obligations/`` next to this file (taken from the rule-pack stream's branch).

The mock answers a fixed set of ``as_of`` instants (``SNAPSHOTS``). Each complaint's ledger is the
records of every snapshot in order, sealed into one hash chain; ``positions`` gives each record's
index in it, for decision replay. One complaint has a record edited after sealing, so the console
can show a broken chain.

Run from the repository root: ``uv run python console/mock/build_fixtures.py``.
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from provisional_api import (
    ChainStatus,
    ComplaintDetail,
    ComplaintSummary,
    NextDeadline,
)

from abhiyogah.calendar import load_bank_calendar
from abhiyogah.domain.complaint import fold_events
from abhiyogah.domain.decision import GENESIS_HASH, DecisionRecord, DecisionResult
from abhiyogah.domain.enums import EntityType, FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance, TextSpan
from abhiyogah.evaluator import EntityProfile, evaluate
from abhiyogah.registry.schema import Obligation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "fixtures.json"

IST = timezone(timedelta(hours=5, minutes=30))

PROFILE = EntityProfile(
    entity_type=EntityType.COMMERCIAL_BANK,
    outlets=120,
    outlets_as_on=date(2025, 3, 31),
    home_branch_state="MH",
)

SNAPSHOTS = [
    datetime(2026, 9, 10, 18, 0, tzinfo=IST),
    datetime(2026, 9, 20, 18, 0, tzinfo=IST),
    datetime(2026, 10, 1, 18, 0, tzinfo=IST),
    datetime(2026, 10, 12, 18, 0, tzinfo=IST),
    datetime(2026, 10, 19, 18, 0, tzinfo=IST),
    datetime(2026, 10, 21, 18, 0, tzinfo=IST),
    datetime(2026, 11, 2, 18, 0, tzinfo=IST),
]
"""The instants the mock can answer; a request is served from the latest one at or before it."""

TAMPERED = "CMP-2026-000105"
"""The complaint whose ledger is edited after sealing, to show a broken chain."""

CRM = Provenance(source=FactSource.SYSTEM, actor="crm-feed")
OFFICER = Provenance(source=FactSource.HUMAN, actor="officer-synthetic-01")
IO_DESK = Provenance(source=FactSource.HUMAN, actor="io-desk-synthetic")
EXTRACTOR = Provenance(
    source=FactSource.LLM,
    model="synthetic-extractor",
    prompt_version="triage-extract-v0",
    span=TextSpan(document_ref="DOC-SYN-0101", start=42, end=97),
)


def _at(day: str, hhmm: str = "11:00") -> datetime:
    """An IST instant from ``YYYY-MM-DD`` and ``HH:MM``."""
    return datetime.fromisoformat(f"{day}T{hhmm}:00+05:30")


def _events(
    cid: str, rows: list[tuple[EventType, datetime, dict[str, Any], Provenance]]
) -> list[ComplaintEvent]:
    """Number a complaint's events; each is recorded one minute after it occurred."""
    return [
        ComplaintEvent(
            event_id=f"EV-{cid[-6:]}-{i:02d}",
            complaint_id=cid,
            type=etype,
            occurred_at=when,
            recorded_at=when + timedelta(minutes=1),
            payload=payload,
            provenance=prov,
        )
        for i, (etype, when, payload, prov) in enumerate(rows, start=1)
    ]


E = EventType
COMPLAINTS: dict[str, list[ComplaintEvent]] = {
    # Wholly rejected and never referred to the IO: the 20-day clock is due on 19 Oct.
    "CMP-2026-000101": _events(
        "CMP-2026-000101",
        [
            (E.BANK_RECEIVED, _at("2026-09-29", "10:30"), {}, CRM),
            (E.ACKNOWLEDGED, _at("2026-09-29", "10:35"), {}, CRM),
            (
                E.FACTS_RECORDED,
                _at("2026-09-29", "10:40"),
                {"channel": "UPI_P2P", "amount_paise": 245000, "transaction_date_t": "2026-09-27"},
                EXTRACTOR,
            ),
            (E.OUTCOME_SET, _at("2026-10-06", "16:00"), {"outcome": "WHOLLY_REJECTED"}, OFFICER),
        ],
    ),
    # Fully resolved with a final reply inside 30 days.
    "CMP-2026-000102": _events(
        "CMP-2026-000102",
        [
            (E.BANK_RECEIVED, _at("2026-09-10", "09:15"), {"channel": "ATM"}, CRM),
            (E.ACKNOWLEDGED, _at("2026-09-10", "09:20"), {}, CRM),
            (E.OUTCOME_SET, _at("2026-09-24", "15:00"), {"outcome": "FULLY_RESOLVED"}, OFFICER),
            (E.FINAL_REPLY_SENT, _at("2026-09-25", "12:00"), {}, OFFICER),
        ],
    ),
    # Partially resolved; referred to the IO late and replied to late.
    "CMP-2026-000103": _events(
        "CMP-2026-000103",
        [
            (E.BANK_RECEIVED, _at("2026-08-20", "14:00"), {"channel": "IMPS"}, CRM),
            (E.ACKNOWLEDGED, _at("2026-08-21", "10:00"), {}, CRM),
            (E.OUTCOME_SET, _at("2026-08-28", "17:00"), {"outcome": "PARTIALLY_RESOLVED"}, OFFICER),
            (E.IO_REFERRED, _at("2026-09-12", "11:00"), {}, OFFICER),
            (E.IO_DECIDED, _at("2026-09-26", "16:30"), {}, IO_DESK),
            (E.FINAL_REPLY_SENT, _at("2026-09-30", "12:00"), {}, OFFICER),
        ],
    ),
    # Recently received; the 30-day reply clock is running.
    "CMP-2026-000104": _events(
        "CMP-2026-000104",
        [
            (E.BANK_RECEIVED, _at("2026-10-12", "10:00"), {"channel": "POS_CARD_PRESENT"}, CRM),
            (E.ACKNOWLEDGED, _at("2026-10-12", "10:05"), {}, CRM),
        ],
    ),
    # Wholly rejected and referred on time; its ledger is tampered with below.
    TAMPERED: _events(
        TAMPERED,
        [
            (E.BANK_RECEIVED, _at("2026-09-01", "12:00"), {"channel": "UPI_MERCHANT"}, CRM),
            (E.ACKNOWLEDGED, _at("2026-09-01", "12:05"), {}, CRM),
            (E.OUTCOME_SET, _at("2026-09-08", "15:00"), {"outcome": "WHOLLY_REJECTED"}, OFFICER),
            (E.IO_REFERRED, _at("2026-09-15", "10:00"), {}, OFFICER),
            (E.IO_DECIDED, _at("2026-09-25", "16:00"), {}, IO_DESK),
            (E.FINAL_REPLY_SENT, _at("2026-09-28", "11:00"), {}, OFFICER),
        ],
    ),
}

OPEN = (DecisionResult.RUNNING, DecisionResult.BREACHED)
NOT_IN_PLAY = (DecisionResult.NOT_APPLICABLE, DecisionResult.NOT_TRIGGERED)

EVALUATED = {"IO-CB-2026-14-1-a", "IO-CB-2026-14-1-b", "IO-CB-2026-14-9", "RBIOS-2026-10-1-f"}
"""Obligations run on the complaints. The others need facts ``main`` lacks (``issue_type``, #20);
they are still listed in the rule browser."""


def load_obligations() -> list[Obligation]:
    """The rule pack if it is merged, else the DRAFT copies next to this file."""
    pack = ROOT / "rules" / "obligations"
    folder = pack if any(pack.glob("*.yaml")) else HERE / "obligations"
    obs = [
        Obligation.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        for p in sorted(folder.glob("*.yaml"))
        if not p.name.startswith("_")
    ]
    return obs


def chain_status(chain: list[DecisionRecord]) -> ChainStatus:
    """Verify a chain and report the first bad record, if any."""
    prev = GENESIS_HASH
    for i, rec in enumerate(chain):
        if rec.prev_hash != prev or rec.hash is None or rec.hash != rec.compute_hash():
            return ChainStatus(verified=False, length=len(chain), broken_at=i)
        prev = rec.hash
    return ChainStatus(verified=True, length=len(chain))


def summary(
    cid: str, records: list[DecisionRecord], events: list[ComplaintEvent]
) -> ComplaintSummary:
    """One deadline-board row."""
    facts = fold_events(cid, events)
    open_deadlines = sorted(
        (r for r in records if r.deadline is not None and r.result in OPEN),
        key=lambda r: (r.deadline.due_date if r.deadline else None, r.obligation_id),
    )
    nxt = open_deadlines[0] if open_deadlines else None
    return ComplaintSummary(
        complaint_id=cid,
        channel=facts.channel.value if facts.channel else None,
        obligation_ids=[r.obligation_id for r in records if r.result not in NOT_IN_PLAY],
        next_deadline=(
            NextDeadline(
                obligation_id=nxt.obligation_id, due_date=nxt.deadline.due_date, result=nxt.result
            )
            if nxt is not None and nxt.deadline is not None
            else None
        ),
        open_breaches=sum(r.breach is not None for r in records),
    )


def build() -> dict[str, Any]:
    """Evaluate every complaint at every snapshot and assemble the mock responses."""
    pack = load_obligations()
    obligations = [o for o in pack if o.obligation_id in EVALUATED]
    calendar = load_bank_calendar()
    chains: dict[str, list[DecisionRecord]] = {cid: [] for cid in COMPLAINTS}
    snapshots: list[dict[str, Any]] = []
    for as_of in SNAPSHOTS:
        board: list[ComplaintSummary] = []
        details: dict[str, Any] = {}
        positions: dict[str, dict[str, int]] = {}
        for cid, all_events in COMPLAINTS.items():
            seen = [e for e in all_events if e.recorded_at <= as_of]
            if not seen:
                continue
            chain = chains[cid]
            records = []
            for rec in evaluate(seen, obligations, calendar, as_of, profile=PROFILE):
                sealed = rec.seal(chain[-1].hash if chain and chain[-1].hash else GENESIS_HASH)
                chain.append(sealed)
                records.append(sealed)
            if cid == TAMPERED and len(chain) > 1:
                # Simulate an after-the-fact edit of the first record (its hash is left as it was).
                chain[0] = chain[0].model_copy(update={"clause": chain[0].clause + " (edited)"})
            status = chain_status(chain)
            board.append(summary(cid, records, seen))
            details[cid] = ComplaintDetail(
                complaint_id=cid,
                as_of=as_of,
                events=seen,
                facts=fold_events(cid, seen),
                decisions=records,
                chain=status,
            ).model_dump(mode="json")
            base = len(chain) - len(records)
            positions[cid] = {r.obligation_id: base + i for i, r in enumerate(records)}
        snapshots.append(
            {
                "as_of": as_of.isoformat(),
                "board": [b.model_dump(mode="json") for b in board],
                "complaints": details,
                "positions": positions,
            }
        )
    return {
        "obligations": [o.model_dump(mode="json") for o in pack],
        "snapshots": snapshots,
    }


def main() -> None:
    """Write ``fixtures.json``."""
    OUT.write_text(
        json.dumps(build(), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
