"""Reply QA gate (report row A18, IO Directions 2026 cl. 14(11)-(12)).

Before a reply to a partially resolved or wholly rejected complaint is sent, the gate checks that
the draft carries every element the rule pack requires. No element is hard-coded here:

- the element codes come from the A18 obligation's parameters (``required_elements``, plus
  ``required_elements_if_io_upheld`` when the IO upheld the decision), at the version in force on
  the draft date;
- whether the gate applies at all comes from the obligation's trigger condition, evaluated on the
  complaint's facts. If a fact it needs is unknown, the gate applies (it fails closed);
- if ``io_upheld`` is unknown, the IO elements are required too.

The model only perceives: it reports which element codes the masked draft contains, each with the
span where it appears, plus any wording it thinks is risky. Deterministic code decides. A draft
with a missing element, or one the model could not read, is blocked. Risk flags are advice for the
drafter and never block; a flag that overlaps a required element's span is discarded, so the
mandatory Ombudsman wording is never reported as a risk.

``reply_elements`` on the result is what the bank puts in the ``FINAL_REPLY_SENT`` payload when the
reply is actually sent (CLAUDE.md hard rule 6); this module creates no events.
"""

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.enums import FactSource
from abhiyogah.domain.events import Provenance, TextSpan
from abhiyogah.domain.tz import ist_date
from abhiyogah.evaluator.conditions import evaluate_condition
from abhiyogah.evaluator.parameters import parameter_at
from abhiyogah.perception.errors import LlmCallError, LlmOutputError, PerceptionError
from abhiyogah.perception.gateway import LlmGateway, LlmRequest
from abhiyogah.perception.pii import PiiMasker
from abhiyogah.registry.schema import Obligation

__all__ = [
    "IO_UPHELD_PARAMETER",
    "REPLY_QA_PROMPT_ID",
    "REPLY_QA_PROMPT_VERSION",
    "REQUIRED_PARAMETER",
    "ElementFound",
    "ReplyQaAnswer",
    "ReplyQaResult",
    "RiskFlag",
    "check_reply",
    "required_elements",
]

REPLY_QA_PROMPT_ID = "reply_qa"
REPLY_QA_PROMPT_VERSION = "reply-qa-v1"
REQUIRED_PARAMETER = "required_elements"
IO_UPHELD_PARAMETER = "required_elements_if_io_upheld"

_GUIDANCE: dict[str, str] = {
    "IO_REVIEW_STATEMENT": "says the bank's Internal Ombudsman reviewed the complaint",
    "RBIOS_OPTION_ADVICE": "tells the complainant they may complain to the RBI Ombudsman",
    "RBIOS_COMPLETE_COMPLAINT_DETAILS": "advises giving the Ombudsman complete complaint details",
    "CMS_PORTAL_LINK": "gives the RBI complaint portal address",
    "CRPC_POSTAL_ADDRESS": "gives the postal address of RBI's complaint processing centre",
    "CRPC_EMAIL_ADDRESS": "gives the email address of RBI's complaint processing centre",
}
"""Hints that help the model recognise each code. They describe content; they are not wording to
copy, and a code without a hint is still checked."""


class ElementFound(BaseModel):
    """An element the model found in the draft, and where."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(ge=0)


class RiskFlag(BaseModel):
    """Wording the model thinks is risky (e.g. a promise or a discouragement to escalate)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note: str
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(ge=0)


class ReplyQaAnswer(BaseModel):
    """The model's answer. Its JSON schema is what the model must follow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    elements: list[ElementFound]
    risks: list[RiskFlag]


class ReplyQaResult(BaseModel):
    """The gate's verdict on one draft reply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    complaint_id: str
    applies: bool
    """Whether A18 covers this reply (trigger condition true, or a needed fact unknown)."""
    required: list[str]
    present: list[str]
    missing: list[str]
    can_send: bool
    element_spans: dict[str, TextSpan]
    risks: list[RiskFlag]
    provenance: Provenance | None
    needs_manual: bool
    reason: str

    @property
    def reply_elements(self) -> list[str]:
        """Element codes for the ``FINAL_REPLY_SENT`` payload once the reply is sent."""
        return list(self.present)


def _codes(obligation: Obligation, name: str, on: date) -> list[str]:
    if name not in obligation.parameters:
        return []
    found = parameter_at(obligation, name, on)
    if found is None:
        return []
    value = found[1].value
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise PerceptionError(f"{obligation.obligation_id}: {name} is not a list of codes")
    return [str(v) for v in value]


def required_elements(obligation: Obligation, facts: ComplaintFacts, on: date) -> list[str]:
    """Element codes the reply must carry, from the obligation's parameters in force on ``on``."""
    codes = _codes(obligation, REQUIRED_PARAMETER, on)
    if facts.io_upheld is None or facts.io_upheld.value:
        codes += [c for c in _codes(obligation, IO_UPHELD_PARAMETER, on) if c not in codes]
    return codes


_SYSTEM = """You check a draft reply from an Indian bank to a customer complaint. The text is \
masked: values like <EMAIL_1> replace personal data and count as present values.

elements: for each code below that the draft clearly contains, give the code and the character \
offsets of the words that contain it. Leave a code out if it is absent or only partly there.
{codes}
risks: wording that could mislead or harm the customer, such as promises the bank may not keep, \
admissions of fault, or discouraging escalation. Advising the customer of their right to approach \
the RBI Ombudsman, and the RBI addresses, are required content and are never a risk."""


def _request(masked: str, codes: list[str]) -> LlmRequest:
    lines = "\n".join(f"- {c}: {_GUIDANCE.get(c, c.replace('_', ' ').lower())}" for c in codes)
    return LlmRequest(
        prompt_id=REPLY_QA_PROMPT_ID,
        prompt_version=REPLY_QA_PROMPT_VERSION,
        system=_SYSTEM.format(codes=lines),
        text=masked,
        output_schema=ReplyQaAnswer.model_json_schema(),
    )


def check_reply(
    draft: str,
    *,
    obligation: Obligation,
    facts: ComplaintFacts,
    document_ref: str,
    gateway: LlmGateway | None,
    masker: PiiMasker,
    as_of: AwareDatetime,
) -> ReplyQaResult:
    """Check one draft reply against the A18 obligation. Blocks sending if anything is missing."""
    trigger = evaluate_condition(obligation.trigger.condition, facts)
    applies = trigger.result or bool(trigger.missing)
    if not applies:
        return ReplyQaResult(
            complaint_id=facts.complaint_id,
            applies=applies,
            required=[],
            present=[],
            missing=[],
            can_send=True,
            element_spans={},
            risks=[],
            provenance=None,
            needs_manual=False,
            reason=f"{obligation.obligation_id} does not apply to this reply.",
        )
    required = required_elements(obligation, facts, ist_date(as_of))

    def manual(reason: str) -> ReplyQaResult:
        return ReplyQaResult(
            complaint_id=facts.complaint_id,
            applies=applies,
            required=required,
            present=[],
            missing=list(required),
            can_send=False,
            element_spans={},
            risks=[],
            provenance=None,
            needs_manual=True,
            reason=reason,
        )

    if gateway is None:
        return manual("No model configured; a person checks the reply before it is sent.")
    masked = masker.mask(draft).text
    try:
        response = gateway.complete(_request(masked, required))
        answer = ReplyQaAnswer.model_validate(response.output)
    except (LlmCallError, LlmOutputError, ValidationError) as exc:
        return manual(f"Model could not check the reply ({type(exc).__name__}); a person must.")

    spans: dict[str, TextSpan] = {}
    for el in answer.elements:
        grounded = el.evidence_start < el.evidence_end <= len(masked)
        if el.code in required and grounded and el.code not in spans:
            spans[el.code] = TextSpan(
                document_ref=document_ref, start=el.evidence_start, end=el.evidence_end
            )
    present = [c for c in required if c in spans]
    missing = sorted(c for c in required if c not in spans)

    def overlaps_required(risk: RiskFlag) -> bool:
        return any(
            risk.evidence_start < s.end and s.start < risk.evidence_end for s in spans.values()
        )

    risks = [r for r in answer.risks if not overlaps_required(r)]
    reason = (
        "Every required element is present."
        if not missing
        else "Blocked: missing " + ", ".join(missing) + "."
    )
    return ReplyQaResult(
        complaint_id=facts.complaint_id,
        applies=applies,
        required=required,
        present=present,
        missing=missing,
        can_send=not missing,
        element_spans=spans,
        risks=risks,
        provenance=Provenance(
            source=FactSource.LLM, model=response.model, prompt_version=response.prompt_version
        ),
        needs_manual=False,
        reason=reason,
    )
