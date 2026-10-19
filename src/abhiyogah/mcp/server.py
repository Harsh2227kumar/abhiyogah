"""The MCP server: registers ``EngineTools`` with the official MCP Python SDK (``mcp>=2``).

Configuration (environment):

- ``ABHIYOGAH_MCP_API_KEY``: the API key the tools present; its role is the agent's role. Use a
  READER key; an ADMIN key also allows ``as_of`` time travel.
- ``ABHIYOGAH_API_URL``: base URL of a running API. Unset: the API is built in-process
  (``abhiyogah.api.app.create_app``, configured from the same environment) and called over ASGI.

Run over stdio with ``python -m abhiyogah.mcp.server``.

The SDK is not a project dependency yet (see the Requests in ``tasks/07-mcp-regwatch.md``), so it
is imported when the server is built, and ``McpUnavailableError`` says how to get it.
"""

import importlib
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import httpx

from abhiyogah.api.schemas import ComplaintDetail, DeadlineItem, Explanation
from abhiyogah.mcp.tools import EngineTools, ReadOnlyError, ReplyCheck, ToolCallError
from abhiyogah.registry.schema import Obligation

__all__ = ["McpUnavailableError", "build_server", "main", "tools_from_env"]

SERVER_NAME = "abhiyogah"
INSTRUCTIONS = (
    "RBI complaint-compliance engine. Every result is the engine's deterministic, clause-cited "
    "decision; quote clauses and dates from the result rather than restating the law. "
    "Tools are read-only."
)


class McpUnavailableError(Exception):
    """The MCP Python SDK (``mcp>=2``) is not installed."""


def tools_from_env(env: Mapping[str, str] = os.environ) -> EngineTools:
    """Tools over a running API (``ABHIYOGAH_API_URL``) or an in-process one."""
    key = env.get("ABHIYOGAH_MCP_API_KEY", "")
    url = env.get("ABHIYOGAH_API_URL")
    if url:
        return EngineTools.over(httpx.AsyncHTTPTransport(retries=1), key, url)
    from abhiyogah.api.app import create_app
    from abhiyogah.api.settings import Settings

    app = create_app(settings=Settings.from_env(env))
    return EngineTools.over(httpx.ASGITransport(app=app), key, "http://abhiyogah.internal")


def _sdk() -> Any:
    """The SDK's server class, tool annotations and ``ToolError``; else ``McpUnavailableError``."""
    try:
        server = importlib.import_module("mcp.server.mcpserver")
        errors = importlib.import_module("mcp.server.mcpserver.exceptions")
        types = importlib.import_module("mcp.types")
    except ModuleNotFoundError as exc:
        raise McpUnavailableError(
            "the MCP server needs the MCP Python SDK: uv pip install 'mcp>=2.2,<3'"
        ) from exc
    return server.MCPServer, types.ToolAnnotations, errors.ToolError


@contextmanager
def _reported(tool_error: type[Exception]) -> Iterator[None]:
    """Turn an API refusal into the SDK's ``ToolError``, so the agent reads the API's message."""
    try:
        yield
    except (ToolCallError, ReadOnlyError) as exc:
        raise tool_error(str(exc)) from exc


def build_server(tools: EngineTools) -> Any:
    """An ``MCPServer`` whose five tools call ``tools``; every tool is annotated read-only."""
    server_cls, annotations_cls, tool_error = _sdk()
    server = server_cls(name=SERVER_NAME, instructions=INSTRUCTIONS)
    read_only = annotations_cls(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )

    async def evaluate_complaint(
        complaint_id: str, as_of: datetime | None = None
    ) -> ComplaintDetail:
        """Evaluate a complaint: facts, clause-cited decisions, deadlines, breaches, actions.

        ``as_of`` (ISO 8601 with offset) evaluates at a past or future instant; it needs an ADMIN
        key.
        """
        with _reported(tool_error):
            return await tools.evaluate_complaint(complaint_id, as_of)

    async def get_deadlines(complaint_id: str, as_of: datetime | None = None) -> list[DeadlineItem]:
        """A complaint's computed deadlines: clause, day basis and clock state, soonest first."""
        with _reported(tool_error):
            return await tools.get_deadlines(complaint_id, as_of)

    async def explain_decision(decision_id: str) -> Explanation:
        """Render a stored decision record (by its hash) as text, with its chain status."""
        with _reported(tool_error):
            return await tools.explain_decision(decision_id)

    async def check_reply(complaint_id: str, as_of: datetime | None = None) -> ReplyCheck:
        """The engine's check that the sent final reply carries every required element (A18)."""
        with _reported(tool_error):
            return await tools.check_reply(complaint_id, as_of)

    async def list_obligations() -> list[Obligation]:
        """Every obligation in the loaded rule pack, with clause, parameters and verification."""
        with _reported(tool_error):
            return await tools.list_obligations()

    for tool in (
        evaluate_complaint,
        get_deadlines,
        explain_decision,
        check_reply,
        list_obligations,
    ):
        server.tool(annotations=read_only)(tool)
    return server


def main() -> None:
    """Serve the tools over stdio."""
    build_server(tools_from_env()).run("stdio")


if __name__ == "__main__":
    main()
