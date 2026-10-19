"""The MCP ``evaluate_complaint`` result equals the API's for the demo complaint, field for field.

Checked twice: through the tool function (always), and through the MCP protocol with the official
SDK's client connected in-process (skipped where the SDK is not installed).
"""

import asyncio
from datetime import datetime
from typing import Any

import pytest

from abhiyogah.mcp.server import build_server
from tests.api.conftest import ADMIN, READER
from tests.api.test_end_to_end import CID
from tests.mcp.conftest import Demo

TRAVEL = "2026-08-25T12:00:00+05:30"
"""Past day 20: the IO referral and the shadow credit are both breached."""


def api_result(
    demo: Demo, params: dict[str, str] | None = None, key: dict[str, str] = READER
) -> Any:
    """``GET /complaints/{CID}`` as JSON."""
    res = demo.client.get(f"/complaints/{CID}", params=params, headers=key)
    assert res.status_code == 200, res.text
    return res.json()


def test_tool_result_equals_api_result(demo: Demo) -> None:
    """Now, and time-travelled past the breaches with an ADMIN key."""

    async def go() -> tuple[Any, Any]:
        async with demo.tools(READER) as reader, demo.tools(ADMIN) as admin:
            now = await reader.evaluate_complaint(CID)
            travel = await admin.evaluate_complaint(CID, datetime.fromisoformat(TRAVEL))
            return now.model_dump(mode="json"), travel.model_dump(mode="json")

    now, travel = asyncio.run(go())
    assert now == api_result(demo)
    assert travel == api_result(demo, {"as_of": TRAVEL}, ADMIN)
    assert {b["breach"]["obligation_id"] for b in travel["breaches"]} == {
        "IO-CB-2026-14-1-b",
        "RBCCB-2025-72",
    }


def test_mcp_protocol_result_equals_api_result(demo: Demo) -> None:
    """An MCP client's ``tools/call`` returns the API's JSON as structured content."""
    mcp = pytest.importorskip("mcp", reason="the MCP Python SDK is not installed")

    async def go() -> tuple[Any, Any]:
        async with demo.tools(ADMIN) as tools, mcp.Client(build_server(tools)) as client:
            now = await client.call_tool("evaluate_complaint", {"complaint_id": CID})
            travel = await client.call_tool(
                "evaluate_complaint", {"complaint_id": CID, "as_of": TRAVEL}
            )
            assert not now.is_error
            assert not travel.is_error
            return now.structured_content, travel.structured_content

    now, travel = asyncio.run(go())
    assert now == api_result(demo)
    assert travel == api_result(demo, {"as_of": TRAVEL}, ADMIN)


def test_mcp_protocol_reports_api_refusals_as_tool_errors(demo: Demo) -> None:
    """A READER's time travel is the API's 403, returned to the agent as a tool error."""
    mcp = pytest.importorskip("mcp", reason="the MCP Python SDK is not installed")

    async def go() -> Any:
        async with demo.tools(READER) as tools, mcp.Client(build_server(tools)) as client:
            return await client.call_tool(
                "evaluate_complaint", {"complaint_id": CID, "as_of": TRAVEL}
            )

    result = asyncio.run(go())
    assert result.is_error
    assert "403" in result.content[0].text
