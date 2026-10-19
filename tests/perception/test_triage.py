"""Triage: the high-recall gate, review tasks for every "not a complaint", provenance, fallbacks."""

from datetime import UTC, datetime

import pytest
from pydantic import JsonValue

from abhiyogah.domain.enums import FactSource, IssueType
from abhiyogah.perception.adapters import FakeModel
from abhiyogah.perception.errors import LlmCallError
from abhiyogah.perception.gateway import LlmGateway, LlmRequest, LlmResponse
from abhiyogah.perception.pii import PiiMasker
from abhiyogah.perception.triage import (
    TRIAGE_PROMPT_VERSION,
    Language,
    TriageGate,
    TriageLabel,
    TriageResult,
    detect_language,
    has_deficiency_cue,
    triage,
)
from abhiyogah.workflow.review import FindingKind, ReviewKind
from tests.perception.synthetic import FAKE_ACCOUNT

AS_OF = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
MASKER = PiiMasker()


def _answer(**overrides: JsonValue) -> dict[str, JsonValue]:
    answer: dict[str, JsonValue] = {
        "label": "COMPLAINT",
        "confidence": 0.95,
        "issue_type": "FAILED_TRANSACTION",
        "category": None,
        "language": "ENGLISH",
        "evidence_start": 0,
        "evidence_end": 5,
    }
    answer.update(overrides)
    return answer


def _fake(**overrides: JsonValue) -> FakeModel:
    return FakeModel({"triage": lambda r: _answer(**overrides)})


def _run(text: str, fake: LlmGateway | None, gate: TriageGate | None = None) -> TriageResult:
    return triage(
        text,
        complaint_id="C-1",
        document_ref="DOC-1",
        gateway=fake,
        masker=MASKER,
        as_of=AS_OF,
        gate=gate,
    )


def test_complaint_has_llm_provenance_and_no_review() -> None:
    result = _run("Money debited but not credited to the payee.", _fake())
    assert result.is_complaint
    assert result.issue_type is IssueType.FAILED_TRANSACTION
    assert result.review_task is None
    assert result.finding is not None
    assert result.finding.kind is FindingKind.IS_COMPLAINT
    prov = result.provenance
    assert prov is not None
    assert prov.source is FactSource.LLM
    assert prov.model == "fake-deterministic"
    assert prov.prompt_version == TRIAGE_PROMPT_VERSION
    assert prov.span is not None
    assert (prov.span.document_ref, prov.span.start, prov.span.end) == ("DOC-1", 0, 5)


def test_confident_query_without_cue_is_not_a_complaint_and_opens_review() -> None:
    result = _run("What are your branch timings on Saturday?", _fake(label="QUERY"))
    assert not result.is_complaint
    assert result.finding is not None
    assert result.finding.kind is FindingKind.NOT_A_COMPLAINT
    task = result.review_task
    assert task is not None
    assert task.kind is ReviewKind.NOT_A_COMPLAINT
    assert task.complaint_id == "C-1"
    assert task.provenance == result.provenance


def test_query_with_deficiency_cue_stays_a_complaint() -> None:
    result = _run("Rs 500 deducted twice, what is the charge for?", _fake(label="QUERY"))
    assert result.is_complaint
    assert result.review_task is None
    assert "deficiency cue" in result.reason


def test_unsure_request_stays_a_complaint() -> None:
    result = _run("Please send me a new cheque book.", _fake(label="REQUEST", confidence=0.6))
    assert result.is_complaint
    assert result.model_label is TriageLabel.REQUEST
    assert "below the confidence threshold" in result.reason


def test_threshold_is_configurable() -> None:
    gate = TriageGate(not_complaint_min_confidence=0.5)
    result = _run("Please send me a new cheque book.", _fake(label="REQUEST", confidence=0.6), gate)
    assert not result.is_complaint
    assert result.review_task is not None


def test_model_sees_only_masked_text() -> None:
    fake = _fake()
    _run(f"Debited from account {FAKE_ACCOUNT} but not credited", fake)
    assert FAKE_ACCOUNT not in fake.calls[0].text
    assert "<ACCOUNT_NUMBER_1>" in fake.calls[0].text


def test_categories_are_configuration() -> None:
    gate = TriageGate(categories=("ATM_DEBIT_CARD", "MOBILE_ELECTRONIC_BANKING"))
    fake = _fake(category="ATM_DEBIT_CARD")
    result = _run("ATM debited cash not dispensed", fake, gate)
    assert result.category == "ATM_DEBIT_CARD"
    assert "ATM_DEBIT_CARD" in fake.calls[0].system
    schema = fake.calls[0].output_schema
    assert isinstance(schema, dict)
    props = schema["properties"]
    assert isinstance(props, dict)
    assert props["category"] == {"enum": ["ATM_DEBIT_CARD", "MOBILE_ELECTRONIC_BANKING", None]}


def test_category_outside_the_list_is_dropped() -> None:
    result = _run("ATM debited cash not dispensed", _fake(category="MADE_UP"))
    assert result.category is None


def test_out_of_range_span_is_dropped() -> None:
    result = _run("short debited", _fake(evidence_start=2, evidence_end=999))
    assert result.provenance is not None
    assert result.provenance.span is None


def test_no_model_goes_to_manual_queue_as_complaint() -> None:
    result = _run("Paise kat gaye par mile nahi", None)
    assert result.is_complaint
    assert result.needs_manual
    assert result.provenance is None
    assert result.language is Language.HINGLISH


def test_model_failure_goes_to_manual_queue() -> None:
    def broken(request: LlmRequest) -> dict[str, JsonValue]:
        raise LlmCallError("timeout")

    result = _run("anything", FakeModel({"triage": broken}))
    assert result.needs_manual
    assert result.is_complaint


def test_schema_violation_goes_to_manual_queue() -> None:
    result = _run("anything", _fake(label="MAYBE"))
    assert result.needs_manual
    assert result.is_complaint


class _ServedModel:
    model = "served"

    def complete(self, request: LlmRequest) -> LlmResponse:
        return LlmResponse(
            model="served-v2", prompt_id=request.prompt_id, prompt_version="x", output=_answer()
        )


def test_provenance_records_the_model_that_answered() -> None:
    result = _run("debited", _ServedModel())
    assert result.provenance is not None
    assert result.provenance.model == "served-v2"


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("My UPI payment failed", Language.ENGLISH),
        ("मेरे खाते से पैसे कट गए", Language.HINDI),
        ("Mera paisa wapas nahi aaya hai", Language.HINGLISH),
        ("12345", Language.OTHER),
    ],
)
def test_detect_language(text: str, language: Language) -> None:
    assert detect_language(text) is language


@pytest.mark.parametrize(
    "text",
    ["amount not credited", "मेरी शिकायत", "paise kat gaye", "unauthorised txn", "I want a refund"],
)
def test_deficiency_cues(text: str) -> None:
    assert has_deficiency_cue(text)


def test_plain_query_has_no_cue() -> None:
    assert not has_deficiency_cue("What is the interest rate on fixed deposits?")
