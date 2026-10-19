"""A polite fetcher for RBI pages, PDFs and RSS feeds.

Polite means:

- **Honest user agent.** Every request says who is asking and how to reach them
  (``ABHIYOGAH_REGWATCH_CONTACT``); it never imitates a browser.
- **robots.txt.** Each host's ``robots.txt`` is read once (through the same rate limit) and obeyed,
  including ``Crawl-delay`` when it is longer than ours. An unreadable ``robots.txt`` (other than
  404) stops the fetch rather than assuming permission.
- **Rate limit.** At most one request per host every ``min_interval`` seconds.
- **Retries.** Network errors, 429 and 5xx are retried a few times with exponential backoff, and a
  ``Retry-After`` header is honoured (capped at ``max_backoff``).
- **Bot checks are not circumvented.** A challenge page (CAPTCHA, JS check, WAF block) raises
  ``BotCheckError`` at once: no retry, no other user agent, no headless browser. A human decides.

Time is injected (``monotonic``, ``sleep``) so tests never wait. ``SOURCES`` lists the RBI pages
and feeds to watch; their URLs are configuration, not regulation.
"""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict

__all__ = [
    "DEFAULT_CONTACT",
    "SOURCES",
    "BotCheckError",
    "FeedItem",
    "FetchError",
    "Fetched",
    "Fetcher",
    "RobotsDisallowedError",
    "Source",
    "SourceKind",
    "parse_feed",
    "user_agent",
]

DEFAULT_CONTACT = "https://github.com/Harsh2227kumar/abhiyogah"
"""Where a site operator can reach us when ``ABHIYOGAH_REGWATCH_CONTACT`` is unset."""

VERSION = "0.1"

MAX_BODY_BYTES = 50 * 1024 * 1024
"""Bodies larger than this are refused (RBI PDFs are a few MB)."""

_BOT_MARKERS = (
    "captcha",
    "cf-chl-",
    "challenge-platform",
    "checking your browser",
    "access denied",
    "request rejected",
    "are you a robot",
    "enable javascript and cookies",
)
"""Lower-case phrases that mark a challenge or WAF block page."""


class SourceKind(StrEnum):
    """What a source publishes."""

    NOTIFICATION = "NOTIFICATION"
    MASTER_DIRECTION = "MASTER_DIRECTION"
    PRESS_RELEASE = "PRESS_RELEASE"


@dataclass(frozen=True)
class Source:
    """One RBI listing or feed to watch."""

    key: str
    url: str
    kind: SourceKind
    feed: bool
    verified: bool = False
    """False until the URL has been confirmed by a live, polite fetch."""


SOURCES: tuple[Source, ...] = (
    Source(
        "notifications-rss",
        "https://www.rbi.org.in/notifications_rss.xml",
        SourceKind.NOTIFICATION,
        True,
    ),
    Source(
        "press-releases-rss",
        "https://www.rbi.org.in/pressreleases_rss.xml",
        SourceKind.PRESS_RELEASE,
        True,
    ),
    Source(
        "notifications",
        "https://www.rbi.org.in/Scripts/NotificationUser.aspx",
        SourceKind.NOTIFICATION,
        False,
    ),
    Source(
        "master-directions",
        "https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx",
        SourceKind.MASTER_DIRECTION,
        False,
    ),
    Source(
        "press-releases",
        "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
        SourceKind.PRESS_RELEASE,
        False,
    ),
)
"""RBI sources. Unverified: the cloud sandbox cannot reach rbi.org.in; confirm on a live run."""


class FetchError(Exception):
    """A fetch failed after its retries, or was refused."""


class BotCheckError(FetchError):
    """The site answered with a bot check; a human must decide what to do."""


class RobotsDisallowedError(FetchError):
    """robots.txt disallows the URL for our user agent."""


class Fetched(BaseModel):
    """One fetched document, as received."""

    model_config = ConfigDict(frozen=True)

    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: AwareDatetime


class FeedItem(BaseModel):
    """One RSS ``<item>``."""

    model_config = ConfigDict(frozen=True)

    title: str
    link: str
    published: AwareDatetime | None = None
    description: str = ""


def user_agent(contact: str | None = None) -> str:
    """The honest user agent: product, version, purpose and contact."""
    who = contact or os.environ.get("ABHIYOGAH_REGWATCH_CONTACT") or DEFAULT_CONTACT
    return f"AbhiyogahRegWatch/{VERSION} (regulatory-change monitoring; +{who})"


def _looks_like_bot_check(response: httpx.Response) -> bool:
    """A challenge or WAF page: a challenge header, or a short HTML page with a marker phrase."""
    if "cf-mitigated" in response.headers or response.headers.get("x-amzn-waf-action"):
        return True
    if response.status_code not in (200, 403, 429, 503):
        return False
    if "html" not in response.headers.get("content-type", ""):
        return False
    text = response.content[:20_000].decode("utf-8", errors="replace").lower()
    return any(m in text for m in _BOT_MARKERS)


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds from a ``Retry-After`` header (delta or HTTP date), if present and parseable."""
    value = response.headers.get("retry-after")
    if value is None:
        return None
    if value.strip().isdigit():
        return float(value.strip())
    try:
        when = parsedate_to_datetime(value)
        date = (
            parsedate_to_datetime(response.headers["date"]) if "date" in response.headers else None
        )
    except (TypeError, ValueError, KeyError):
        return None
    if date is None:
        return None
    return max(0.0, (when - date).total_seconds())


@dataclass
class Fetcher:
    """Fetches URLs politely; see the module docstring."""

    client: httpx.Client
    now: Callable[[], datetime]
    min_interval: float = 10.0
    max_retries: int = 3
    base_backoff: float = 5.0
    max_backoff: float = 300.0
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    contact: str | None = None
    _last: dict[str, float] = field(default_factory=dict)
    _robots: dict[str, RobotFileParser | None] = field(default_factory=dict)
    _delay: dict[str, float] = field(default_factory=dict)

    @property
    def agent(self) -> str:
        """The user agent sent with every request."""
        return user_agent(self.contact)

    def _wait_turn(self, host: str) -> None:
        """Sleep until ``host``'s interval since our last request has passed."""
        interval = max(self.min_interval, self._delay.get(host, 0.0))
        last = self._last.get(host)
        if last is not None:
            gap = self.monotonic() - last
            if gap < interval:
                self.sleep(interval - gap)
        self._last[host] = self.monotonic()

    def _send(self, url: str) -> httpx.Response:
        """One rate-limited GET with our user agent; size-capped."""
        host = urlsplit(url).netloc
        self._wait_turn(host)
        response = self.client.get(url, headers={"User-Agent": self.agent}, follow_redirects=True)
        if len(response.content) > MAX_BODY_BYTES:
            raise FetchError(f"{url}: body over {MAX_BODY_BYTES} bytes")
        return response

    def _robots_for(self, url: str) -> RobotFileParser | None:
        """The host's parsed robots.txt; None if it has none (404/410)."""
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            robots_url = f"{parts.scheme}://{host}/robots.txt"
            response = self._with_retries(robots_url)
            if response.status_code in (404, 410):
                self._robots[host] = None
            elif response.is_success:
                parser = RobotFileParser(robots_url)
                parser.parse(response.text.splitlines())
                self._robots[host] = parser
                delay = parser.crawl_delay(self.agent)
                if delay is not None:
                    self._delay[host] = float(delay)
            else:
                raise FetchError(
                    f"{robots_url}: HTTP {response.status_code}; not assuming permission"
                )
        return self._robots[host]

    def _with_retries(self, url: str) -> httpx.Response:
        """GET with retries on network errors, 429 and 5xx; bot checks raise at once."""
        attempt = 0
        while True:
            try:
                response = self._send(url)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise FetchError(f"{url}: {exc!r} after {attempt + 1} attempts") from exc
                self.sleep(min(self.max_backoff, self.base_backoff * 2**attempt))
                attempt += 1
                continue
            if _looks_like_bot_check(response):
                raise BotCheckError(
                    f"{url}: HTTP {response.status_code} looks like a bot check; not retrying"
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.max_retries:
                    raise FetchError(
                        f"{url}: HTTP {response.status_code} after {attempt + 1} attempts"
                    )
                wait = _retry_after(response)
                backoff = self.base_backoff * 2**attempt
                self.sleep(min(self.max_backoff, max(backoff, wait or 0.0)))
                attempt += 1
                continue
            return response

    def fetch(self, url: str) -> Fetched:
        """Fetch ``url`` if robots.txt allows it; non-2xx after retries raises ``FetchError``."""
        robots = self._robots_for(url)
        if robots is not None and not robots.can_fetch(self.agent, url):
            raise RobotsDisallowedError(f"{url}: disallowed by robots.txt")
        response = self._with_retries(url)
        if not response.is_success:
            raise FetchError(f"{url}: HTTP {response.status_code}")
        return Fetched(
            url=url,
            final_url=str(response.url),
            status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            body=response.content,
            fetched_at=self.now(),
        )


def _text(item: ET.Element, tag: str) -> str:
    """The stripped text of ``item``'s child ``tag``, or ''."""
    child = item.find(tag)
    return (child.text or "").strip() if child is not None else ""


def parse_feed(body: bytes) -> list[FeedItem]:
    """The ``<item>``s of an RSS 2.0 feed, in feed order.

    ElementTree on Python 3.12 does not resolve external entities, and DOCTYPEs are refused here, so
    a hostile feed cannot pull in files or expand entities.
    """
    upper = body.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise FetchError("feed declares a DOCTYPE or entity; refusing to parse")
    root = ET.fromstring(body)  # noqa: S314 - no DOCTYPE, no external entities (see docstring)
    items: list[FeedItem] = []
    for item in root.iter("item"):
        raw = _text(item, "pubDate")
        try:
            published = parsedate_to_datetime(raw) if raw else None
        except (TypeError, ValueError):
            published = None
        if published is not None and published.tzinfo is None:
            published = None
        items.append(
            FeedItem(
                title=_text(item, "title"),
                link=_text(item, "link"),
                published=published,
                description=_text(item, "description"),
            )
        )
    return items
