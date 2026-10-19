"""Change-impact linking: which obligations a new circular may amend, supersede or repeal.

The linker reads an extracted document against the loaded obligations and proposes links, each
with the paragraphs that justify it. Three kinds of evidence:

- ``CIRCULAR``: the document names a circular number that is an obligation's ``instrument_ref``
  (or appears in its ``source_url``).
- ``CLAUSE``: the document names an obligation's instrument and refers to its clause (exactly, as
  a parent such as ``paragraph 14`` for ``14(1)(b)``, or inside a range such as ``paras 67-71``).
- ``INSTRUMENT``: the document names the instrument but none of the obligation's clauses.

The relation (``SUPERSEDES``, ``REPEALS``, ``AMENDS``, else ``MENTIONS``) is read from the verbs of
the cited paragraphs. Links are proposals for a human; nothing here changes a rule.
"""

import re
from collections.abc import Iterable, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from abhiyogah.registry.schema import Obligation
from abhiyogah.regwatch.extract import ExtractedText, Paragraph
from abhiyogah.regwatch.raw_store import CIRCULAR_NUMBER

__all__ = [
    "Evidence",
    "ImpactLink",
    "Relation",
    "clause_refs",
    "link_impacts",
    "normalise_instrument",
]


class Relation(StrEnum):
    """What the document does to the obligation, strongest first."""

    SUPERSEDES = "SUPERSEDES"
    REPEALS = "REPEALS"
    AMENDS = "AMENDS"
    MENTIONS = "MENTIONS"


class Evidence(StrEnum):
    """Why the obligation is linked, strongest first."""

    CIRCULAR = "CIRCULAR"
    CLAUSE = "CLAUSE"
    INSTRUMENT = "INSTRUMENT"


_RELATION_WORDS: tuple[tuple[Relation, re.Pattern[str]], ...] = (
    (Relation.SUPERSEDES, re.compile(r"\bsupersed(?:e|es|ed|ing)\b", re.IGNORECASE)),
    (
        Relation.REPEALS,
        re.compile(r"\b(?:repeal(?:s|ed)?|withdraw(?:n|s)?|rescind(?:ed)?)\b", re.I),
    ),
    (
        Relation.AMENDS,
        re.compile(
            r"\b(?:amend(?:s|ed|ment|ments)?|substitut(?:e|ed|ion)|modif(?:y|ied|ication)|"
            r"insert(?:ed)?|omitted|shall be read with)\b",
            re.IGNORECASE,
        ),
    ),
)
_ORDER = {r: i for i, r in enumerate(Relation)}
_EVIDENCE_ORDER = {e: i for i, e in enumerate(Evidence)}

_CLAUSE = r"\d{1,3}(?:\.\d{1,3})*(?:\([0-9a-z]{1,4}\))*"
_REF = re.compile(
    rf"\b(?:paragraphs?|paras?\.?|clauses?|cl\.|sections?|sub-paragraph)\s+"
    rf"({_CLAUSE}(?:\s*(?:-|–|to)\s*{_CLAUSE})?)",
    re.IGNORECASE,
)
_TOKEN = re.compile(_CLAUSE)


class ImpactLink(BaseModel):
    """A proposed link from a new document to an obligation, with its evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    obligation_id: str
    relation: Relation
    evidence: Evidence
    anchors: list[str] = Field(min_length=1, description="Paragraphs that justify the link.")
    detail: str = Field(description="What matched, e.g. 'clause 14(1)(b) of <instrument>'.")


def normalise_instrument(name: str) -> str:
    """Lower case, 'Reserve Bank of India' as 'rbi', dashes as '-', single spaces, no 'the'."""
    s = name.lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"reserve\s+bank\s+of\s+india", "rbi", s)
    s = re.sub(r"\bthe\b", " ", s)
    s = re.sub(r"\s*-\s*", " - ", s)
    return re.sub(r"\s+", " ", s).strip()


def _range(ref: str) -> tuple[str, str] | None:
    """The two ends of ``67-71`` / ``67 to 71``, if ``ref`` is a range."""
    parts = re.split(r"\s*(?:-|–|to)\s*", ref)
    return (parts[0], parts[1]) if len(parts) == 2 else None


def clause_refs(text: str) -> list[str]:
    """Clause references in ``text``, as written (``14(1)(b)``, ``67-71``)."""
    return [m.group(1).strip() for m in _REF.finditer(text)]


def _covers(ref: str, clause_token: str) -> bool:
    """True if a document reference ``ref`` covers an obligation clause token."""
    if ref == clause_token or clause_token.startswith(ref + "("):
        return True
    span = _range(ref)
    if span is None:
        return False
    head = re.match(r"\d+", clause_token)
    lo, hi = (re.match(r"\d+", end) for end in span)
    if head is None or lo is None or hi is None:
        return False
    return int(lo.group(0)) <= int(head.group(0)) <= int(hi.group(0))


def _clause_tokens(ob: Obligation) -> list[str]:
    """The obligation's clause numbers; a range such as ``paras 67-71`` expands to 67 ... 71."""
    span = re.search(r"\b(\d{1,3})\s*[-–]\s*(\d{1,3})\b", ob.clause)
    if span is not None and int(span.group(1)) <= int(span.group(2)):
        return [str(n) for n in range(int(span.group(1)), int(span.group(2)) + 1)]
    return _TOKEN.findall(ob.clause)


def _relation(paragraphs: Iterable[Paragraph]) -> Relation:
    """The strongest relation word in ``paragraphs``; MENTIONS if none."""
    found = [r for p in paragraphs for r, pattern in _RELATION_WORDS if pattern.search(p.text)]
    return min(found, key=_ORDER.__getitem__, default=Relation.MENTIONS)


def _instrument_paragraphs(text: ExtractedText, instrument: str) -> list[Paragraph]:
    """Paragraphs that name ``instrument``."""
    want = normalise_instrument(instrument)
    return [p for p in text.paragraphs if want in normalise_instrument(p.text)]


def link_impacts(text: ExtractedText, obligations: Sequence[Obligation]) -> list[ImpactLink]:
    """Proposed links, one per obligation (its strongest evidence), sorted by obligation ID."""
    by_number: dict[str, list[Paragraph]] = {}
    for p in text.paragraphs:
        for number in CIRCULAR_NUMBER.findall(p.text):
            by_number.setdefault(number, []).append(p)
    refs = [(p, ref) for p in text.paragraphs for ref in clause_refs(p.text)]
    links: list[ImpactLink] = []
    for ob in obligations:
        candidates: list[ImpactLink] = []
        for number, paras in by_number.items():
            if number == ob.instrument_ref or number in str(ob.source_url):
                candidates.append(
                    ImpactLink(
                        obligation_id=ob.obligation_id,
                        relation=_relation(paras),
                        evidence=Evidence.CIRCULAR,
                        anchors=[p.anchor for p in paras],
                        detail=f"circular {number} is this obligation's instrument",
                    )
                )
        named = _instrument_paragraphs(text, ob.instrument)
        if named:
            tokens = _clause_tokens(ob)
            hit = [(p, r) for p, r in refs if any(_covers(r, t) for t in tokens)]
            if hit:
                paras = list(dict.fromkeys(p for p, _ in hit))
                cited = ", ".join(dict.fromkeys(r for _, r in hit))
                candidates.append(
                    ImpactLink(
                        obligation_id=ob.obligation_id,
                        relation=_relation(paras),
                        evidence=Evidence.CLAUSE,
                        anchors=list(dict.fromkeys(p.anchor for p in [*named, *paras])),
                        detail=f"{cited} of {ob.instrument} (obligation clause {ob.clause})",
                    )
                )
            else:
                candidates.append(
                    ImpactLink(
                        obligation_id=ob.obligation_id,
                        relation=_relation(named),
                        evidence=Evidence.INSTRUMENT,
                        anchors=[p.anchor for p in named],
                        detail=f"names {ob.instrument} but not clause {ob.clause}",
                    )
                )
        if candidates:
            links.append(min(candidates, key=lambda c: _EVIDENCE_ORDER[c.evidence]))
    return sorted(links, key=lambda link: link.obligation_id)
