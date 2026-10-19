"""Extraction keeps paragraph order, numbers and stable anchors."""

import hashlib

import pytest

from abhiyogah.regwatch.extract import ExtractionError, extract, html_paragraphs, text_paragraphs
from abhiyogah.regwatch.raw_store import RawDocument
from tests.regwatch.conftest import FETCHED_AT, fixture


def doc(body: bytes, content_type: str) -> RawDocument:
    """A raw-store record for ``body``."""
    return RawDocument(
        sha256=hashlib.sha256(body).hexdigest(),
        url="https://www.rbi.org.in/x",
        final_url="https://www.rbi.org.in/x",
        content_type=content_type,
        size=len(body),
        fetched_at=FETCHED_AT,
    )


def test_html_circular_keeps_numbered_paragraphs() -> None:
    """Numbered paragraphs keep their numbers; the header block keeps its circular number."""
    body = fixture("circular_io_amendment.html")
    got = extract(doc(body, "text/html; charset=utf-8"), body)
    assert got.method == "html"
    numbered = {p.number: p for p in got.paragraphs if p.number}
    assert list(numbered) == ["1", "2", "3", "4"]
    assert "14(1)(b)" in numbered["2"].text
    assert "RBI/2098-99/777" in numbered["3"].text
    assert got.paragraphs[0].text.startswith("RBI/2099-2100/901 DOR.TEST")
    assert got.find(numbered["3"].anchor) == numbered["3"]
    assert "SYNTHETIC" not in got.full_text()  # comments are not text
    assert "Synthetic Notification (TEST ONLY)" not in got.full_text()  # <head> is skipped


def test_anchors_are_stable_for_the_same_bytes() -> None:
    """Same bytes, same anchors."""
    body = fixture("circular_io_amendment.html")
    a = extract(doc(body, "text/html"), body)
    b = extract(doc(body, "text/html"), body)
    assert [p.anchor for p in a.paragraphs] == [p.anchor for p in b.paragraphs]
    assert [p.anchor for p in a.paragraphs] == [f"p{i}" for i in range(1, len(a.paragraphs) + 1)]


def test_scripts_and_styles_are_dropped() -> None:
    """Only visible text."""
    paras = html_paragraphs("<style>p{}</style><p>One <b>bold</b><br>line</p><script>x()</script>")
    assert [p.text for p in paras] == ["One bold line"]


def test_text_splits_at_blank_lines_and_numbered_lines() -> None:
    """A wrapped line joins its paragraph; a bare number at line start does not split."""
    text = "Header\n1. First para\ncontinues here and\n10 working days later.\n(a) Sub\n\nTail"
    paras = text_paragraphs(text)
    assert [(p.anchor, p.number) for p in paras] == [
        ("p1", None),
        ("p2", "1"),
        ("p3", "(a)"),
        ("p4", None),
    ]
    assert paras[1].text == "1. First para continues here and 10 working days later."


def test_pdf_paragraphs_carry_their_page() -> None:
    """Each PDF paragraph knows its page; anchors are page-scoped."""
    pytest.importorskip("pypdf", reason="pypdf is not installed")
    body = fixture("master_direction_synthetic.pdf")
    got = extract(doc(body, "application/pdf"), body)
    assert got.method == "pdf"
    assert [(p.anchor, p.number, p.page) for p in got.paragraphs] == [
        ("page1-p1", None, 1),
        ("page1-p2", "1", 1),
        ("page1-p3", "2", 1),
        ("page2-p1", "3", 2),
        ("page2-p2", "(a)", 2),
    ]
    assert "RBI/2099-2100/903" in got.paragraphs[0].text
    assert got.paragraphs[1].text.endswith("It continues on a second line.")


def test_unknown_binary_is_refused() -> None:
    """No guessing at formats we cannot read."""
    with pytest.raises(ExtractionError):
        extract(doc(b"\x00\x01", "application/zip"), b"\x00\x01")
