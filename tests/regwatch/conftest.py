"""Offline helpers: saved fixtures, a scripted transport and a fake clock."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from abhiyogah.regwatch.fetcher import Fetcher

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "regwatch" / "fixtures"
FETCHED_AT = datetime(2099, 1, 7, 4, 30, tzinfo=UTC)

Handler = Callable[[httpx.Request], httpx.Response]


def fixture(name: str) -> bytes:
    """A saved fixture's bytes."""
    return (FIXTURES / name).read_bytes()


@dataclass
class FakeTime:
    """A monotonic clock that only moves when something sleeps."""

    t: float = 1000.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        """Now."""
        return self.t

    def sleep(self, seconds: float) -> None:
        """Record the sleep and advance."""
        self.sleeps.append(seconds)
        self.t += seconds


@dataclass
class Site:
    """A scripted site: path -> responses (the last repeats); every request is logged."""

    routes: dict[str, list[httpx.Response]]
    seen: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer from the script; 404 for unknown paths."""
        self.seen.append(request)
        key = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        script = self.routes.get(key)
        if not script:
            return httpx.Response(404)
        return script.pop(0) if len(script) > 1 else script[0]

    def paths(self) -> list[str]:
        """Paths requested, in order."""
        return [r.url.path for r in self.seen]


def fetcher(site: Site, clock: FakeTime, **kw: float | int | str) -> Fetcher:
    """A fetcher over ``site`` with fake time."""
    return Fetcher(
        client=httpx.Client(transport=httpx.MockTransport(site)),
        now=lambda: FETCHED_AT,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        contact="mailto:regwatch@example.org",
        **kw,  # type: ignore[arg-type]
    )
