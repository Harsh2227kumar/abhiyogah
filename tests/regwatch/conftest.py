"""Offline helpers: a no-network guard, saved fixtures, a scripted transport and a fake clock."""

import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from abhiyogah.regwatch.fetcher import Fetcher

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "regwatch" / "fixtures"
FETCHED_AT = datetime(2099, 1, 7, 4, 30, tzinfo=UTC)


LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_loopback(address: object) -> bool:
    """Whether a socket address points at this machine (no network is involved)."""
    return isinstance(address, tuple) and bool(address) and address[0] in LOOPBACK


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regulatory Watch tests are offline: any non-loopback socket connection fails the test.

    Loopback stays open because asyncio on Windows builds its event loop's self-pipe from a
    127.0.0.1 socket pair (``socket.socketpair`` has no AF_UNIX fallback there).
    """
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    create_connection = socket.create_connection

    def refuse() -> AssertionError:
        return AssertionError("Regulatory Watch tests must not open network connections")

    def guarded_connect(self: socket.socket, address: object) -> None:
        if not _is_loopback(address):
            raise refuse()
        connect(self, address)  # type: ignore[arg-type]

    def guarded_connect_ex(self: socket.socket, address: object) -> int:
        if not _is_loopback(address):
            raise refuse()
        return connect_ex(self, address)  # type: ignore[arg-type]

    def guarded_create_connection(address: object, *args: object, **kwargs: object) -> object:
        if not _is_loopback(address):
            raise refuse()
        return create_connection(address, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)


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
