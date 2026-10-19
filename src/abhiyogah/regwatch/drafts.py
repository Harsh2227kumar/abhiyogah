"""Draft proposals: changed obligation YAML for human legal review, never a rule change.

For each impact link, the generator copies the linked obligation and marks it as a proposal:
``status: DRAFT``, no ``signed_off_by``, obligation-level ``verification: UNVERIFIED`` (nobody has
read the new text against it yet) and a ``supersedes_note`` naming the circular, the relation and
the paragraphs to read. **No value changes**: day counts, amounts, caps, validity dates and
parameters stay as they are, because a value may only come from a human reading the primary text
(CLAUDE.md hard rule 2). The summary tells the reviewer exactly what to read and decide.

``write_proposals`` writes to a proposals directory and refuses any path inside a ``rules``
directory: proposals are copied into ``rules/`` by a human, on a branch, through review.
"""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from abhiyogah.domain.enums import RuleStatus, Verification
from abhiyogah.registry.schema import Obligation
from abhiyogah.regwatch.extract import ExtractedText
from abhiyogah.regwatch.impact import Evidence, ImpactLink, Relation
from abhiyogah.regwatch.raw_store import RawDocument
from abhiyogah.regwatch.relevance import Relevance

__all__ = [
    "DraftError",
    "Proposal",
    "ProposalSet",
    "draft_proposals",
    "write_proposals",
]

_ASK = {
    Relation.SUPERSEDES: (
        "Does the new circular replace this obligation? If so, set `valid_to` and add a new "
        "obligation for the replacement, each from the primary text."
    ),
    Relation.REPEALS: (
        "Is this obligation withdrawn? If so, from which date, and is anything saved "
        "(`REPEALED_BUT_SAVED`)?"
    ),
    Relation.AMENDS: (
        "Which values, conditions or clause wording change, and from which date? Add a new dated "
        "parameter value rather than editing the old one."
    ),
    Relation.MENTIONS: "Is this obligation affected at all? If not, close the proposal.",
}


class DraftError(Exception):
    """A proposal would be written where rules live, or would not validate."""


class Proposal(BaseModel):
    """One proposed obligation file and why it was proposed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    obligation_id: str
    link: ImpactLink
    obligation: Obligation
    yaml_text: str


class ProposalSet(BaseModel):
    """Everything Regulatory Watch proposes for one new document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: RawDocument
    relevance: Relevance
    proposals: list[Proposal]
    summary_md: str


def _note(doc: RawDocument, link: ImpactLink) -> str:
    """The ``supersedes_note`` a proposal carries."""
    number = ", ".join(doc.circular_numbers) or doc.url
    return (
        f"REGWATCH PROPOSAL (not reviewed): {number} {link.relation.value} this obligation "
        f"({link.evidence.value}: {link.detail}; read {', '.join(link.anchors)} in "
        f"raw document {doc.sha256}). Values unchanged pending human reading of the primary text."
    )


def _yaml(ob: Obligation, doc: RawDocument) -> str:
    """The obligation as YAML, field order kept, with a header saying what it is."""
    data = ob.model_dump(mode="json", exclude_none=True)
    header = (
        f"# REGWATCH PROPOSAL for human legal review. Status DRAFT; not signed off.\n"
        f"# Source document: {doc.url} (sha256 {doc.sha256}).\n"
        f"# Copy into rules/obligations/ only after review, on a branch, through a PR.\n"
    )
    return header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _proposal(ob: Obligation, link: ImpactLink, doc: RawDocument) -> Proposal:
    """A DRAFT copy of ``ob`` noting ``link``; every regulatory value unchanged."""
    proposed = Obligation.model_validate(
        {
            **ob.model_dump(),
            "status": RuleStatus.DRAFT,
            "signed_off_by": None,
            "verification": Verification.UNVERIFIED,
            "supersedes_note": _note(doc, link),
        }
    )
    return Proposal(
        obligation_id=ob.obligation_id,
        link=link,
        obligation=proposed,
        yaml_text=_yaml(proposed, doc),
    )


def _summary(
    doc: RawDocument, text: ExtractedText, relevance: Relevance, proposals: list[Proposal]
) -> str:
    """Markdown for the reviewer: the document, why it matters, and one question per obligation."""
    when = doc.published_on.isoformat() if doc.published_on else "not given"
    lines = [
        f"# Regulatory Watch proposal: {doc.title or doc.url}",
        "",
        "Generated automatically for **human legal review**. Nothing here is in force, and no "
        "value has been changed: every day count, amount, cap and date stays as it is until a "
        "reviewer reads the primary text.",
        "",
        f"- Source: {doc.url}",
        f"- Circular numbers mentioned: {', '.join(doc.circular_numbers) or 'none found'}",
        f"- Published: {when}; fetched {doc.fetched_at.isoformat()}",
        f"- Raw document: sha256 `{doc.sha256}` ({text.method}, {len(text.paragraphs)} paragraphs)",
        f"- Topics: {', '.join(t.value for t in relevance.topics) or 'none'}"
        + (" (an LLM added a topic: check it)" if relevance.needs_review else ""),
        "",
        "## Obligations to review",
        "",
    ]
    if not proposals:
        lines += [
            "No existing obligation is linked. Decide whether this document needs a new "
            "obligation; if it does, write one from the primary text.",
            "",
        ]
    for p in proposals:
        link = p.link
        lines += [
            f"### {p.obligation_id}: {link.relation.value} ({link.evidence.value})",
            "",
            f"- Obligation: {p.obligation.instrument}, {p.obligation.clause}",
            f"- Why linked: {link.detail}",
            f"- Question: {_ASK[link.relation]}",
            "- Paragraphs to read:",
            *(f"  - `{a}`: {text.find(a).text}" for a in link.anchors),
            "",
        ]
        if link.evidence is Evidence.INSTRUMENT:
            lines += ["Weak link: the instrument is named but not this clause.", ""]
    return "\n".join(lines)


def draft_proposals(
    doc: RawDocument,
    text: ExtractedText,
    relevance: Relevance,
    links: list[ImpactLink],
    obligations: list[Obligation],
) -> ProposalSet:
    """Proposals for every linked obligation, plus the reviewer's summary."""
    by_id = {ob.obligation_id: ob for ob in obligations}
    missing = [link.obligation_id for link in links if link.obligation_id not in by_id]
    if missing:
        raise DraftError(f"links to obligations not loaded: {missing}")
    proposals = [_proposal(by_id[link.obligation_id], link, doc) for link in links]
    return ProposalSet(
        document=doc,
        relevance=relevance,
        proposals=proposals,
        summary_md=_summary(doc, text, relevance, proposals),
    )


def write_proposals(proposals: ProposalSet, out_dir: Path, today: date) -> Path:
    """Write ``summary.md`` and one YAML per proposal under ``out_dir/<date>-<sha12>/``.

    Refuses any ``out_dir`` inside a ``rules`` directory; never overwrites an existing proposal.
    """
    resolved = out_dir.resolve()
    if "rules" in resolved.parts:
        raise DraftError(f"refusing to write proposals under a rules directory: {resolved}")
    target = resolved / f"{today.isoformat()}-{proposals.document.sha256[:12]}"
    target.mkdir(parents=True, exist_ok=False)
    (target / "summary.md").write_text(proposals.summary_md + "\n", encoding="utf-8")
    for p in proposals.proposals:
        (target / f"{p.obligation_id}.yaml").write_text(p.yaml_text, encoding="utf-8")
    return target
