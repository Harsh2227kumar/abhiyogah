"""PerceptionService: rules-only fallback sends every step to the manual queue."""

from datetime import UTC, datetime

from pydantic import JsonValue

from abhiyogah.perception.adapters import FakeModel
from abhiyogah.perception.errors import LlmCallError
from abhiyogah.perception.gateway import GatewayConfig, LlmRequest, Provider
from abhiyogah.perception.service import ManualStep, PerceptionService
from abhiyogah.workflow.review import ReviewKind
from tests.perception.synthetic import FAKE_UTR
from tests.perception.test_reply_qa import ALL, _draft, _facts, _model, _obligation

AS_OF = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
TEXT = f"Rs 2,000 debited by UPI on 2026-10-18 but not credited. UTR {FAKE_UTR}."


def _query_answer(request: LlmRequest) -> dict[str, JsonValue]:
    return {
        "label": "QUERY",
        "confidence": 0.99,
        "issue_type": "OTHER",
        "category": None,
        "language": "ENGLISH",
        "evidence_start": 0,
        "evidence_end": 4,
    }


def _utr_answer(request: LlmRequest) -> dict[str, JsonValue]:
    start = request.text.index(FAKE_UTR)
    return {
        "facts": [
            {
                "kind": "UTR",
                "value": FAKE_UTR,
                "evidence_start": start,
                "evidence_end": start + len(FAKE_UTR),
            }
        ]
    }


def test_rules_only_from_empty_config() -> None:
    service = PerceptionService.from_config(GatewayConfig.from_env({}))
    assert service.rules_only
    outcome = service.perceive(TEXT, complaint_id="C-1", document_ref="DOC-1", as_of=AS_OF)
    assert outcome.triage.is_complaint
    assert outcome.triage.needs_manual
    assert outcome.events == []
    assert outcome.review_tasks == []
    assert [t.step for t in outcome.manual_tasks] == [ManualStep.TRIAGE, ManualStep.EXTRACTION]
    assert all(t.complaint_id == "C-1" and t.created_at == AS_OF for t in outcome.manual_tasks)


def test_rules_only_reply_check_blocks_with_a_manual_task() -> None:
    service = PerceptionService(None)
    result, task = service.check_reply(
        _draft(ALL), obligation=_obligation(), facts=_facts(), document_ref="R-1", as_of=AS_OF
    )
    assert not result.can_send
    assert task is not None
    assert task.step is ManualStep.REPLY_QA


def test_configured_model_produces_events_and_review_tasks() -> None:
    service = PerceptionService.from_config(
        GatewayConfig(provider=Provider.FAKE),
        fake_responders={"triage": _query_answer, "extract_facts": _utr_answer},
    )
    assert not service.rules_only
    outcome = service.perceive(
        "Please tell me the FD rate. Ref UTR " + FAKE_UTR,
        complaint_id="C-2",
        document_ref="DOC-2",
        as_of=AS_OF,
    )
    assert not outcome.triage.is_complaint
    assert [t.kind for t in outcome.review_tasks] == [ReviewKind.NOT_A_COMPLAINT]
    assert len(outcome.events) == 1
    assert outcome.events[0].payload == {"utr": FAKE_UTR}
    assert outcome.manual_tasks == []


def test_failing_model_falls_back_to_manual_per_step() -> None:
    def broken(request: LlmRequest) -> dict[str, JsonValue]:
        raise LlmCallError("down")

    service = PerceptionService(FakeModel({"triage": broken, "extract_facts": _utr_answer}))
    outcome = service.perceive(TEXT, complaint_id="C-3", document_ref="DOC-3", as_of=AS_OF)
    assert outcome.triage.is_complaint
    assert [t.step for t in outcome.manual_tasks] == [ManualStep.TRIAGE]
    assert len(outcome.events) == 1


def test_reply_check_with_model_has_no_manual_task() -> None:
    service = PerceptionService(_model())
    result, task = service.check_reply(
        _draft(ALL), obligation=_obligation(), facts=_facts(), document_ref="R-1", as_of=AS_OF
    )
    assert result.can_send
    assert task is None
