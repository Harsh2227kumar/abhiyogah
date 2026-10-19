"""Fact extraction: amount, UTR, transaction date T, channel and account type.

The model reads the masked text and returns each fact with the character span it came from.
Deterministic code then keeps a fact only if it is grounded and well-formed:

- the span lies inside the masked text and is not a PII placeholder;
- an amount or UTR must appear in its span (digits for amounts, verbatim for UTRs);
- a date must parse as ``YYYY-MM-DD`` and must not be after ``as_of`` (Asia/Kolkata);
- channel and account type must be members of the domain enums;
- two different values for the same fact are a conflict, and both are dropped.

Each kept fact becomes one ``FACTS_RECORDED`` ``ComplaintEvent`` whose provenance names the model,
prompt version and span, so a decision record can cite exactly where the value came from. Dropped
facts are reported with a reason; a person fills them in. Liability, breach and compensation are
never extracted (CLAUDE.md hard rule 4).
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, ValidationError

from abhiyogah.domain.enums import AccountType, Channel, FactSource
from abhiyogah.domain.events import ComplaintEvent, EventType, Provenance, TextSpan
from abhiyogah.domain.money import PAISE_PER_RUPEE
from abhiyogah.domain.tz import ist_date
from abhiyogah.perception.errors import LlmCallError, LlmOutputError
from abhiyogah.perception.gateway import LlmGateway, LlmRequest
from abhiyogah.perception.pii import PiiMasker

__all__ = [
    "EXTRACTION_PROMPT_ID",
    "EXTRACTION_PROMPT_VERSION",
    "DroppedFact",
    "ExtractedFact",
    "ExtractionAnswer",
    "ExtractionResult",
    "FactKind",
    "extract_facts",
    "parse_amount_paise",
]

EXTRACTION_PROMPT_ID = "extract_facts"
EXTRACTION_PROMPT_VERSION = "extract-v1"


class FactKind(StrEnum):
    """Facts the model may extract, and the ``ComplaintFacts`` payload key each one sets."""

    AMOUNT = "AMOUNT"
    UTR = "UTR"
    TRANSACTION_DATE = "TRANSACTION_DATE"
    CHANNEL = "CHANNEL"
    ACCOUNT_TYPE = "ACCOUNT_TYPE"


PAYLOAD_KEYS: dict[FactKind, str] = {
    FactKind.AMOUNT: "amount_paise",
    FactKind.UTR: "utr",  # evidence only; not a ComplaintFacts field, so folding ignores it
    FactKind.TRANSACTION_DATE: "transaction_date_t",
    FactKind.CHANNEL: "channel",
    FactKind.ACCOUNT_TYPE: "account_type",
}


class ExtractedFactAnswer(BaseModel):
    """One fact as the model reports it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FactKind
    value: str = Field(description="Amount in rupees, UTR, ISO date, or an enum member name.")
    evidence_start: int = Field(ge=0)
    evidence_end: int = Field(ge=0)


class ExtractionAnswer(BaseModel):
    """The model's answer: every fact it found. Its JSON schema is what the model must follow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: list[ExtractedFactAnswer]


class ExtractedFact(BaseModel):
    """A fact that passed the checks, as it goes into the event payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FactKind
    payload_key: str
    value: JsonValue
    span: TextSpan


class DroppedFact(BaseModel):
    """A fact the model reported that was not kept, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FactKind
    value: str
    reason: str


class ExtractionResult(BaseModel):
    """Extraction outcome: the events to append, and anything a person must check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    complaint_id: str
    facts: list[ExtractedFact]
    events: list[ComplaintEvent]
    dropped: list[DroppedFact]
    needs_manual: bool
    """True when the model could not be used; a person must extract the facts."""
    reason: str = ""


_SYSTEM = """You extract facts from a customer complaint sent to an Indian bank. The text is \
masked: values like <ACCOUNT_NUMBER_1> replace personal data; never return a placeholder.

Report only facts stated in the text, each with the character offsets of the words it came from:
- AMOUNT: the disputed amount in rupees, digits only with an optional decimal part (e.g. 15000.50).
- UTR: the UTR, RRN or transaction reference exactly as written.
- TRANSACTION_DATE: the date of the disputed transaction as YYYY-MM-DD.
- CHANNEL: one of {channels}.
- ACCOUNT_TYPE: one of {account_types}.
Leave a fact out if the text does not state it. Do not guess."""

_PLACEHOLDER = re.compile(r"<[A-Z_]+_\d+>")
_AMOUNT = re.compile(r"^\d+(?:\.\d{1,2})?$")
_UTR = re.compile(r"^[A-Za-z0-9]{10,22}$")


def parse_amount_paise(value: str) -> int | None:
    """Rupees as written by the model (``"15,000.50"``) to integer paise, or ``None``."""
    cleaned = value.replace(",", "").strip()
    if not _AMOUNT.match(cleaned):
        return None
    try:
        paise = Decimal(cleaned) * PAISE_PER_RUPEE
    except InvalidOperation:
        return None
    return int(paise) if paise > 0 else None


def _request(masked: str) -> LlmRequest:
    return LlmRequest(
        prompt_id=EXTRACTION_PROMPT_ID,
        prompt_version=EXTRACTION_PROMPT_VERSION,
        system=_SYSTEM.format(
            channels=", ".join(c.value for c in Channel),
            account_types=", ".join(a.value for a in AccountType),
        ),
        text=masked,
        output_schema=ExtractionAnswer.model_json_schema(),
    )


class _RejectedError(Exception):
    """A reported fact failed a check; the message is the reason."""


def _check(answer: ExtractedFactAnswer, masked: str, as_of: AwareDatetime) -> JsonValue:
    """The payload value if the fact passes its checks; raises ``_RejectedError`` otherwise."""
    if not answer.evidence_start < answer.evidence_end <= len(masked):
        raise _RejectedError("span is outside the text")
    evidence = masked[answer.evidence_start : answer.evidence_end]
    if _PLACEHOLDER.search(answer.value) or _PLACEHOLDER.fullmatch(evidence.strip()):
        raise _RejectedError("value is masked personal data")
    match answer.kind:
        case FactKind.AMOUNT:
            paise = parse_amount_paise(answer.value)
            if paise is None:
                raise _RejectedError("amount is not a positive rupee value")
            digits = re.sub(r"\D", "", answer.value.split(".")[0])
            if digits not in re.sub(r"\D", "", evidence):
                raise _RejectedError("amount does not appear in its span")
            return paise
        case FactKind.UTR:
            utr = answer.value.strip()
            if not _UTR.match(utr):
                raise _RejectedError("UTR is not 10-22 letters or digits")
            if utr not in evidence:
                raise _RejectedError("UTR does not appear in its span")
            return utr
        case FactKind.TRANSACTION_DATE:
            try:
                day = date.fromisoformat(answer.value.strip())
            except ValueError as exc:
                raise _RejectedError("date is not YYYY-MM-DD") from exc
            if day > ist_date(as_of):
                raise _RejectedError("date is in the future")
            return day.isoformat()
        case FactKind.CHANNEL:
            if answer.value not in Channel.__members__:
                raise _RejectedError("not a known channel")
            return answer.value
        case FactKind.ACCOUNT_TYPE:
            if answer.value not in AccountType.__members__:
                raise _RejectedError("not a known account type")
            return answer.value


def extract_facts(
    text: str,
    *,
    complaint_id: str,
    document_ref: str,
    gateway: LlmGateway | None,
    masker: PiiMasker,
    as_of: AwareDatetime,
) -> ExtractionResult:
    """Extract facts from one customer text into ``FACTS_RECORDED`` events with LLM provenance."""
    if gateway is None:
        return ExtractionResult(
            complaint_id=complaint_id,
            facts=[],
            events=[],
            dropped=[],
            needs_manual=True,
            reason="No model configured; a person extracts the facts.",
        )
    masked = masker.mask(text).text
    try:
        response = gateway.complete(_request(masked))
        answer = ExtractionAnswer.model_validate(response.output)
    except (LlmCallError, LlmOutputError, ValidationError) as exc:
        return ExtractionResult(
            complaint_id=complaint_id,
            facts=[],
            events=[],
            dropped=[],
            needs_manual=True,
            reason=f"Model unavailable or answer malformed ({type(exc).__name__}).",
        )

    kept: dict[FactKind, ExtractedFact] = {}
    reported: dict[FactKind, str] = {}
    conflicted: set[FactKind] = set()
    dropped: list[DroppedFact] = []
    for item in answer.facts:
        try:
            checked = _check(item, masked, as_of)
        except _RejectedError as rejected:
            dropped.append(DroppedFact(kind=item.kind, value=item.value, reason=str(rejected)))
            continue
        fact = ExtractedFact(
            kind=item.kind,
            payload_key=PAYLOAD_KEYS[item.kind],
            value=checked,
            span=TextSpan(
                document_ref=document_ref, start=item.evidence_start, end=item.evidence_end
            ),
        )
        previous = kept.get(item.kind)
        if item.kind in conflicted or (previous is not None and previous.value != fact.value):
            if previous is not None:
                dropped.append(
                    DroppedFact(kind=item.kind, value=reported[item.kind], reason="conflict")
                )
                del kept[item.kind]
            conflicted.add(item.kind)
            dropped.append(DroppedFact(kind=item.kind, value=item.value, reason="conflict"))
            continue
        if previous is None:
            kept[item.kind] = fact
            reported[item.kind] = item.value

    facts = [kept[k] for k in FactKind if k in kept]
    events = [
        ComplaintEvent(
            event_id=f"EV-{EXTRACTION_PROMPT_ID}-{complaint_id}-{document_ref}-{f.kind.value}",
            complaint_id=complaint_id,
            type=EventType.FACTS_RECORDED,
            occurred_at=as_of,
            recorded_at=as_of,
            payload={f.payload_key: f.value},
            provenance=Provenance(
                source=FactSource.LLM,
                model=response.model,
                prompt_version=response.prompt_version,
                span=f.span,
            ),
        )
        for f in facts
    ]
    return ExtractionResult(
        complaint_id=complaint_id,
        facts=facts,
        events=events,
        dropped=dropped,
        needs_manual=False,
    )
