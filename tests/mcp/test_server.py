"""The MCP server registers the five read-only tools with the official SDK."""

import asyncio

import pytest

from abhiyogah.mcp.server import build_server
from tests.api.conftest import READER
from tests.mcp.conftest import Demo

pytest.importorskip("mcp.server.mcpserver", reason="the MCP Python SDK is not installed")

TOOLS = {
    "evaluate_complaint",
    "get_deadlines",
    "explain_decision",
    "check_reply",
    "list_obligations",
}


def test_server_lists_the_five_read_only_tools(demo: Demo) -> None:
    """Every tool is there, annotated read-only and non-destructive, with an output schema."""
    server = build_server(demo.tools(READER))
    listed = asyncio.run(server.list_tools())
    assert {t.name for t in listed} == TOOLS
    for tool in listed:
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.output_schema is not None
