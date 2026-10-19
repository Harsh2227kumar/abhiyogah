"""Text extraction from stored RBI documents, keeping paragraph anchors.

A document becomes an ordered list of ``Paragraph``s. Each has a positional ``anchor`` that is
stable for the same bytes (``p7`` in HTML, ``page2-p3`` in a PDF) and, when the paragraph starts
with one, the ``number`` as printed (``3``, ``14.2``, ``(a)``, ``(iv)``). Downstream steps cite
paragraphs by anchor, so a reviewer can find the exact text in the stored original.

HTML uses the standard library parser: block elements (``p``, ``li``, headings, cells, ``div``)
end a paragraph, ``script``/``style`` are dropped. PDFs need ``pypdf``, which is not a project
dependency yet (see the Requests in ``tasks/07-mcp-regwatch.md``); it is imported when needed and
``ExtractionError`` says how to get it. In PDF and plain text a paragraph ends at a blank line or
where a numbered line begins.
"""

import importlib
import io
import re
from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from abhiyogah.regwatch.raw_store import RawDocument

__all__ = [
    "ExtractedText",
    "ExtractionError",
    "Paragraph",
    "extract",
    "html_paragraphs",
    "text_paragraphs",
]

_NUMBER = re.compile(r"^(\d{1,3}\.(?:\d{1,3}\.?)*|\((?:[a-z]{1,2}|[ivxlc]{1,6}|\d{1,3})\))\s+")
"""A leading paragraph number: ``3.``, ``14.2``, ``(a)``, ``(iv)``, ``(2)``; a bare ``10`` is not."""

_BLOCKS = frozenset(
    {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "div", "tr", "table", "blockquote"}
)
_SKIP = frozenset({"script", "style", "head", "noscript"})
_WS = re.compile(r"\s+")


class ExtractionError(Exception):
    """The document's format cannot be extracted here."""


class Paragraph(BaseModel):
    """One paragraph of a document, in order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anchor: str = Field(description="Positional and stable for the same bytes, e.g. 'p7'.")
    number: str | None = Field(default=None, description="As printed, e.g. '3', '(a)'.")
    page: int | None = Field(default=None, ge=1, description="1-based PDF page.")
    text: str


class ExtractedText(BaseModel):
    """A stored document's paragraphs and how they were extracted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str
    method: str = Field(description="'html', 'pdf' or 'text'.")
    paragraphs: list[Paragraph]

    def find(self, anchor: str) -> Paragraph:
        """The paragraph with ``anchor``; ``KeyError`` if there is none."""
        for p in self.paragraphs:
            if p.anchor == anchor:
                return p
        raise KeyError(anchor)

    def full_text(self) -> str:
        """All paragraphs, one per line."""
        return "\n".join(p.text for p in self.paragraphs)


def _number(text: str) -> str | None:
    """The paragraph number ``text`` starts with, without a trailing dot."""
    m = _NUMBER.match(text)
    return m.group(1).rstrip(".") if m else None


class _Blocks(HTMLParser):
    """Collects the text of block elements, in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._buf: list[str] = []
        self._skip = 0

    def _flush(self) -> None:
        text = _WS.sub(" ", "".join(self._buf)).strip()
        if text:
            self.blocks.append(text)
        self._buf = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCKS:
            self._flush()
        elif tag == "br":
            self._buf.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._buf.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def html_paragraphs(html: str) -> list[Paragraph]:
    """Paragraphs of an HTML page, anchored ``p1``, ``p2``, ..."""
    parser = _Blocks()
    parser.feed(html)
    parser.close()
    return [
        Paragraph(anchor=f"p{i}", number=_number(t), text=t) for i, t in enumerate(parser.blocks, 1)
    ]


def text_paragraphs(text: str, page: int | None = None) -> list[Paragraph]:
    """Paragraphs of plain text: split at blank lines and where a numbered line begins."""
    chunks: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or (_NUMBER.match(line) and current):
            if current:
                chunks.append(current)
            current = [line] if line else []
            continue
        current.append(line)
    if current:
        chunks.append(current)
    prefix = f"page{page}-" if page is not None else ""
    out: list[Paragraph] = []
    for i, chunk in enumerate(chunks, 1):
        joined = _WS.sub(" ", " ".join(chunk)).strip()
        out.append(
            Paragraph(anchor=f"{prefix}p{i}", number=_number(joined), page=page, text=joined)
        )
    return out


def _pdf_pages(body: bytes) -> list[str]:
    """Each page's text, via ``pypdf``."""
    try:
        pypdf: Any = importlib.import_module("pypdf")
    except ModuleNotFoundError as exc:
        raise ExtractionError("PDF extraction needs pypdf: uv pip install pypdf") from exc
    reader = pypdf.PdfReader(io.BytesIO(body))
    return [str(page.extract_text() or "") for page in reader.pages]


def extract(doc: RawDocument, body: bytes) -> ExtractedText:
    """Paragraphs of a stored document (``body`` is the blob ``doc`` names)."""
    kind = doc.content_type.lower()
    if body.startswith(b"%PDF") or "pdf" in kind:
        pages = _pdf_pages(body)
        paragraphs = [p for n, t in enumerate(pages, 1) for p in text_paragraphs(t, page=n)]
        return ExtractedText(sha256=doc.sha256, method="pdf", paragraphs=paragraphs)
    text = body.decode("utf-8", errors="replace")
    if "html" in kind or "<html" in text[:2048].lower():
        return ExtractedText(sha256=doc.sha256, method="html", paragraphs=html_paragraphs(text))
    if kind.startswith("text/") or not kind:
        return ExtractedText(sha256=doc.sha256, method="text", paragraphs=text_paragraphs(text))
    raise ExtractionError(f"cannot extract text from {doc.content_type!r}")
