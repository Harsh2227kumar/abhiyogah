"""Change-impact links cite paragraphs and pick the strongest evidence per obligation."""

from abhiyogah.regwatch.extract import ExtractedText, html_paragraphs, text_paragraphs
from abhiyogah.regwatch.impact import (
    Evidence,
    Relation,
    clause_refs,
    link_impacts,
    normalise_instrument,
)
from tests.evaluator.builders import obligation
from tests.regwatch.conftest import fixture

IO = "RBI (Commercial Banks – Internal Ombudsman) Directions, 2026"
RBC = "RBI (Commercial Banks – Responsible Business Conduct) Directions, 2025"
A13 = obligation()  # IO-CB-2026-14-1-b, clause 14(1)(b)
IO_OTHER = obligation(obligation_id="IO-CB-2026-9-1", clause="9(1)")
LIABILITY = obligation(obligation_id="RBCCB-2025-67-71", instrument=RBC, clause="paras 67-71")
OLD = obligation(
    obligation_id="OLD-2098-3",
    instrument="Synthetic old circular",
    instrument_ref="RBI/2098-99/777",
)
UNRELATED = obligation(obligation_id="TAT-2019-UPI-P2P", instrument="Synthetic TAT circular")
ALL = [A13, IO_OTHER, LIABILITY, OLD, UNRELATED]


def io_amendment() -> ExtractedText:
    """The synthetic IO amendment fixture."""
    paras = html_paragraphs(fixture("circular_io_amendment.html").decode())
    return ExtractedText(sha256="0" * 64, method="html", paragraphs=paras)


def text(body: str) -> ExtractedText:
    """Plain text as a document."""
    return ExtractedText(sha256="1" * 64, method="text", paragraphs=text_paragraphs(body))


def test_instrument_names_normalise() -> None:
    """'Reserve Bank of India', en dashes and spacing do not block a match."""
    assert normalise_instrument("Reserve Bank of India (Commercial Banks–Internal Ombudsman)") == (
        normalise_instrument("RBI (Commercial Banks – Internal  Ombudsman)")
    )


def test_clause_refs_are_found() -> None:
    """Paragraph, para, clause and ranges."""
    body = "Paragraph 14(1)(b) and para 9 and paras 67-71 and clause 3.2; not 14(1) alone."
    assert clause_refs(body) == ["14(1)(b)", "9", "67-71", "3.2"]


def test_io_amendment_links() -> None:
    """Clause link for 14(1)(b), instrument-only for 9(1), circular link for the superseded one."""
    text_ = io_amendment()
    links = {link.obligation_id: link for link in link_impacts(text_, ALL)}
    assert set(links) == {"IO-CB-2026-14-1-b", "IO-CB-2026-9-1", "OLD-2098-3"}

    a13 = links["IO-CB-2026-14-1-b"]
    assert (a13.evidence, a13.relation) == (Evidence.CLAUSE, Relation.AMENDS)
    assert any("14(1)(b)" in text_.find(a).text for a in a13.anchors)

    other = links["IO-CB-2026-9-1"]
    assert other.evidence is Evidence.INSTRUMENT
    assert other.relation is Relation.MENTIONS

    old = links["OLD-2098-3"]
    assert (old.evidence, old.relation) == (Evidence.CIRCULAR, Relation.SUPERSEDES)
    assert all("RBI/2098-99/777" in text_.find(a).text for a in old.anchors)


def test_parent_clause_and_ranges_cover() -> None:
    """'paragraph 14' covers 14(1)(b); 'para 69' falls inside 67-71."""
    doc = text(
        f"1. In the {IO}, paragraph 14 is substituted.\n"
        f"2. In the Reserve Bank of India (Commercial Banks - Responsible Business Conduct) "
        "Directions, 2025, para 69 is omitted."
    )
    links = {link.obligation_id: link for link in link_impacts(doc, ALL)}
    assert links["IO-CB-2026-14-1-b"].evidence is Evidence.CLAUSE
    assert links["IO-CB-2026-14-1-b"].relation is Relation.AMENDS
    assert links["RBCCB-2025-67-71"].evidence is Evidence.CLAUSE
    assert links["IO-CB-2026-9-1"].evidence is Evidence.INSTRUMENT


def test_repeal_wording() -> None:
    """Withdrawal is a repeal."""
    doc = text(f"1. The {IO} are hereby withdrawn.")
    links = {link.obligation_id: link.relation for link in link_impacts(doc, ALL)}
    assert links["IO-CB-2026-14-1-b"] is Relation.REPEALS


def test_unrelated_document_links_nothing() -> None:
    """No instrument, no circular number: no links."""
    assert link_impacts(text("1. Currency chest timings are revised."), ALL) == []
