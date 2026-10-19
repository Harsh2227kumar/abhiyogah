"""The raw store keeps every version as received, addressed by SHA-256, and never rewrites."""

import hashlib
import stat
from datetime import date
from pathlib import Path

import pytest

from abhiyogah.regwatch.fetcher import Fetched
from abhiyogah.regwatch.raw_store import RawStore, RawStoreError, circular_numbers
from tests.regwatch.conftest import FETCHED_AT, fixture

URL = "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=990001"


def page(body: bytes, content_type: str = "text/html; charset=utf-8") -> Fetched:
    """A fetched document."""
    return Fetched(
        url=URL,
        final_url=URL,
        status=200,
        content_type=content_type,
        body=body,
        fetched_at=FETCHED_AT,
    )


def test_circular_numbers_match_the_rbi_pattern() -> None:
    """``RBI/YYYY-YY/N`` and ``RBI/YYYY-YYYY/N``; distinct, in first-seen order."""
    text = "RBI/2099-2100/901 replaces RBI/2098-99/777; see RBI/2099-2100/901 again. RBI/99-00/1"
    assert circular_numbers(text) == ["RBI/2099-2100/901", "RBI/2098-99/777"]


def test_put_stores_bytes_hash_numbers_date_and_url(tmp_path: Path) -> None:
    """The record carries the SHA-256, URL, fetch time, circular numbers and the feed's date."""
    store = RawStore(tmp_path)
    body = fixture("circular_io_amendment.html")
    doc = store.put(page(body), title="Synthetic", published_on=date(2099, 1, 5))
    assert doc.sha256 == hashlib.sha256(body).hexdigest()
    assert doc.url == URL
    assert doc.size == len(body)
    assert doc.fetched_at == FETCHED_AT
    assert doc.published_on == date(2099, 1, 5)
    assert doc.circular_numbers == ["RBI/2099-2100/901", "RBI/2098-99/777"]
    assert store.read(doc.sha256) == body
    assert list(store.documents()) == [doc]


def test_pdf_numbers_come_from_the_feed_hint(tmp_path: Path) -> None:
    """A PDF body is not searched as text; the feed's description is."""
    doc = RawStore(tmp_path).put(
        page(b"%PDF-1.4 RBI/0000-00/0", "application/pdf"), hint="RBI/2099-2100/902 · synthetic"
    )
    assert doc.circular_numbers == ["RBI/2099-2100/902"]


def test_blobs_are_read_only_and_refetch_is_idempotent(tmp_path: Path) -> None:
    """Same URL and bytes: one record, one blob, mode 0444."""
    store = RawStore(tmp_path)
    first = store.put(page(b"<html>v1</html>"))
    again = store.put(page(b"<html>v1</html>"))
    assert again == first
    assert len(list(store.documents())) == 1
    mode = (tmp_path / "blobs" / first.sha256).stat().st_mode
    assert not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    assert [p.name for p in (tmp_path / "blobs").iterdir()] == [first.sha256]


def test_changed_bytes_add_a_version_and_keep_the_old(tmp_path: Path) -> None:
    """A page that changed is a new version; the first is still readable."""
    store = RawStore(tmp_path)
    v1 = store.put(page(b"<html>v1</html>"))
    v2 = store.put(page(b"<html>v2</html>"))
    assert store.versions(URL) == [v1, v2]
    assert store.read(v1.sha256) == b"<html>v1</html>"


def test_tampering_is_detected(tmp_path: Path) -> None:
    """An altered blob fails ``read`` and shows up in ``verify``."""
    store = RawStore(tmp_path)
    doc = store.put(page(b"<html>v1</html>"))
    assert store.verify() == []
    blob = tmp_path / "blobs" / doc.sha256
    blob.chmod(0o644)
    blob.write_bytes(b"<html>forged</html>")
    assert store.verify() == [doc.sha256]
    with pytest.raises(RawStoreError):
        store.read(doc.sha256)
    with pytest.raises(RawStoreError):
        store.put(page(b"<html>v1</html>").model_copy(update={"url": URL + "&x=1"}))


def test_the_store_has_no_delete() -> None:
    """Evidence is never deleted (CLAUDE.md hard rule 7)."""
    assert not [n for n in dir(RawStore) if any(w in n for w in ("delete", "remove", "purge"))]
