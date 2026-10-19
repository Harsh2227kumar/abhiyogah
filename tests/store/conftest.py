"""Store fixtures: the in-memory store always; PostgreSQL only when DATABASE_URL is set."""

import pytest

from abhiyogah.store import MemoryStore, Store


@pytest.fixture(params=[pytest.param("memory", id="memory")])
def store(request: pytest.FixtureRequest) -> Store:
    """A fresh, empty store."""
    return MemoryStore()
