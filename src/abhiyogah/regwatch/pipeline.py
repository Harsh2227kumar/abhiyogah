"""One Regulatory Watch pass over a feed: fetch, store, extract, classify, link, draft.

``watch_feed`` reads an RSS source, fetches each linked document politely, keeps it in the raw
store, and for every document that is new (or changed) and relevant writes proposals for human
review. A bot check stops the pass at once (the site is asking us to stop); other fetch errors are
reported per item and the pass continues.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from abhiyogah.registry.schema import Obligation
from abhiyogah.regwatch.drafts import draft_proposals, write_proposals
from abhiyogah.regwatch.extract import ExtractionError, extract
from abhiyogah.regwatch.fetcher import BotCheckError, Fetcher, FetchError, Source, parse_feed
from abhiyogah.regwatch.impact import link_impacts
from abhiyogah.regwatch.raw_store import RawStore
from abhiyogah.regwatch.relevance import TopicSuggester, classify

__all__ = ["ItemOutcome", "WatchReport", "watch_feed"]


class ItemOutcome(BaseModel):
    """What happened to one feed item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    link: str
    status: str
    """``UNCHANGED``, ``NOT_RELEVANT``, ``PROPOSED``, ``FETCH_FAILED`` or ``EXTRACT_FAILED``."""
    sha256: str | None = None
    proposal_dir: str | None = None
    detail: str = ""


class WatchReport(BaseModel):
    """One pass over one source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    items: list[ItemOutcome]
    stopped: str | None = None
    """Set when a bot check stopped the pass."""


def watch_feed(
    source: Source,
    fetcher: Fetcher,
    store: RawStore,
    obligations: Sequence[Obligation],
    proposals_dir: Path,
    today: date,
    suggester: TopicSuggester | None = None,
) -> WatchReport:
    """Run one pass over ``source`` (an RSS feed); see the module docstring."""
    try:
        feed = fetcher.fetch(source.url)
    except BotCheckError as exc:
        return WatchReport(source=source.key, items=[], stopped=str(exc))
    store.put(feed, title=source.key)
    known = {(d.sha256, d.url) for d in store.documents()}
    outcomes: list[ItemOutcome] = []
    for item in parse_feed(feed.body):
        try:
            fetched = fetcher.fetch(item.link)
        except BotCheckError as exc:
            return WatchReport(source=source.key, items=outcomes, stopped=str(exc))
        except FetchError as exc:
            outcomes.append(ItemOutcome(link=item.link, status="FETCH_FAILED", detail=str(exc)))
            continue
        published = item.published.date() if item.published else None
        doc = store.put(fetched, title=item.title, published_on=published, hint=item.description)
        if (doc.sha256, doc.url) in known:
            outcomes.append(ItemOutcome(link=item.link, status="UNCHANGED", sha256=doc.sha256))
            continue
        known.add((doc.sha256, doc.url))
        try:
            text = extract(doc, store.read(doc.sha256))
        except ExtractionError as exc:
            outcomes.append(
                ItemOutcome(
                    link=item.link, status="EXTRACT_FAILED", sha256=doc.sha256, detail=str(exc)
                )
            )
            continue
        relevance = classify(text, suggester)
        if not relevance.relevant:
            outcomes.append(ItemOutcome(link=item.link, status="NOT_RELEVANT", sha256=doc.sha256))
            continue
        links = link_impacts(text, obligations)
        proposals = draft_proposals(doc, text, relevance, links, list(obligations))
        out = write_proposals(proposals, proposals_dir, today)
        outcomes.append(
            ItemOutcome(
                link=item.link,
                status="PROPOSED",
                sha256=doc.sha256,
                proposal_dir=str(out),
                detail=f"{len(proposals.proposals)} obligation(s) to review",
            )
        )
    return WatchReport(source=source.key, items=outcomes)
