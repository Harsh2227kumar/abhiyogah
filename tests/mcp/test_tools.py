"""The MCP tools read the platform API and add no logic of their own."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
import pytest

from abhiyogah.domain.decision import DecisionResult
from abhiyogah.mcp.tools import REPLY_CHECKS, EngineTools, ReadOnlyError, ToolCallError
from tests.api.conftest import ADMIN, READER
from tests.api.test_end_to_end import CID
from tests.mcp.conftest import Demo


def run[T](
    demo: Demo, call: Callable[[EngineTools], Awaitable[T]], key: dict[str, str] = READER
) -> T:
    """Run one tool call against the demo API."""

    async def go() -> T:
        async with demo.tools(key) as tools:
            return await call(tools)

    return asyncio.run(go())


def test_reply_checks_are_the_evaluators_reply_content_obligations() -> None:
    """``check_reply`` selects on the evaluator's own registry, not a copy."""
    assert "IO-CB-2026-14-11-12" in REPLY_CHECKS


def test_get_deadlines_are_the_complaints_deadlines(demo: Demo) -> None:
    """Deadlines are the API's, in the API's order."""
    api = demo.client.get(f"/complaints/{CID}", headers=READER).json()["deadlines"]
    got = run(demo, lambda t: t.get_deadlines(CID))
    assert [d.model_dump(mode="json") for d in got] == api
    assert {d.obligation_id for d in got} >= {"IO-CB-2026-14-1-b", "RBCCB-2025-72"}


def test_check_reply_reports_missing_elements(demo: Demo) -> None:
    """The A18 decision on the sent reply: one element missing, a corrected reply required."""
    check = run(demo, lambda t: t.check_reply(CID))
    (rec,) = check.checks
    assert rec.result is DecisionResult.DETERMINED
    assert rec.outputs == {"reply_complete": False, "missing_elements": ["B"]}
    assert [a.action for a in rec.required_actions] == ["SEND_CORRECTED_REPLY"]


def test_explain_decision_renders_a_stored_record(demo: Demo) -> None:
    """Explanations come from the stored chain."""
    chain = demo.client.get(f"/complaints/{CID}/decisions", headers=READER).json()["records"]
    last = chain[-1]["hash"]
    got = run(demo, lambda t: t.explain_decision(last))
    api = demo.client.get(f"/decisions/{last}/explain", headers=READER).json()
    assert got.model_dump(mode="json") == api
    assert got.chain.verified is True


def test_list_obligations_is_the_loaded_rule_pack(demo: Demo) -> None:
    """The rule pack as the API serves it."""
    api = demo.client.get("/obligations", headers=READER).json()
    got = run(demo, lambda t: t.list_obligations())
    assert [o.model_dump(mode="json") for o in got] == api


def test_api_errors_surface_with_status_and_detail(demo: Demo) -> None:
    """An unknown complaint is the API's 404; time travel without ADMIN is the API's 403."""
    with pytest.raises(ToolCallError) as missing:
        run(demo, lambda t: t.evaluate_complaint("CMP-NOPE"))
    assert missing.value.status == 404
    assert "CMP-NOPE" in missing.value.detail
    past = datetime(2026, 8, 25, 6, tzinfo=UTC)
    with pytest.raises(ToolCallError) as forbidden:
        run(demo, lambda t: t.evaluate_complaint(CID, past))
    assert forbidden.value.status == 403
    travelled = run(demo, lambda t: t.evaluate_complaint(CID, past), ADMIN)
    assert travelled.as_of == past


def test_a_bad_key_is_refused_by_the_api(demo: Demo) -> None:
    """Authentication is the API's: a wrong key is a 401."""
    with pytest.raises(ToolCallError) as refused:
        run(demo, lambda t: t.list_obligations(), {"X-API-Key": "not-a-key-0123456789"})
    assert refused.value.status == 401


def test_the_client_refuses_writes(demo: Demo) -> None:
    """Tools are read-only: a POST through their client never reaches the API."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(201)

    async def post() -> None:
        async with EngineTools.over(httpx.MockTransport(handler), "k", "http://test") as tools:
            await tools._client.post(f"/complaints/{CID}/events", json={})

    with pytest.raises(ReadOnlyError):
        asyncio.run(post())
    assert seen == []
