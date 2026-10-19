"""Relevance: which watched topics a new RBI document touches, and where.

Keywords decide first. Each topic has search phrases (search terms, not regulatory values); each hit
is recorded with the paragraph anchor it was found in, so a reviewer sees why a document was kept.

An LLM is optional and can only **add**: it may suggest topics the keywords missed (raising recall),
never remove a keyword hit. A suggestion is a fact with provenance (model, prompt version, the
paragraph anchors it cites), and any document where the LLM and the keywords disagree is flagged
``needs_review``. Nothing here reads a document as "not relevant" on an LLM's word alone, and no
step changes a rule: relevance only decides what a human looks at.
"""

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from abhiyogah.regwatch.extract import ExtractedText, Paragraph

__all__ = [
    "KEYWORDS",
    "Hit",
    "LlmSuggestion",
    "Relevance",
    "Topic",
    "TopicSuggester",
    "classify",
    "keyword_hits",
]


class Topic(StrEnum):
    """What Regulatory Watch watches for."""

    COMPLAINTS = "COMPLAINTS"
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"
    FRAUD = "FRAUD"
    KYC = "KYC"
    PAYMENT_TAT = "PAYMENT_TAT"
    INTERNAL_OMBUDSMAN = "INTERNAL_OMBUDSMAN"


def _ci(*phrases: str) -> list[re.Pattern[str]]:
    """Case-insensitive whole-word patterns; whitespace in a phrase matches any whitespace."""
    return [
        re.compile(r"\b" + r"\s+".join(map(re.escape, p.split())) + r"\b", re.IGNORECASE)
        for p in phrases
    ]


def _cs(*tokens: str) -> list[re.Pattern[str]]:
    """Case-sensitive whole-word patterns, for acronyms that are also common syllables."""
    return [re.compile(r"\b" + re.escape(t) + r"\b") for t in tokens]


KEYWORDS: dict[Topic, list[re.Pattern[str]]] = {
    Topic.COMPLAINTS: _ci(
        "complaint",
        "complaints",
        "grievance",
        "grievances",
        "grievance redress",
        "Integrated Ombudsman",
        "RB-IOS",
        "Ombudsman Scheme",
    ),
    Topic.CUSTOMER_SERVICE: _ci(
        "customer service",
        "customer services",
        "customer protection",
        "responsible business conduct",
        "fair practices code",
    ),
    Topic.FRAUD: _ci(
        "fraud",
        "frauds",
        "fraudulent",
        "unauthorised electronic banking",
        "unauthorized electronic banking",
        "unauthorised transaction",
        "unauthorised transactions",
        "limited liability",
        "zero liability",
    ),
    Topic.KYC: [
        *_ci("know your customer", "customer due diligence", "re-KYC", "V-CIP"),
        *_cs("KYC"),
    ],
    Topic.PAYMENT_TAT: [
        *_ci(
            "turn around time",
            "turnaround time",
            "failed transaction",
            "failed transactions",
            "auto-reversal",
            "harmonisation of turn around time",
        ),
        *_cs("TAT", "TATs"),
    ],
    Topic.INTERNAL_OMBUDSMAN: [*_ci("internal ombudsman"), *_cs("IO")],
}
"""Search phrases per topic. Extend here; every change is reviewed like code."""


class Hit(BaseModel):
    """A keyword found in a paragraph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: Topic
    term: str = Field(description="The text matched, as written in the document.")
    anchor: str


class LlmSuggestion(BaseModel):
    """A topic an LLM suggests, with provenance. It can add a topic, never remove one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: Topic
    anchors: list[str] = Field(min_length=1, description="Paragraphs the model cites.")
    model: str
    prompt_version: str
    rationale: str = ""


class TopicSuggester(Protocol):
    """An optional LLM pass (through the perception gateway) that suggests topics."""

    def suggest(self, paragraphs: Sequence[Paragraph]) -> list[LlmSuggestion]:
        """Topics the model sees, each citing paragraph anchors."""
        ...


class Relevance(BaseModel):
    """The relevance of one extracted document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str
    topics: list[Topic] = Field(description="Keyword topics plus LLM-added ones, sorted.")
    hits: list[Hit]
    suggestions: list[LlmSuggestion] = Field(default_factory=list)
    relevant: bool
    needs_review: bool = Field(
        description="An LLM suggested a topic the keywords did not find, or cited a bad anchor."
    )


def keyword_hits(paragraphs: Sequence[Paragraph]) -> list[Hit]:
    """Every keyword hit, in paragraph then topic order; a term counts once per paragraph."""
    hits: list[Hit] = []
    for p in paragraphs:
        for topic, patterns in KEYWORDS.items():
            seen: set[str] = set()
            for pattern in patterns:
                for m in pattern.finditer(p.text):
                    term = m.group(0)
                    if term.lower() not in seen:
                        seen.add(term.lower())
                        hits.append(Hit(topic=topic, term=term, anchor=p.anchor))
    return hits


def classify(text: ExtractedText, suggester: TopicSuggester | None = None) -> Relevance:
    """Keyword topics, then any LLM additions; disagreement goes to human review."""
    hits = keyword_hits(text.paragraphs)
    keyword_topics = {h.topic for h in hits}
    suggestions = suggester.suggest(text.paragraphs) if suggester is not None else []
    anchors = {p.anchor for p in text.paragraphs}
    added = {s.topic for s in suggestions} - keyword_topics
    bad_cite = any(a not in anchors for s in suggestions for a in s.anchors)
    topics = sorted(keyword_topics | added)
    return Relevance(
        sha256=text.sha256,
        topics=topics,
        hits=hits,
        suggestions=suggestions,
        relevant=bool(topics),
        needs_review=bool(added) or bad_cite,
    )
