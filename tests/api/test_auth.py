"""API-key roles: unknown keys get 401, too-low roles get 403, keys are parsed strictly."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from abhiyogah.api.auth import Principal, Role, parse_api_keys, require

KEYS = ";".join(
    [
        "reader-1:reader:r-key-0123456789ab",
        "writer-1:writer:w-key-0123456789ab",
        "admin-1:admin:a-key-0123456789ab",
    ]
)


def app() -> TestClient:
    """A tiny app with one route per role."""
    api = FastAPI()
    api.state.keyring = parse_api_keys(KEYS)

    @api.get("/read")
    def read(p: Annotated[Principal, Depends(require(Role.READER))]) -> str:
        return p.actor_id

    @api.post("/write")
    def write(p: Annotated[Principal, Depends(require(Role.WRITER))]) -> str:
        return p.actor_id

    @api.get("/admin")
    def admin(p: Annotated[Principal, Depends(require(Role.ADMIN))]) -> str:
        return p.actor_id

    return TestClient(api)


@pytest.mark.parametrize(
    ("key", "path", "method", "code"),
    [
        (None, "/read", "GET", 401),
        ("wrong-key-0123456789", "/read", "GET", 401),
        ("r-key-0123456789ab", "/read", "GET", 200),
        ("r-key-0123456789ab", "/write", "POST", 403),
        ("w-key-0123456789ab", "/write", "POST", 200),
        ("w-key-0123456789ab", "/admin", "GET", 403),
        ("a-key-0123456789ab", "/admin", "GET", 200),
        ("a-key-0123456789ab", "/write", "POST", 200),
    ],
)
def test_roles(key: str | None, path: str, method: str, code: int) -> None:
    """Each role reaches its own routes and those below it, and nothing above."""
    headers = {"X-API-Key": key} if key else {}
    assert app().request(method, path, headers=headers).status_code == code


def test_principal_is_the_key_owner() -> None:
    """The route sees who called."""
    assert app().get("/read", headers={"X-API-Key": "w-key-0123456789ab"}).json() == "writer-1"


@pytest.mark.parametrize(
    "spec",
    ["no-colons", "a:reader:", "a:superuser:k-0123456789abcdef", "a:reader:short"],
)
def test_bad_key_specs_are_refused(spec: str) -> None:
    """Malformed entries, unknown roles and short keys fail at start-up."""
    with pytest.raises(ValueError):  # noqa: PT011 - message varies by case
        parse_api_keys(spec)


def test_blank_spec_has_no_keys() -> None:
    """No keys configured means every request is refused."""
    assert parse_api_keys(" ; ").lookup("anything-at-all-123") is None
