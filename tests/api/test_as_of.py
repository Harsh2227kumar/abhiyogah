"""``as_of`` is time travel: ADMIN only, on every read route that takes it, and offset-aware."""

from typing import Any

import pytest
from fastapi.routing import APIRoute

from tests.api.conftest import ADMIN, READER, WRITER, Api
from tests.api.test_api import CID, post

AS_OF = "2026-08-25T12:00:00+05:30"


def as_of_paths(api: Api) -> list[str]:
    """Every GET route that declares an ``as_of`` query parameter, with path params filled in."""
    routes: list[Any] = [r for r in api.client.app.routes if isinstance(r, APIRoute)]  # type: ignore[attr-defined]
    paths = []
    for r in routes:
        if "GET" in (r.methods or ()) and any(p.name == "as_of" for p in r.dependant.query_params):
            paths.append(
                r.path.replace("{complaint_id}", CID).replace(
                    "{obligation_id}", "IO-CB-2026-14-1-b"
                )
            )
    return sorted(paths)


def params(path: str, **extra: str) -> dict[str, str]:
    """Query params, adding the closure route's required unit."""
    base = {"unit": "NODAL-CELL"} if path.endswith("/closure") else {}
    return {**base, **extra}


def test_every_read_with_as_of_is_covered(api: Api) -> None:
    """The routes that take as_of are the ones the console and board read."""
    assert as_of_paths(api) == sorted(
        [
            "/board/deadlines",
            "/complaints",
            f"/complaints/{CID}",
            f"/complaints/{CID}/closure",
            f"/complaints/{CID}/decisions",
            f"/complaints/{CID}/decisions/IO-CB-2026-14-1-b",
        ]
    )


@pytest.mark.parametrize("headers", [READER, WRITER])
def test_non_admins_may_not_time_travel(api: Api, headers: dict[str, str]) -> None:
    """READER and WRITER get 403 for any as_of, and 200 without one."""
    post(api)
    for path in as_of_paths(api):
        travel = api.client.get(path, params=params(path, as_of=AS_OF), headers=headers)
        assert travel.status_code == 403, path
        assert api.client.get(path, params=params(path), headers=headers).status_code == 200, path


def test_admin_may_time_travel_everywhere(api: Api) -> None:
    """ADMIN gets 200 for as_of on every such route."""
    post(api)
    for path in as_of_paths(api):
        res = api.client.get(path, params=params(path, as_of=AS_OF), headers=ADMIN)
        assert res.status_code == 200, (path, res.text)


def test_naive_as_of_is_refused(api: Api) -> None:
    """as_of without an offset is ambiguous: 422."""
    post(api)
    res = api.client.get(
        f"/complaints/{CID}", params={"as_of": "2026-08-25T12:00:00"}, headers=ADMIN
    )
    assert res.status_code == 422


def test_as_of_is_echoed(api: Api) -> None:
    """The detail says which instant it was evaluated at."""
    post(api)
    body = api.client.get(f"/complaints/{CID}", params={"as_of": AS_OF}, headers=ADMIN).json()
    assert body["as_of"] == "2026-08-25T12:00:00+05:30"
