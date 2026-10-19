"""``openapi.json`` is generated from the code and is never stale."""

import json

from abhiyogah.api.openapi import DEFAULT_PATH, render


def test_committed_openapi_json_is_current() -> None:
    """Run `make openapi` if this fails."""
    assert DEFAULT_PATH.read_text(encoding="utf-8") == render()


def test_document_declares_the_api_key_scheme_and_core_routes() -> None:
    """Clients see the X-API-Key scheme and the console's operation IDs."""
    doc = json.loads(render())
    assert doc["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"
    ops = {op["operationId"] for path in doc["paths"].values() for op in path.values()}
    assert {
        "listComplaints",
        "getComplaint",
        "getDecision",
        "listObligations",
        "postEvents",
        "listDecisions",
        "explainDecision",
        "boardDeadlines",
    } <= ops
