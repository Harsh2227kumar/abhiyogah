"""PostgreSQL-only checks: migrations match the models; the database refuses to edit evidence."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from abhiyogah.domain.events import EventType
from abhiyogah.ledger import verify_chain
from abhiyogah.store.models import Base
from abhiyogah.store.sql import SqlStore
from abhiyogah.workflow import ReviewKind, ReviewTask
from tests.domain.test_decision import make_record
from tests.workflow.builders import ev

pytestmark = pytest.mark.db

E1 = ev(1, EventType.BANK_RECEIVED, date(2026, 8, 3))


def seeded(engine: Engine) -> SqlStore:
    """A store with one event, one decision record and one review task."""
    store = SqlStore(engine)
    store.append_events([E1])
    store.append_decisions("CMP-TEST-1", [make_record()])
    store.add_review_task(
        ReviewTask(
            task_id="RT-1",
            complaint_id=E1.complaint_id,
            kind=ReviewKind.NO_DEFICIENCY,
            reason="test",
            source_ref="PF-1",
            created_at=E1.recorded_at,
        )
    )
    return store


def test_migrations_match_the_models(pg_engine: Engine) -> None:
    """Autogenerate finds nothing to add: models and migrations agree."""
    with pg_engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE events SET payload = '{}'::jsonb",
        "DELETE FROM events",
        "TRUNCATE events CASCADE",
        "UPDATE decision_records SET result = 'RUNNING'",
        "DELETE FROM decision_records",
        "TRUNCATE decision_records",
        "DELETE FROM review_tasks",
        "UPDATE review_tasks SET kind = 'NOT_A_COMPLAINT'",
        "UPDATE review_tasks SET status = 'DONE'",
        "TRUNCATE review_tasks",
    ],
)
def test_database_refuses_to_change_evidence(pg_engine: Engine, statement: str) -> None:
    """Triggers refuse every rewrite, whatever client sends it."""
    seeded(pg_engine)
    with pytest.raises(DBAPIError, match="not allowed"), pg_engine.begin() as conn:
        conn.execute(text(statement))


def test_review_task_closes_only_with_a_business_event(pg_engine: Engine) -> None:
    """OPEN -> DONE with the closing event's ID is the one allowed update."""
    seeded(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(
            text("UPDATE review_tasks SET status = 'DONE', closed_by_event_id = :e"),
            {"e": E1.event_id},
        )
    with pytest.raises(DBAPIError, match="not allowed"), pg_engine.begin() as conn:
        conn.execute(text("UPDATE review_tasks SET status = 'OPEN'"))


def test_round_trip_keeps_hashes_valid(pg_engine: Engine) -> None:
    """Records read back from JSONB still verify (canonical JSON is stable)."""
    store = seeded(pg_engine)
    assert verify_chain(store.decisions("CMP-TEST-1")).verified


def test_forked_chain_is_impossible(pg_engine: Engine) -> None:
    """A second record on the same prev_hash violates the chain-link constraint."""
    store = seeded(pg_engine)
    (first,) = store.decisions("CMP-TEST-1")
    with pytest.raises(DBAPIError), pg_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO decision_records "
                "(hash, prev_hash, complaint_id, obligation_id, result, as_of, record) "
                "VALUES (:h, :p, 'CMP-TEST-1', 'X', 'RUNNING', now(), '{}'::jsonb)"
            ),
            {"h": "e" * 64, "p": first.prev_hash},
        )


def test_concurrent_appends_keep_one_chain(pg_engine: Engine) -> None:
    """Parallel writers on one complaint serialise on the advisory lock."""
    store = SqlStore(pg_engine)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: store.append_decisions("CMP-TEST-1", [make_record()]), range(16)))
    chain = store.decisions("CMP-TEST-1")
    assert len(chain) == 16
    assert verify_chain(chain).verified


def test_database_url_is_set() -> None:
    """Sanity: db tests only run with a database."""
    assert os.environ.get("DATABASE_URL")
