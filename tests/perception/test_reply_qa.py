"""Reply QA gate (A18): rule-pack elements, blocks on any gap, never flags the Ombudsman text."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import JsonValue

from abhiyogah.domain.complaint import ComplaintFacts, fold_events
from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance
from abhiyogah.perception.adapters import FakeModel
from abhiyogah.perception.errors import LlmCallError
from abhiyogah.perception.gateway import LlmRequest
from abhiyogah.perception.pii import PiiMasker
from abhiyogah.perception.reply_qa import (
    REPLY_QA_PROMPT_VERSION,
    ReplyQaResult,
    check_reply,
    required_elements,
)
from abhiyogah.registry.schema import Obligation
from tests.perception.synthetic import FAKE_ACCOUNT

FIXTURE = Path(__file__).parent / "fixtures" / "IO-CB-2026-14-11-12.yaml"
RULE_FILE = Path("rules/obligations/IO-CB-2026-14-11-12.yaml")
AS_OF = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)
MASKER = PiiMasker()
HUMAN = Provenance(source=FactSource.HUMAN, actor="officer-1")

# Synthetic draft. Each sentence is tagged with the element code it carries, for the fake model.
SENTENCES: list[tuple[str, str]] = [
    ("IO_REVIEW_STATEMENT", "Our Internal Ombudsman has reviewed your complaint."),
    ("RBIOS_OPTION_ADVICE", "You may complain to the RBI Ombudsman under RB-IOS 2026."),
    ("RBIOS_COMPLETE_COMPLAINT_DETAILS", "Please give complete details of your complaint."),
    ("CMS_PORTAL_LINK", "File online at the RBI complaint portal (synthetic link)."),
    ("CRPC_POSTAL_ADDRESS", "Or write to the CRPC at [synthetic postal address]."),
    ("CRPC_EMAIL_ADDRESS", "Or email the CRPC at [synthetic email address]."),
]


def _obligation(path: Path = FIXTURE) -> Obligation:
    return Obligation.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _facts(
    outcome: str | None = "WHOLLY_REJECTED", io_upheld: bool | None = True
) -> ComplaintFacts:
    t = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
    events = []
    if outcome is not None:
        events.append(
            ComplaintEvent(
                event_id="E1",
                complaint_id="C-1",
                type=EventType.OUTCOME_SET,
                occurred_at=t,
                recorded_at=t,
                payload={"outcome": outcome},
                provenance=HUMAN,
            )
        )
    if io_upheld is not None:
        events.append(
            ComplaintEvent(
                event_id="E2",
                complaint_id="C-1",
                type=EventType.IO_DECIDED,
                occurred_at=t,
                recorded_at=t,
                payload={"io_upheld": io_upheld},
                provenance=HUMAN,
            )
        )
    return fold_events("C-1", events)


def _draft(codes: list[str]) -> str:
    body = " ".join(s for c, s in SENTENCES if c in codes)
    return f"Dear customer, regarding account {FAKE_ACCOUNT}, we cannot refund the charge. {body}"


def _model(risks: list[tuple[str, str]] | None = None) -> FakeModel:
    """Finds each tagged sentence present in the masked draft; flags any ``(note, needle)``."""

    def respond(request: LlmRequest) -> dict[str, JsonValue]:
        text = request.text
        elements: list[JsonValue] = []
        for code, sentence in SENTENCES:
            if sentence in text:
                start = text.index(sentence)
                elements.append(
                    {"code": code, "evidence_start": start, "evidence_end": start + len(sentence)}
                )
        flagged: list[JsonValue] = []
        for note, needle in risks or []:
            start = text.index(needle)
            flagged.append(
                {"note": note, "evidence_start": start, "evidence_end": start + len(needle)}
            )
        return {"elements": elements, "risks": flagged}

    return FakeModel({"reply_qa": respond})


def _check(draft: str, facts: ComplaintFacts, gateway: FakeModel | None = None) -> ReplyQaResult:
    return check_reply(
        draft,
        obligation=_obligation(),
        facts=facts,
        document_ref="DRAFT-1",
        gateway=_model() if gateway is None else gateway,
        masker=MASKER,
        as_of=AS_OF,
    )


ALL = [c for c, _ in SENTENCES]


def test_required_elements_come_from_the_obligation() -> None:
    ob = _obligation()
    on = date(2026, 8, 27)
    upheld = required_elements(ob, _facts(io_upheld=True), on)
    assert upheld == [
        "RBIOS_OPTION_ADVICE",
        "RBIOS_COMPLETE_COMPLAINT_DETAILS",
        "CMS_PORTAL_LINK",
        "CRPC_POSTAL_ADDRESS",
        "CRPC_EMAIL_ADDRESS",
        "IO_REVIEW_STATEMENT",
    ]
    assert "IO_REVIEW_STATEMENT" not in required_elements(ob, _facts(io_upheld=False), on)
    assert "IO_REVIEW_STATEMENT" in required_elements(ob, _facts(io_upheld=None), on)
    assert required_elements(ob, _facts(), date(2025, 1, 1)) == []


def test_complete_reply_can_be_sent() -> None:
    result = _check(_draft(ALL), _facts())
    assert result.applies
    assert result.can_send
    assert result.missing == []
    assert sorted(result.reply_elements) == sorted(ALL)
    assert result.provenance is not None
    assert result.provenance.source is FactSource.LLM
    assert result.provenance.prompt_version == REPLY_QA_PROMPT_VERSION
    assert set(result.element_spans) == set(ALL)


def test_missing_elements_block_sending() -> None:
    draft = _draft([c for c in ALL if c not in {"IO_REVIEW_STATEMENT", "CRPC_EMAIL_ADDRESS"}])
    result = _check(draft, _facts())
    assert not result.can_send
    assert result.missing == ["CRPC_EMAIL_ADDRESS", "IO_REVIEW_STATEMENT"]
    assert "Blocked" in result.reason


def test_io_statement_not_required_when_io_did_not_uphold() -> None:
    draft = _draft([c for c in ALL if c != "IO_REVIEW_STATEMENT"])
    assert _check(draft, _facts(io_upheld=False)).can_send


def test_fully_resolved_reply_is_outside_a18() -> None:
    result = _check("We have refunded the amount.", _facts(outcome="FULLY_RESOLVED"))
    assert not result.applies
    assert result.can_send
    assert result.required == []


def test_unknown_outcome_fails_closed() -> None:
    result = _check("We have refunded the amount.", _facts(outcome=None))
    assert result.applies
    assert not result.can_send


def test_ombudsman_wording_is_never_flagged_as_a_risk() -> None:
    ombudsman = dict(SENTENCES)["RBIOS_OPTION_ADVICE"]
    promise = "we cannot refund the charge"
    gateway = _model(risks=[("mentions the regulator", ombudsman), ("firm refusal", promise)])
    result = _check(_draft(ALL), _facts(), gateway)
    assert [r.note for r in result.risks] == ["firm refusal"]
    assert result.can_send  # risks never block


def test_model_sees_masked_draft_and_the_rule_pack_codes() -> None:
    gateway = _model()
    _check(_draft(ALL), _facts(), gateway)
    request = gateway.calls[0]
    assert FAKE_ACCOUNT not in request.text
    for code in ALL:
        assert code in request.system


def test_element_with_bad_span_does_not_count() -> None:
    gateway = FakeModel(
        {
            "reply_qa": lambda r: {
                "elements": [{"code": c, "evidence_start": 0, "evidence_end": 99999} for c in ALL],
                "risks": [],
            }
        }
    )
    result = _check(_draft(ALL), _facts(), gateway)
    assert not result.can_send
    assert result.missing == sorted(ALL)


def test_unknown_codes_from_the_model_are_ignored() -> None:
    gateway = FakeModel(
        {
            "reply_qa": lambda r: {
                "elements": [{"code": "MADE_UP", "evidence_start": 0, "evidence_end": 4}],
                "risks": [],
            }
        }
    )
    assert _check(_draft(ALL), _facts(), gateway).present == []


def test_no_model_blocks_for_manual_check() -> None:
    result = check_reply(
        _draft(ALL),
        obligation=_obligation(),
        facts=_facts(),
        document_ref="D",
        gateway=None,
        masker=MASKER,
        as_of=AS_OF,
    )
    assert result.needs_manual
    assert not result.can_send


def test_model_failure_blocks_for_manual_check() -> None:
    def broken(request: LlmRequest) -> dict[str, JsonValue]:
        raise LlmCallError("down")

    result = _check(_draft(ALL), _facts(), FakeModel({"reply_qa": broken}))
    assert result.needs_manual
    assert not result.can_send


@pytest.mark.parametrize("path", [p for p in [RULE_FILE] if p.exists()] or [FIXTURE])
def test_rule_pack_file_agrees_with_the_fixture(path: Path) -> None:
    on = date(2026, 8, 27)
    assert required_elements(_obligation(path), _facts(), on) == required_elements(
        _obligation(), _facts(), on
    )
