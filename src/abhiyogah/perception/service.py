"""One entry point for perception, and the rules-only fallback.

``PerceptionService.from_config`` builds the configured gateway. With ``LLM_PROVIDER`` empty (or
``NONE``) there is no gateway, and the service runs rules-only: no model is ever called, nothing is
classified or extracted automatically, and every step becomes a ``ManualTask`` for a person.
Complaints are never dropped in this mode, since an untriaged text counts as a complaint. The same
happens step by step when a configured model fails or answers out of schema.

``ManualTask`` is perception's queue entry. ``workflow.review.ReviewTask`` has no kind for manual
perception yet (see Requests in ``tasks/06-perception.md``), so the two stay separate. "Not a
complaint" findings still open a ``ReviewTask`` as the workflow requires.
"""

from collections.abc import Mapping
from enum import StrEnum

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.events import ComplaintEvent
from abhiyogah.perception.adapters import (
    AnthropicClient,
    BedrockClient,
    Responder,
    build_gateway,
)
from abhiyogah.perception.extraction import ExtractionResult, extract_facts
from abhiyogah.perception.gateway import GatewayConfig, LlmGateway
from abhiyogah.perception.pii import PiiMasker, default_masker
from abhiyogah.perception.reply_qa import ReplyQaResult, check_reply
from abhiyogah.perception.triage import TriageGate, TriageResult, triage
from abhiyogah.registry.schema import Obligation
from abhiyogah.workflow.review import ReviewTask

__all__ = ["ManualStep", "ManualTask", "PerceptionOutcome", "PerceptionService"]


class ManualStep(StrEnum):
    """Which perception step a person must do by hand."""

    TRIAGE = "TRIAGE"
    EXTRACTION = "EXTRACTION"
    REPLY_QA = "REPLY_QA"


class ManualTask(BaseModel):
    """A perception step left to a person (no model, or the model failed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    complaint_id: str
    step: ManualStep
    document_ref: str
    reason: str
    created_at: AwareDatetime


class PerceptionOutcome(BaseModel):
    """Everything perception produced for one complaint text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    triage: TriageResult
    extraction: ExtractionResult
    events: list[ComplaintEvent]
    """``FACTS_RECORDED`` events with LLM provenance, ready to append."""
    review_tasks: list[ReviewTask]
    manual_tasks: list[ManualTask]


def _manual(
    step: ManualStep, complaint_id: str, document_ref: str, reason: str, as_of: AwareDatetime
) -> ManualTask:
    return ManualTask(
        task_id=f"MT-{step.value}-{complaint_id}-{document_ref}",
        complaint_id=complaint_id,
        step=step,
        document_ref=document_ref,
        reason=reason,
        created_at=as_of,
    )


class PerceptionService:
    """Triage, extraction and reply QA behind one object; rules-only when no model is set."""

    def __init__(
        self,
        gateway: LlmGateway | None,
        masker: PiiMasker | None = None,
        gate: TriageGate | None = None,
    ) -> None:
        """Use ``gateway`` (``None`` = rules-only) with ``masker`` and triage ``gate``."""
        self._gateway = gateway
        self._masker = masker or default_masker()
        self._gate = gate or TriageGate()

    @classmethod
    def from_config(
        cls,
        config: GatewayConfig,
        *,
        masker: PiiMasker | None = None,
        gate: TriageGate | None = None,
        fake_responders: Mapping[str, Responder] | None = None,
        anthropic_client: AnthropicClient | None = None,
        bedrock_client: BedrockClient | None = None,
        http_client: httpx.Client | None = None,
    ) -> "PerceptionService":
        """Build the configured gateway (checks the region) and wrap it."""
        gateway = build_gateway(
            config,
            fake_responders=fake_responders,
            anthropic_client=anthropic_client,
            bedrock_client=bedrock_client,
            http_client=http_client,
        )
        return cls(gateway, masker, gate)

    @property
    def rules_only(self) -> bool:
        """True when no model is configured: every step goes to the manual queue."""
        return self._gateway is None

    def perceive(
        self, text: str, *, complaint_id: str, document_ref: str, as_of: AwareDatetime
    ) -> PerceptionOutcome:
        """Triage a customer text and extract its facts."""
        t = triage(
            text,
            complaint_id=complaint_id,
            document_ref=document_ref,
            gateway=self._gateway,
            masker=self._masker,
            as_of=as_of,
            gate=self._gate,
        )
        x = extract_facts(
            text,
            complaint_id=complaint_id,
            document_ref=document_ref,
            gateway=self._gateway,
            masker=self._masker,
            as_of=as_of,
        )
        manual = []
        if t.needs_manual:
            manual.append(_manual(ManualStep.TRIAGE, complaint_id, document_ref, t.reason, as_of))
        if x.needs_manual:
            manual.append(
                _manual(ManualStep.EXTRACTION, complaint_id, document_ref, x.reason, as_of)
            )
        return PerceptionOutcome(
            triage=t,
            extraction=x,
            events=list(x.events),
            review_tasks=[t.review_task] if t.review_task is not None else [],
            manual_tasks=manual,
        )

    def check_reply(
        self,
        draft: str,
        *,
        obligation: Obligation,
        facts: ComplaintFacts,
        document_ref: str,
        as_of: AwareDatetime,
    ) -> tuple[ReplyQaResult, ManualTask | None]:
        """Run the A18 reply QA gate; a draft the model could not check gets a manual task."""
        result = check_reply(
            draft,
            obligation=obligation,
            facts=facts,
            document_ref=document_ref,
            gateway=self._gateway,
            masker=self._masker,
            as_of=as_of,
        )
        task = None
        if result.needs_manual:
            task = _manual(
                ManualStep.REPLY_QA, facts.complaint_id, document_ref, result.reason, as_of
            )
        return result, task
