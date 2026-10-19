"""One offline Regulatory Watch pass, end to end, over saved fixtures."""

import socket
from datetime import date
from pathlib import Path

import httpx
import pytest

from abhiyogah.domain.enums import RuleStatus
from abhiyogah.regwatch.fetcher import SOURCES
from abhiyogah.regwatch.pipeline import watch_feed
from abhiyogah.regwatch.raw_store import RawStore
from tests.regwatch.conftest import FakeTime, Site, fetcher, fixture
from tests.regwatch.test_impact import ALL

FEED = next(s for s in SOURCES if s.key == "notifications-rss")
TODAY = date(2099, 1, 7)
HTML = {"content-type": "text/html; charset=utf-8"}
ITEM = "/Scripts/NotificationUser.aspx?Id="


def site(*, bot_on_second: bool = False) -> Site:
    """robots.txt, the feed, two notifications; the third item is gone (404)."""
    second = (
        httpx.Response(
            200, content=fixture("bot_check.html"), headers={"content-type": "text/html"}
        )
        if bot_on_second
        else httpx.Response(200, content=fixture("notification_unrelated.html"), headers=HTML)
    )
    return Site(
        {
            "/robots.txt": [httpx.Response(200, text="User-agent: *\nAllow: /\n")],
            "/notifications_rss.xml": [
                httpx.Response(
                    200,
                    content=fixture("notifications_rss.xml"),
                    headers={"content-type": "application/rss+xml"},
                )
            ],
            f"{ITEM}990001": [
                httpx.Response(200, content=fixture("circular_io_amendment.html"), headers=HTML)
            ],
            f"{ITEM}990002": [second],
        }
    )


def test_one_pass_proposes_for_the_relevant_notification_only(tmp_path: Path) -> None:
    """IO amendment: proposals. Currency chests: not relevant. Missing item: reported."""
    store = RawStore(tmp_path / "raw")
    report = watch_feed(
        FEED, fetcher(site(), FakeTime()), store, ALL, tmp_path / "proposals", TODAY
    )
    assert report.stopped is None
    assert [i.status for i in report.items] == ["PROPOSED", "NOT_RELEVANT", "FETCH_FAILED"]
    out = Path(report.items[0].proposal_dir or "")
    assert (out / "summary.md").is_file()
    proposal = (out / "IO-CB-2026-14-1-b.yaml").read_text(encoding="utf-8")
    assert f"status: {RuleStatus.DRAFT.value}" in proposal
    stored = {d.url.rsplit("=", 1)[-1] for d in store.documents()}
    assert stored == {"https://www.rbi.org.in/notifications_rss.xml", "990001", "990002"}
    first = next(d for d in store.documents() if d.url.endswith("990001"))
    assert first.published_on == date(2099, 1, 5)
    assert first.circular_numbers[0] == "RBI/2099-2100/901"


def test_a_second_pass_finds_nothing_new(tmp_path: Path) -> None:
    """Same bytes: UNCHANGED, and no second proposal directory."""
    store = RawStore(tmp_path / "raw")
    watch_feed(FEED, fetcher(site(), FakeTime()), store, ALL, tmp_path / "proposals", TODAY)
    again = watch_feed(FEED, fetcher(site(), FakeTime()), store, ALL, tmp_path / "proposals", TODAY)
    assert [i.status for i in again.items] == ["UNCHANGED", "UNCHANGED", "FETCH_FAILED"]
    assert len(list((tmp_path / "proposals").iterdir())) == 1


def test_a_bot_check_stops_the_pass(tmp_path: Path) -> None:
    """After a challenge page nothing more is requested."""
    s = site(bot_on_second=True)
    report = watch_feed(
        FEED, fetcher(s, FakeTime()), RawStore(tmp_path / "raw"), ALL, tmp_path / "p", TODAY
    )
    assert report.stopped is not None
    assert [i.status for i in report.items] == ["PROPOSED"]
    assert s.seen[-1].url.query == b"Id=990002"


def test_the_network_guard_is_on() -> None:
    """A real connection attempt fails inside these tests."""
    with pytest.raises(AssertionError, match="network"):
        socket.create_connection(("www.rbi.org.in", 443), timeout=1)
