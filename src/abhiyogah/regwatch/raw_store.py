"""The immutable raw store: every fetched RBI document as received, addressed by its SHA-256.

Layout under ``root``:

- ``blobs/<sha256>``: the exact bytes, written once (exclusive create) and made read-only.
- ``index.jsonl``: one ``RawDocument`` per line, append-only. A document fetched again with the same
  bytes from the same URL adds nothing; changed bytes at a URL add a new line, and both versions are
  kept.

Nothing here deletes or rewrites. ``verify`` re-hashes every blob against the index.
"""

import hashlib
import os
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from abhiyogah.regwatch.fetcher import Fetched

__all__ = [
    "CIRCULAR_NUMBER",
    "RawDocument",
    "RawStore",
    "RawStoreError",
    "circular_numbers",
]

CIRCULAR_NUMBER = re.compile(r"RBI/\d{4}-\d{2,4}/\d+")
"""An RBI circular reference number, e.g. ``RBI/2025-26/123``."""


class RawStoreError(Exception):
    """A blob does not match its hash, or the store was tampered with."""


class RawDocument(BaseModel):
    """One stored document and what we know about it at fetch time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    url: str
    final_url: str
    content_type: str
    size: int = Field(ge=0)
    fetched_at: AwareDatetime
    circular_numbers: list[str] = Field(
        default_factory=list, description="RBI/YYYY-YY/N references seen, in first-seen order."
    )
    published_on: date | None = Field(
        default=None, description="The publication date the source gave (feed pubDate), if any."
    )
    title: str = ""


def circular_numbers(*texts: str) -> list[str]:
    """Distinct circular numbers in ``texts``, in first-seen order."""
    seen: dict[str, None] = {}
    for text in texts:
        for match in CIRCULAR_NUMBER.findall(text):
            seen.setdefault(match, None)
    return list(seen)


def _sha256(data: bytes) -> str:
    """Hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _visible_text(fetched: Fetched) -> str:
    """The body as text when it is HTML, XML or plain text; '' for PDFs and other binaries."""
    kind = fetched.content_type.lower()
    if any(t in kind for t in ("html", "xml", "text")):
        return fetched.body.decode("utf-8", errors="replace")
    return ""


class RawStore:
    """A content-addressed, append-only store on the local filesystem."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.blobs = root / "blobs"
        self.index = root / "index.jsonl"
        self.blobs.mkdir(parents=True, exist_ok=True)

    def _write_blob(self, sha: str, body: bytes) -> None:
        """Write ``body`` once; an existing blob must hash to ``sha``."""
        path = self.blobs / sha
        if path.exists():
            if _sha256(path.read_bytes()) != sha:
                raise RawStoreError(f"blob {sha} on disk does not match its name")
            return
        tmp = self.blobs / f".{sha}.partial"
        with tmp.open("xb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.chmod(0o444)
        try:
            os.link(tmp, path)  # fails if another writer got there first; never overwrites
        except FileExistsError:
            pass
        finally:
            tmp.unlink()

    def put(
        self, fetched: Fetched, *, title: str = "", published_on: date | None = None, hint: str = ""
    ) -> RawDocument:
        """Store ``fetched``; return its record (the existing one if URL and bytes are unchanged).

        ``title`` and ``hint`` (e.g. the feed item's title and description) are searched for
        circular numbers along with the body's text.
        """
        sha = _sha256(fetched.body)
        for doc in self.documents():
            if doc.sha256 == sha and doc.url == fetched.url:
                return doc
        self._write_blob(sha, fetched.body)
        doc = RawDocument(
            sha256=sha,
            url=fetched.url,
            final_url=fetched.final_url,
            content_type=fetched.content_type,
            size=len(fetched.body),
            fetched_at=fetched.fetched_at,
            circular_numbers=circular_numbers(title, hint, _visible_text(fetched)),
            published_on=published_on,
            title=title,
        )
        with self.index.open("a", encoding="utf-8") as fh:
            fh.write(doc.model_dump_json() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return doc

    def documents(self) -> Iterator[RawDocument]:
        """Every record, oldest first."""
        if not self.index.exists():
            return
        with self.index.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield RawDocument.model_validate_json(line)

    def versions(self, url: str) -> list[RawDocument]:
        """Every stored version of ``url``, oldest first."""
        return [d for d in self.documents() if d.url == url]

    def read(self, sha: str) -> bytes:
        """A blob's bytes, checked against its hash."""
        data = (self.blobs / sha).read_bytes()
        if _sha256(data) != sha:
            raise RawStoreError(f"blob {sha} does not match its hash")
        return data

    def verify(self) -> list[str]:
        """Hashes in the index whose blob is missing or altered (empty means intact)."""
        bad: list[str] = []
        for doc in self.documents():
            path = self.blobs / doc.sha256
            if not path.exists() or _sha256(path.read_bytes()) != doc.sha256:
                bad.append(doc.sha256)
        return bad
