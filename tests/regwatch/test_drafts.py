"""Proposals are DRAFT, unsigned, value-preserving, and never written into rules/."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from abhiyogah.domain.enums import RuleStatus, Verification
from abhiyogah.registry.schema import Obligation
from abhiyogah.regwatch.drafts import DraftError, ProposalSet, draft_proposals, write_proposals
from abhiyogah.regwatch.extract import ExtractedText, html_paragraphs
from abhiyogah.regwatch.fetcher import Fetched
from abhiyogah.regwatch.impact import Relation, link_impacts
from abhiyogah.regwatch.raw_store import RawStore
from abhiyogah.regwatch.relevance import classify
from tests.regwatch.conftest import FETCHED_AT, fixture
from tests.regwatch.test_impact import ALL

URL = "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=990001"
TODAY = date(2099, 1, 7)


def signed(ob: Obligation) -> Obligation:
    """The obligation as if the owner had signed it off."""
    return ob.model_copy(
        update={
            "status": RuleStatus.IN_FORCE,
            "verification": Verification.PRIMARY_TEXT_READ,
            "signed_off_by": "owner@example.org",
        }
    )


def pipeline(tmp_path: Path, obligations: list[Obligation]) -> ProposalSet:
    """Store, extract, classify, link and draft the synthetic IO amendment."""
    body = fixture("circular_io_amendment.html")
    fetched = Fetched(
        url=URL,
        final_url=URL,
        status=200,
        content_type="text/html",
        body=body,
        fetched_at=FETCHED_AT,
    )
    doc = RawStore(tmp_path / "raw").put(
        fetched, title="Synthetic IO amendment", published_on=date(2099, 1, 5)
    )
    text = ExtractedText(
        sha256=doc.sha256, method="html", paragraphs=html_paragraphs(body.decode())
    )
    links = link_impacts(text, obligations)
    return draft_proposals(doc, text, classify(text), links, obligations)


def test_proposals_are_draft_unsigned_and_change_no_value(tmp_path: Path) -> None:
    """Even from a signed, in-force rule: DRAFT, no sign-off, UNVERIFIED, same parameters."""
    obligations = [signed(ob) for ob in ALL]
    got = pipeline(tmp_path, obligations)
    by_id = {ob.obligation_id: ob for ob in obligations}
    assert {p.obligation_id for p in got.proposals} == {
        "IO-CB-2026-14-1-b",
        "IO-CB-2026-9-1",
        "OLD-2098-3",
    }
    for p in got.proposals:
        before = by_id[p.obligation_id]
        assert p.obligation.status is RuleStatus.DRAFT
        assert p.obligation.signed_off_by is None
        assert p.obligation.verification is Verification.UNVERIFIED
        assert p.obligation.parameters == before.parameters
        assert p.obligation.clock == before.clock
        assert (p.obligation.valid_from, p.obligation.valid_to) == (
            before.valid_from,
            before.valid_to,
        )
        assert "RBI/2099-2100/901" in (p.obligation.supersedes_note or "")
        reparsed = Obligation.model_validate(yaml.safe_load(p.yaml_text))
        assert reparsed == p.obligation
        assert p.yaml_text.startswith("# REGWATCH PROPOSAL")
        assert "signed_off_by" not in p.yaml_text


def test_summary_asks_the_reviewer_with_the_paragraphs(tmp_path: Path) -> None:
    """One section per obligation, with the question and the cited text."""
    got = pipeline(tmp_path, list(ALL))
    md = got.summary_md
    assert "human legal review" in md
    assert "### IO-CB-2026-14-1-b: AMENDS (CLAUSE)" in md
    assert "### OLD-2098-3: SUPERSEDES (CIRCULAR)" in md
    assert "Paragraph 14(1)(b) of the Directions" in md
    assert "Weak link" in md  # IO-CB-2026-9-1 is instrument-only
    assert "Published: 2099-01-05" in md
    relations = {p.obligation_id: p.link.relation for p in got.proposals}
    assert relations["OLD-2098-3"] is Relation.SUPERSEDES


def test_no_link_still_gets_a_summary(tmp_path: Path) -> None:
    """With no obligation loaded, the reviewer is asked whether a new one is needed."""
    got = pipeline(tmp_path, [])
    assert got.proposals == []
    assert "No existing obligation is linked" in got.summary_md


def test_write_proposals_refuses_rules_dirs(tmp_path: Path) -> None:
    """Never into rules/; never over an existing proposal."""
    got = pipeline(tmp_path, list(ALL))
    with pytest.raises(DraftError, match="rules directory"):
        write_proposals(got, tmp_path / "repo" / "rules" / "obligations", TODAY)
    out = write_proposals(got, tmp_path / "proposals", TODAY)
    assert out.name == f"2099-01-07-{got.document.sha256[:12]}"
    assert sorted(p.name for p in out.iterdir()) == [
        "IO-CB-2026-14-1-b.yaml",
        "IO-CB-2026-9-1.yaml",
        "OLD-2098-3.yaml",
        "summary.md",
    ]
    with pytest.raises(FileExistsError):
        write_proposals(got, tmp_path / "proposals", TODAY)


def test_links_to_unloaded_obligations_are_refused(tmp_path: Path) -> None:
    """A link must name a loaded obligation."""
    got = pipeline(tmp_path, list(ALL))
    with pytest.raises(DraftError):
        draft_proposals(
            got.document,
            ExtractedText(sha256=got.document.sha256, method="html", paragraphs=[]),
            got.relevance,
            [p.link for p in got.proposals],
            [],
        )
