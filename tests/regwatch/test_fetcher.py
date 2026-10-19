"""The fetcher is polite: honest UA, robots.txt, rate limit, retries, and no bot-check bypass."""

import httpx
import pytest

from abhiyogah.regwatch.fetcher import (
    SOURCES,
    BotCheckError,
    FetchError,
    RobotsDisallowedError,
    parse_feed,
    user_agent,
)
from tests.regwatch.conftest import FETCHED_AT, FakeTime, Site, fetcher, fixture

BASE = "https://www.rbi.org.in"
FEED = f"{BASE}/notifications_rss.xml"
ROBOTS_OK = httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
RSS = httpx.Response(
    200, content=fixture("notifications_rss.xml"), headers={"content-type": "application/rss+xml"}
)


def test_user_agent_is_honest() -> None:
    """Product, version, purpose and contact; never a browser string."""
    agent = user_agent("mailto:regwatch@example.org")
    assert agent.startswith("AbhiyogahRegWatch/")
    assert "+mailto:regwatch@example.org" in agent
    assert "Mozilla" not in agent


def test_fetch_reads_robots_once_and_sends_our_agent() -> None:
    """robots.txt first, then the page; the UA is ours on every request."""
    site = Site({"/robots.txt": [ROBOTS_OK], "/notifications_rss.xml": [RSS]})
    f = fetcher(site, FakeTime())
    got = f.fetch(FEED)
    f.fetch(FEED)
    assert site.paths() == ["/robots.txt", "/notifications_rss.xml", "/notifications_rss.xml"]
    assert {r.headers["user-agent"] for r in site.seen} == {f.agent}
    assert got.status == 200
    assert got.fetched_at == FETCHED_AT
    assert got.body == fixture("notifications_rss.xml")


def test_rate_limit_spaces_requests_per_host() -> None:
    """Back-to-back requests to one host wait out ``min_interval``."""
    site = Site({"/robots.txt": [ROBOTS_OK], "/notifications_rss.xml": [RSS]})
    clock = FakeTime()
    f = fetcher(site, clock, min_interval=10.0)
    f.fetch(FEED)
    f.fetch(FEED)
    assert clock.sleeps == [10.0, 10.0]


def test_crawl_delay_longer_than_ours_is_obeyed() -> None:
    """A robots.txt Crawl-delay above ``min_interval`` wins."""
    robots = httpx.Response(200, text="User-agent: *\nCrawl-delay: 30\n")
    site = Site({"/robots.txt": [robots], "/notifications_rss.xml": [RSS]})
    clock = FakeTime()
    fetcher(site, clock, min_interval=10.0).fetch(FEED)
    assert clock.sleeps == [30.0]


def test_robots_disallow_is_obeyed() -> None:
    """A disallowed path is never requested."""
    site = Site({"/robots.txt": [ROBOTS_OK]})
    with pytest.raises(RobotsDisallowedError):
        fetcher(site, FakeTime()).fetch(f"{BASE}/private/x.pdf")
    assert site.paths() == ["/robots.txt"]


def test_missing_robots_allows_but_a_broken_one_stops() -> None:
    """404 robots.txt: no rules. 403 robots.txt: do not assume permission."""
    site = Site({"/notifications_rss.xml": [RSS]})
    assert fetcher(site, FakeTime()).fetch(FEED).status == 200
    blocked = Site({"/robots.txt": [httpx.Response(403, text="no")]})
    with pytest.raises(FetchError, match="not assuming permission"):
        fetcher(blocked, FakeTime()).fetch(FEED)
    assert blocked.paths() == ["/robots.txt"]


def test_server_errors_are_retried_with_backoff_and_retry_after() -> None:
    """503 then 429 (Retry-After 60) then 200: backoff 5 s, then max(10, 60) s."""
    site = Site(
        {
            "/robots.txt": [ROBOTS_OK],
            "/notifications_rss.xml": [
                httpx.Response(503, text="busy"),
                httpx.Response(429, headers={"retry-after": "60"}),
                RSS,
            ],
        }
    )
    clock = FakeTime()
    f = fetcher(site, clock, min_interval=1.0, base_backoff=5.0)
    assert f.fetch(FEED).status == 200
    assert clock.sleeps == [1.0, 5.0, 60.0]


def test_retries_are_bounded() -> None:
    """Persistent 500s give up after ``max_retries``."""
    site = Site({"/robots.txt": [ROBOTS_OK], "/notifications_rss.xml": [httpx.Response(500)]})
    with pytest.raises(FetchError, match="after 3 attempts"):
        fetcher(site, FakeTime(), max_retries=2).fetch(FEED)
    assert site.paths().count("/notifications_rss.xml") == 3


def test_network_errors_are_retried() -> None:
    """A dropped connection is retried, then succeeds."""
    calls = {"n": 0}
    site = Site({"/robots.txt": [ROBOTS_OK], "/notifications_rss.xml": [RSS]})

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/notifications_rss.xml" and calls["n"] == 0:
            calls["n"] += 1
            raise httpx.ConnectError("reset", request=request)
        return site(request)

    f = fetcher(site, FakeTime())
    f.client = httpx.Client(transport=httpx.MockTransport(flaky))
    assert f.fetch(FEED).status == 200


@pytest.mark.parametrize("status", [200, 403, 503])
def test_bot_checks_stop_at_once(status: int) -> None:
    """A challenge page raises BotCheckError with no retry and no second attempt."""
    page = httpx.Response(
        status, content=fixture("bot_check.html"), headers={"content-type": "text/html"}
    )
    site = Site({"/robots.txt": [ROBOTS_OK], "/notifications_rss.xml": [page]})
    clock = FakeTime()
    with pytest.raises(BotCheckError):
        fetcher(site, clock).fetch(FEED)
    assert site.paths().count("/notifications_rss.xml") == 1
    assert clock.sleeps == [10.0]  # only the rate-limit wait after robots.txt


def test_challenge_header_is_a_bot_check() -> None:
    """``cf-mitigated`` marks a challenge whatever the body."""
    page = httpx.Response(403, text="", headers={"cf-mitigated": "challenge"})
    site = Site({"/robots.txt": [ROBOTS_OK], "/notifications_rss.xml": [page]})
    with pytest.raises(BotCheckError):
        fetcher(site, FakeTime()).fetch(FEED)


def test_other_client_errors_are_not_retried() -> None:
    """A plain 404 fails once."""
    site = Site({"/robots.txt": [ROBOTS_OK]})
    with pytest.raises(FetchError, match="HTTP 404"):
        fetcher(site, FakeTime()).fetch(f"{BASE}/gone.pdf")
    assert site.paths() == ["/robots.txt", "/gone.pdf"]


def test_parse_feed_reads_items_in_order() -> None:
    """Title, link, timezone-aware date and description; a bad date is None, not a guess."""
    items = parse_feed(fixture("notifications_rss.xml"))
    assert [i.link.rsplit("=", 1)[1] for i in items] == ["990001", "990002", "990003"]
    first = items[0]
    assert first.published is not None
    assert first.published.utcoffset() is not None
    assert first.published.isoformat() == "2099-01-05T18:30:00+05:30"
    assert "RBI/2099-2100/901" in first.description
    assert items[2].published is None


def test_parse_feed_refuses_entities() -> None:
    """A DOCTYPE or entity declaration is refused before parsing."""
    hostile = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "y">]><rss><channel/></rss>'
    with pytest.raises(FetchError, match="DOCTYPE"):
        parse_feed(hostile)


def test_sources_are_rbi_and_flagged_unverified() -> None:
    """Every source is on rbi.org.in over HTTPS and not yet confirmed live."""
    assert {s.url.split("/")[2] for s in SOURCES} == {"www.rbi.org.in"}
    assert all(s.url.startswith("https://") and not s.verified for s in SOURCES)
    assert {s.feed for s in SOURCES} == {True, False}
