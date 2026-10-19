"""Store fixtures: the in-memory store always; PostgreSQL only when DATABASE_URL is set.

The PostgreSQL fixtures rebuild the ``public`` schema with the Alembic migrations before each test,
so point DATABASE_URL at a throwaway database.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from abhiyogah.store import MemoryStore, Store
from abhiyogah.store.sql import SqlStore, make_engine

ROOT = Path(__file__).parents[2]


def alembic_config(url: str) -> Config:
    """The repo's Alembic config pointed at ``url``."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def pg_engine() -> Iterator[Engine]:
    """An engine on a freshly migrated schema."""
    url = os.environ["DATABASE_URL"]
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("DROP FUNCTION IF EXISTS abhiyogah_evidence_is_append_only CASCADE"))
        conn.execute(text("DROP FUNCTION IF EXISTS abhiyogah_review_task_guard CASCADE"))
    command.upgrade(alembic_config(url), "head")
    yield engine
    engine.dispose()


@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.db),
    ]
)
def store(request: pytest.FixtureRequest) -> Store:
    """A fresh, empty store of each kind."""
    if request.param == "postgres":
        engine: Engine = request.getfixturevalue("pg_engine")
        return SqlStore(engine)
    return MemoryStore()
