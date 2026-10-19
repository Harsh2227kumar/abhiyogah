"""The engine's MCP tools, as plain async functions over the platform API.

Every tool is one or more ``GET`` calls to the REST API (``abhiyogah.api``), so the MCP server has
no logic path of its own: authentication, roles, ``as_of`` time travel, evaluation and errors are
the API's. The API has no service layer separate from its routes yet (see the Requests in
``tasks/07-mcp-regwatch.md``), so the tools call the routes, either in-process over ASGI or over
HTTP to a running API.

The tools are read-only: the client refuses any method but ``GET`` before it reaches the API.
"""

from datetime import datetime
from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter

from abhiyogah.api.schemas import ComplaintDetail, DeadlineItem, Explanation
from abhiyogah.domain.decision import DecisionRecord
from abhiyogah.evaluator.determinations import DETERMINATIONS, reply_content
from abhiyogah.registry.schema import Obligation

__all__ = [
    "REPLY_CHECKS",
    "EngineTools",
    "ReadOnlyError",
    "ReplyCheck",
    "ToolCallError",
]

REPLY_CHECKS = frozenset(o for o, d in DETERMINATIONS.items() if d is reply_content)
"""Obligations the evaluator checks with its reply-content determination (A18)."""

_OBLIGATIONS = TypeAdapter(list[Obligation])


class ToolCallError(Exception):
    """The API refused or failed a tool's call; ``status`` and ``detail`` are the API's."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"API {status}: {detail}")
        self.status = status
        self.detail = detail


class ReadOnlyError(Exception):
    """A tool tried a method other than GET."""


class ReplyCheck(BaseModel):
    """The engine's reply-content checks (A18) on one complaint, as evaluated at ``as_of``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    complaint_id: str
    as_of: datetime
    checks: list[DecisionRecord]


async def _only_get(request: httpx.Request) -> None:
    """Refuse every method but GET, before it is sent."""
    if request.method != "GET":
        raise ReadOnlyError(f"MCP tools are read-only; refused {request.method} {request.url.path}")


def _detail(response: httpx.Response) -> str:
    """The API's ``detail`` message, or the raw body."""
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return response.text


class EngineTools:
    """The MCP tools, each a read of the platform API through ``client``."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        hooks = client.event_hooks
        if _only_get not in hooks["request"]:
            client.event_hooks = {**hooks, "request": [_only_get, *hooks["request"]]}

    @classmethod
    def over(cls, transport: httpx.AsyncBaseTransport, api_key: str, base_url: str) -> Self:
        """Tools over ``transport`` (ASGI in-process, or HTTP) authenticating with ``api_key``."""
        return cls(
            httpx.AsyncClient(
                transport=transport, base_url=base_url, headers={"X-API-Key": api_key}
            )
        )

    async def __aenter__(self) -> Self:
        """Enter the client's context."""
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the client."""
        await self._client.__aexit__(exc_type, exc, tb)

    async def _get(self, path: str, as_of: datetime | None = None) -> httpx.Response:
        """GET ``path``; non-2xx raises ``ToolCallError``."""
        params = {"as_of": as_of.isoformat()} if as_of is not None else None
        response = await self._client.get(path, params=params)
        if response.is_error:
            raise ToolCallError(response.status_code, _detail(response))
        return response

    async def evaluate_complaint(
        self, complaint_id: str, as_of: datetime | None = None
    ) -> ComplaintDetail:
        """Facts, decisions, deadlines, breaches and required actions for one complaint."""
        response = await self._get(f"/complaints/{complaint_id}", as_of)
        return ComplaintDetail.model_validate_json(response.content)

    async def get_deadlines(
        self, complaint_id: str, as_of: datetime | None = None
    ) -> list[DeadlineItem]:
        """The complaint's computed deadlines, soonest first."""
        return list((await self.evaluate_complaint(complaint_id, as_of)).deadlines)

    async def explain_decision(self, decision_id: str) -> Explanation:
        """A stored decision (by its hash) rendered as text from the record itself."""
        response = await self._get(f"/decisions/{decision_id}/explain")
        return Explanation.model_validate_json(response.content)

    async def check_reply(self, complaint_id: str, as_of: datetime | None = None) -> ReplyCheck:
        """The engine's checks that the sent final reply carries every required element (A18).

        This reads the evaluator's decision on the reply as recorded (``reply_elements``); it does
        not read a draft. Each check is ``DETERMINED`` with ``reply_complete`` and
        ``missing_elements``, or ``INSUFFICIENT_FACTS`` while the reply's elements are unrecorded.
        """
        detail = await self.evaluate_complaint(complaint_id, as_of)
        return ReplyCheck(
            complaint_id=detail.complaint_id,
            as_of=detail.as_of,
            checks=[r for r in detail.decisions if r.obligation_id in REPLY_CHECKS],
        )

    async def list_obligations(self) -> list[Obligation]:
        """Every obligation in the loaded rule pack."""
        response = await self._get("/obligations")
        return _OBLIGATIONS.validate_json(response.content)
