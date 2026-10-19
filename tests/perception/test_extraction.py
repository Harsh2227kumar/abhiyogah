"""Fact extraction: grounded facts become FACTS_RECORDED events with LLM provenance."""

from datetime import UTC, date, datetime

import pytest
from pydantic import JsonValue

from abhiyogah.domain.complaint import fold_events
from abhiyogah.domain.enums import AccountType, Channel, FactSource
from abhiyogah.domain.events import EventType
from abhiyogah.perception.adapters import FakeModel
from abhiyogah.perception.errors import LlmOutputError
from abhiyogah.perception.extraction import (
    EXTRACTION_PROMPT_VERSION,
    ExtractionResult,
    FactKind,
    extract_facts,
    parse_amount_paise,
)
from abhiyogah.perception.gateway import LlmRequest
from abhiyogah.perception.pii import PiiMasker
from tests.perception.synthetic import FAKE_ACCOUNT, FAKE_UTR

AS_OF = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
MASKER = PiiMasker()
TEXT = (
    f"On 2026-10-03 I paid Rs 15,000 by UPI to a shop from my savings account {FAKE_ACCOUNT}. "
    f"UTR {FAKE_UTR}. Money debited but merchant did not get it."
)

Spec = tuple[str, str, str]
"""(kind, value, needle): the model reports ``value`` with a span covering ``needle``."""


def _run(text: str, specs: list[Spec] | None) -> ExtractionResult:
    """Extract with a fake model whose spans point at each needle in the masked text."""
    gateway = None
    if specs is not None:
        masked = MASKER.mask(text).text
        facts: list[JsonValue] = []
        for kind, value, needle in specs:
            start = masked.index(needle)
            facts.append(
                {
                    "kind": kind,
                    "value": value,
                    "evidence_start": start,
                    "evidence_end": start + len(needle),
                }
            )
        gateway = FakeModel({"extract_facts": lambda r: {"facts": facts}})
    return extract_facts(
        text,
        complaint_id="C-1",
        document_ref="DOC-1",
        gateway=gateway,
        masker=MASKER,
        as_of=AS_OF,
    )


ALL_FACTS: list[Spec] = [
    ("AMOUNT", "15000", "15,000"),
    ("UTR", FAKE_UTR, FAKE_UTR),
    ("TRANSACTION_DATE", "2026-10-03", "2026-10-03"),
    ("CHANNEL", "UPI_MERCHANT", "UPI to a shop"),
    ("ACCOUNT_TYPE", "OTHER_SAVINGS", "savings account"),
]


def test_every_fact_becomes_an_event_with_provenance() -> None:
    result = _run(TEXT, ALL_FACTS)
    assert not result.dropped
    assert [f.kind for f in result.facts] == list(FactKind)
    assert len(result.events) == 5
    for event in result.events:
        assert event.type is EventType.FACTS_RECORDED
        assert event.complaint_id == "C-1"
        prov = event.provenance
        assert prov.source is FactSource.LLM
        assert prov.model == "fake-deterministic"
        assert prov.prompt_version == EXTRACTION_PROMPT_VERSION
        assert prov.span is not None
        assert prov.span.document_ref == "DOC-1"


def test_events_fold_into_complaint_facts() -> None:
    facts = fold_events("C-1", _run(TEXT, ALL_FACTS).events)
    assert facts.amount_paise is not None
    assert facts.amount_paise.value == 1_500_000
    assert facts.transaction_date_t is not None
    assert facts.transaction_date_t.value == date(2026, 10, 3)
    assert facts.channel is not None
    assert facts.channel.value is Channel.UPI_MERCHANT
    assert facts.account_type is not None
    assert facts.account_type.value is AccountType.OTHER_SAVINGS
    assert facts.amount_paise.provenance.source is FactSource.LLM


def test_span_points_at_the_evidence_in_the_masked_text() -> None:
    result = _run(TEXT, ALL_FACTS)
    masked = MASKER.mask(TEXT).text
    utr = next(f for f in result.facts if f.kind is FactKind.UTR)
    assert masked[utr.span.start : utr.span.end] == FAKE_UTR


def test_model_sees_masked_text_only() -> None:
    seen: list[LlmRequest] = []

    def responder(request: LlmRequest) -> dict[str, JsonValue]:
        seen.append(request)
        return {"facts": []}

    extract_facts(
        TEXT,
        complaint_id="C-1",
        document_ref="DOC-1",
        gateway=FakeModel({"extract_facts": responder}),
        masker=MASKER,
        as_of=AS_OF,
    )
    assert FAKE_ACCOUNT not in seen[0].text


@pytest.mark.parametrize(
    ("spec", "reason"),
    [
        (("AMOUNT", "25000", "15,000"), "amount does not appear in its span"),
        (("AMOUNT", "-5", "15,000"), "amount is not a positive rupee value"),
        (("UTR", "SYNTH99999999999", "UTR"), "UTR does not appear in its span"),
        (("UTR", "short", "UTR"), "UTR is not 10-22 letters or digits"),
        (("TRANSACTION_DATE", "03/10/2026", "2026-10-03"), "date is not YYYY-MM-DD"),
        (("TRANSACTION_DATE", "2026-12-01", "2026-10-03"), "date is in the future"),
        (("CHANNEL", "CARRIER_PIGEON", "UPI to a shop"), "not a known channel"),
        (("ACCOUNT_TYPE", "GOLD", "savings account"), "not a known account type"),
        (("AMOUNT", "<ACCOUNT_NUMBER_1>", "<ACCOUNT_NUMBER_1>"), "value is masked personal data"),
    ],
)
def test_ungrounded_or_malformed_facts_are_dropped(spec: Spec, reason: str) -> None:
    result = _run(TEXT, [spec])
    assert result.events == []
    assert [d.reason for d in result.dropped] == [reason]


def test_span_outside_the_text_is_dropped() -> None:
    gateway = FakeModel(
        {
            "extract_facts": lambda r: {
                "facts": [
                    {"kind": "UTR", "value": FAKE_UTR, "evidence_start": 5, "evidence_end": 9999}
                ]
            }
        }
    )
    result = extract_facts(
        TEXT, complaint_id="C-1", document_ref="D", gateway=gateway, masker=MASKER, as_of=AS_OF
    )
    assert [d.reason for d in result.dropped] == ["span is outside the text"]


def test_conflicting_values_drop_both() -> None:
    text = "Rs 500 was debited, then Rs 700 was debited again."
    result = _run(text, [("AMOUNT", "500", "500"), ("AMOUNT", "700", "700")])
    assert result.events == []
    assert sorted(d.value for d in result.dropped) == ["500", "700"]
    assert {d.reason for d in result.dropped} == {"conflict"}


def test_repeated_same_value_is_kept_once() -> None:
    text = "Rs 500 was debited. I repeat, Rs 500."
    result = _run(text, [("AMOUNT", "500", "500"), ("AMOUNT", "500", "Rs 500.")])
    assert len(result.events) == 1


def test_no_model_goes_to_manual_queue() -> None:
    result = _run(TEXT, None)
    assert result.needs_manual
    assert result.events == []


def test_model_failure_goes_to_manual_queue() -> None:
    def broken(request: LlmRequest) -> dict[str, JsonValue]:
        raise LlmOutputError("bad json")

    result = extract_facts(
        TEXT,
        complaint_id="C-1",
        document_ref="D",
        gateway=FakeModel({"extract_facts": broken}),
        masker=MASKER,
        as_of=AS_OF,
    )
    assert result.needs_manual


def test_schema_violation_goes_to_manual_queue() -> None:
    gateway = FakeModel({"extract_facts": lambda r: {"facts": [{"kind": "LIABILITY"}]}})
    result = extract_facts(
        TEXT, complaint_id="C-1", document_ref="D", gateway=gateway, masker=MASKER, as_of=AS_OF
    )
    assert result.needs_manual


@pytest.mark.parametrize(
    ("value", "paise"),
    [("15000", 1_500_000), ("15,000.50", 1_500_050), ("1.5", 150), ("0", None), ("1e3", None)],
)
def test_parse_amount_paise(value: str, paise: int | None) -> None:
    assert parse_amount_paise(value) == paise
