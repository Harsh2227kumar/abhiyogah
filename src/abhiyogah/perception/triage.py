"""Triage: complaint vs query, issue type, category and language, with a high-recall gate.

The model answers a schema-constrained question about the masked text. Deterministic code then
applies the gate (IO Directions 2026 cl. 4(1)(c): a complaint is a representation alleging a
deficiency in service, "with or without seeking relief"; report line 139 and gap 29):

- The result is "not a complaint" only when the model says so with at least
  ``TriageGate.not_complaint_min_confidence`` and no deficiency cue appears in the text.
  Anything else stays a complaint: a missed complaint is the failure RBI calls "a gross regulatory
  violation", so recall wins over precision.
- Every "not a complaint" result becomes a ``NOT_A_COMPLAINT`` finding and opens a human review task
  (``workflow.review``). Nothing drops out of the regulated flow on the model's word alone.
- If the model fails or its answer does not fit the schema, the text is treated as a complaint and
  goes to the manual queue.

The RBI category list is not in the research report, so ``categories`` is configuration. With an
empty list the model is not asked for one and ``category`` stays ``None``.
"""

import re
from enum import StrEnum
from typing import Any, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, ValidationError

from abhiyogah.domain.enums import FactSource, IssueType
from abhiyogah.domain.events import Provenance, TextSpan
from abhiyogah.perception.errors import LlmCallError, LlmOutputError
from abhiyogah.perception.gateway import LlmGateway, LlmRequest
from abhiyogah.perception.pii import PiiMasker
from abhiyogah.workflow.review import (
    FindingKind,
    PerceptionFinding,
    ReviewTask,
    review_task_for_finding,
)

__all__ = [
    "TRIAGE_PROMPT_ID",
    "TRIAGE_PROMPT_VERSION",
    "Language",
    "TriageAnswer",
    "TriageGate",
    "TriageLabel",
    "TriageResult",
    "detect_language",
    "has_deficiency_cue",
    "triage",
]

TRIAGE_PROMPT_ID = "triage"
TRIAGE_PROMPT_VERSION = "triage-v1"


class Language(StrEnum):
    """Language of the complaint text."""

    ENGLISH = "ENGLISH"
    HINDI = "HINDI"
    HINGLISH = "HINGLISH"
    """Hindi written in Latin script, often mixed with English."""
    OTHER = "OTHER"


class TriageLabel(StrEnum):
    """What the text is. Only ``COMPLAINT`` stays in the regulated flow without review."""

    COMPLAINT = "COMPLAINT"
    QUERY = "QUERY"
    REQUEST = "REQUEST"


class TriageAnswer(BaseModel):
    """The model's answer. Its JSON schema is what the model must follow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: TriageLabel
    confidence: float = Field(ge=0, le=1, description="Confidence in the label, 0 to 1.")
    issue_type: IssueType
    category: str | None = Field(description="One of the given categories, or null.")
    language: Language
    evidence_start: int = Field(ge=0, description="Start of the text that supports the label.")
    evidence_end: int = Field(ge=0, description="End (exclusive) of that text.")


class TriageGate(BaseModel):
    """Gate settings. The threshold is an operating choice, not a regulatory value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    not_complaint_min_confidence: float = Field(default=0.9, ge=0, le=1)
    categories: tuple[str, ...] = ()


class TriageResult(BaseModel):
    """Triage outcome for one text, with provenance and any review task it opened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    complaint_id: str
    is_complaint: bool
    """The gated result: ``False`` only for a confident model answer with no deficiency cue."""
    model_label: TriageLabel | None
    confidence: float | None
    issue_type: IssueType | None
    category: str | None
    language: Language
    provenance: Provenance | None
    """``None`` when no model answer was used (manual queue)."""
    finding: PerceptionFinding | None
    review_task: ReviewTask | None
    needs_manual: bool
    """True when the model could not be used; a person must triage the text."""
    reason: str


_SYSTEM = """You triage customer messages sent to an Indian bank. The text is masked: values like \
<ACCOUNT_NUMBER_1> replace personal data.

label: COMPLAINT if the customer alleges any deficiency in service by the bank (a failed or \
unauthorised transaction, money debited but not credited, wrong charges, delay, rude or unfair \
treatment, fraud), with or without asking for relief. QUERY if they only ask for information. \
REQUEST if they only ask for a service (new card, statement, address change) and allege no \
deficiency. When unsure, answer COMPLAINT.
confidence: how sure you are of the label, from 0 to 1.
issue_type: FAILED_TRANSACTION, UNAUTHORISED_TRANSACTION, FRAUDULENT_TRANSACTION or OTHER.
category: {category_instruction}
language: ENGLISH, HINDI (Devanagari), HINGLISH (Hindi in Latin script) or OTHER.
evidence_start, evidence_end: character offsets in the text of the words that best support \
the label."""

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")
_HINGLISH_WORDS = frozenset(
    [
        "hai",
        "hain",
        "nahi",
        "nahin",
        "mera",
        "meri",
        "mere",
        "mujhe",
        "kya",
        "kyun",
        "gaya",
        "gaye",
        "gayi",
        "hua",
        "hui",
        "kar",
        "karo",
        "kiya",
        "paise",
        "paisa",
        "abhi",
        "tak",
        "bhi",
        "aur",
        "se",
        "ko",
        "ka",
        "ki",
        "ke",
        "raha",
        "rahi",
        "wapas",
        "kab",
    ]
)
_DEFICIENCY_CUES = re.compile(
    r"(?i)\b(?:not\s+(?:been\s+)?(?:credited|received|refunded|reversed|resolved)|debited|"
    r"deducted|fraud\w*|unauthori[sz]ed|complain\w*|failed|wrong(?:ly)?|charged|refund|"
    r"cheat\w*|harass\w*|scam|grievance|"
    r"kat\s+(?:gaya|gaye|gayi)|nahi\s+(?:aaya|aaye|mila|mile)|wapas\s+nahi|dhokha)"
    r"|शिकायत|धोखा|कट\s*गए|कट\s*गया|नहीं\s*आए|नहीं\s*मिल"
)


def detect_language(text: str) -> Language:
    """A script-and-wordlist guess, used when no model answer is available."""
    devanagari = len(_DEVANAGARI.findall(text))
    latin = len(_LATIN.findall(text))
    if devanagari and devanagari >= latin:
        return Language.HINDI
    words = re.findall(r"[a-z]+", text.lower())
    if sum(w in _HINGLISH_WORDS for w in words) >= 2:
        return Language.HINGLISH
    return Language.ENGLISH if latin else Language.OTHER


def has_deficiency_cue(text: str) -> bool:
    """Whether the text contains words that suggest a deficiency in service."""
    return _DEFICIENCY_CUES.search(text) is not None


def _schema(gate: TriageGate) -> dict[str, JsonValue]:
    schema: dict[str, Any] = TriageAnswer.model_json_schema()
    if gate.categories:
        schema["properties"]["category"] = {"enum": [*gate.categories, None]}
    return cast(dict[str, JsonValue], schema)


def _request(masked: str, gate: TriageGate) -> LlmRequest:
    if gate.categories:
        instruction = "one of " + ", ".join(gate.categories) + ", or null if none fits."
    else:
        instruction = "always null."
    return LlmRequest(
        prompt_id=TRIAGE_PROMPT_ID,
        prompt_version=TRIAGE_PROMPT_VERSION,
        system=_SYSTEM.format(category_instruction=instruction),
        text=masked,
        output_schema=_schema(gate),
    )


def _manual(complaint_id: str, text: str, reason: str) -> TriageResult:
    return TriageResult(
        complaint_id=complaint_id,
        is_complaint=True,
        model_label=None,
        confidence=None,
        issue_type=None,
        category=None,
        language=detect_language(text),
        provenance=None,
        finding=None,
        review_task=None,
        needs_manual=True,
        reason=reason,
    )


def triage(
    text: str,
    *,
    complaint_id: str,
    document_ref: str,
    gateway: LlmGateway | None,
    masker: PiiMasker,
    as_of: AwareDatetime,
    gate: TriageGate | None = None,
) -> TriageResult:
    """Triage one customer text. PII is masked before the model sees it.

    ``document_ref`` names the masked text that provenance spans point into. ``gateway=None``
    means no model is configured: the text is a complaint and goes to the manual queue.
    """
    gate = gate or TriageGate()
    if gateway is None:
        return _manual(complaint_id, text, "No model configured; triage by a person.")
    masked = masker.mask(text)
    try:
        response = gateway.complete(_request(masked.text, gate))
        answer = TriageAnswer.model_validate(response.output)
    except (LlmCallError, LlmOutputError) as exc:
        return _manual(complaint_id, text, f"Model unavailable ({exc}); triage by a person.")
    except ValidationError:
        return _manual(complaint_id, text, "Model answer did not fit the schema.")

    category = answer.category if answer.category in gate.categories else None
    span = None
    if answer.evidence_start < answer.evidence_end <= len(masked.text):
        span = TextSpan(
            document_ref=document_ref, start=answer.evidence_start, end=answer.evidence_end
        )
    provenance = Provenance(
        source=FactSource.LLM,
        model=response.model,
        prompt_version=response.prompt_version,
        span=span,
    )

    cue = has_deficiency_cue(masked.text)
    confident = answer.confidence >= gate.not_complaint_min_confidence
    is_complaint = answer.label is TriageLabel.COMPLAINT or cue or not confident
    if answer.label is TriageLabel.COMPLAINT:
        reason = "Model labelled it a complaint."
    elif cue:
        reason = f"Model said {answer.label.value}, but the text has a deficiency cue."
    elif not confident:
        reason = f"Model said {answer.label.value} below the confidence threshold."
    else:
        reason = f"Model said {answer.label.value} with confidence {answer.confidence:.2f}."

    finding = PerceptionFinding(
        finding_id=f"F-{TRIAGE_PROMPT_ID}-{complaint_id}-{document_ref}",
        complaint_id=complaint_id,
        kind=FindingKind.IS_COMPLAINT if is_complaint else FindingKind.NOT_A_COMPLAINT,
        provenance=provenance,
        found_at=as_of,
        detail=reason,
    )
    return TriageResult(
        complaint_id=complaint_id,
        is_complaint=is_complaint,
        model_label=answer.label,
        confidence=answer.confidence,
        issue_type=answer.issue_type,
        category=category,
        language=answer.language,
        provenance=provenance,
        finding=finding,
        review_task=review_task_for_finding(finding),
        needs_manual=False,
        reason=reason,
    )
