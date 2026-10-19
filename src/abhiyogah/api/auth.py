"""Role-based API-key authentication (v0; OIDC later).

Every route except ``/health`` needs an ``X-API-Key`` header. Each key belongs to a principal with
one role; roles are ordered, so a higher role can do everything a lower one can:

- ``READER``: read complaints, decisions, obligations, the board and review tasks.
- ``WRITER``: also post business events and perception findings.
- ``ADMIN``: also read ``as_of`` other than now (time travel).

Keys are configured as ``ABHIYOGAH_API_KEYS="<actor>:<role>:<key>;..."`` and compared in constant
time. Only the SHA-256 of a key is kept in memory after start-up. Keys are never logged.
"""

import hashlib
import hmac
from collections.abc import Callable, Iterable
from enum import IntEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApiKeyring",
    "Principal",
    "Role",
    "current_principal",
    "parse_api_keys",
    "require",
]


class Role(IntEnum):
    """Ordered roles: each includes the ones below it."""

    READER = 1
    WRITER = 2
    ADMIN = 3


class Principal(BaseModel):
    """The authenticated caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: str = Field(min_length=1)
    role: Role


def _digest(key: str) -> bytes:
    """SHA-256 of a key."""
    return hashlib.sha256(key.encode("utf-8")).digest()


class ApiKeyring:
    """Known keys, held as digests."""

    def __init__(self, entries: Iterable[tuple[str, Principal]]) -> None:
        """``entries`` are ``(key, principal)`` pairs."""
        self._entries = [(_digest(key), principal) for key, principal in entries]

    def lookup(self, key: str) -> Principal | None:
        """The principal for ``key``, comparing every entry in constant time."""
        digest = _digest(key)
        found: Principal | None = None
        for known, principal in self._entries:
            if hmac.compare_digest(known, digest):
                found = principal
        return found


def parse_api_keys(spec: str) -> ApiKeyring:
    """Parse ``"<actor>:<role>:<key>;..."``; blank entries are ignored."""
    entries: list[tuple[str, Principal]] = []
    for raw in spec.split(";"):
        item = raw.strip()
        if not item:
            continue
        parts = item.split(":", 2)
        if len(parts) != 3 or not all(parts):
            raise ValueError("each API key entry must be '<actor>:<role>:<key>'")
        actor, role, key = parts
        try:
            parsed = Role[role.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown role {role!r}") from exc
        if len(key) < 16:
            raise ValueError(f"API key for {actor!r} is shorter than 16 characters")
        entries.append((key, Principal(actor_id=actor, role=parsed)))
    return ApiKeyring(entries)


_api_key = APIKeyHeader(name="X-API-Key", auto_error=False)


def current_principal(request: Request, key: Annotated[str | None, Depends(_api_key)]) -> Principal:
    """The caller behind ``X-API-Key``; 401 if missing or unknown."""
    keyring: ApiKeyring = request.app.state.keyring
    principal = keyring.lookup(key) if key else None
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or unknown API key",
            headers={"WWW-Authenticate": "APIKey"},
        )
    return principal


def require(role: Role) -> Callable[[Principal], Principal]:
    """A dependency that admits callers with at least ``role``; 403 otherwise."""

    def check(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        """Admit or refuse."""
        if principal.role < role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"needs role {role.name}",
            )
        return principal

    return check
