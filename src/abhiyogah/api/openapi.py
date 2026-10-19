"""Export the API's OpenAPI document: ``python -m abhiyogah.api.openapi [path]``.

The document is built from an app with no configuration (in-memory store, empty rule pack), so it
depends only on the code, never on the environment. Keys are kept in the generator's order and the
file ends with a newline, so a stale ``openapi.json`` shows up as a diff (see tests/api).
"""

import json
import sys
from pathlib import Path

from abhiyogah.api.app import create_app
from abhiyogah.api.settings import Settings
from abhiyogah.calendar import load_bank_calendar
from abhiyogah.domain.enums import EntityType
from abhiyogah.evaluator import EntityProfile
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext

__all__ = ["DEFAULT_PATH", "openapi_document", "render"]

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "openapi.json"


def openapi_document() -> dict[str, object]:
    """The OpenAPI document of the API."""
    ctx = EngineContext(
        obligations=[],
        calendar=load_bank_calendar(),
        profile=EntityProfile(entity_type=EntityType.COMMERCIAL_BANK),
    )
    return create_app(settings=Settings(), store=MemoryStore(), ctx=ctx).openapi()


def render() -> str:
    """The document as the text written to ``openapi.json``."""
    return json.dumps(openapi_document(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> None:
    """Write the document to ``argv[0]`` or the repository's ``openapi.json``."""
    path = Path(argv[0]) if argv else DEFAULT_PATH
    path.write_text(render(), encoding="utf-8")
    print(f"openapi: wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
