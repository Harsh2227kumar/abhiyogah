"""The background worker: a procrastinate ``App`` with the re-evaluation tasks.

Run with ``procrastinate --app=abhiyogah.worker.app.app worker`` (docker-compose does this). The
job queue lives in the same PostgreSQL database (``DATABASE_URL``); apply procrastinate's schema
once with ``procrastinate --app=abhiyogah.worker.app.app schema --apply``.

- ``reevaluate_open`` runs every ``ABHIYOGAH_REEVALUATE_MINUTES`` (default 15) and sweeps the
  complaints whose results time can change (``worker.schedule``).
- ``reevaluate_complaint`` re-evaluates one complaint; the API already does this inline right after
  each new event, and other producers (bulk imports) can defer it.

Both append decision records only when a result changed.
"""

from datetime import UTC, datetime
from functools import cache

import procrastinate

from abhiyogah.api.rulepack import load_obligations
from abhiyogah.api.settings import Settings
from abhiyogah.calendar import load_bank_calendar
from abhiyogah.store import MemoryStore, Store
from abhiyogah.worker.reevaluate import EngineContext, reevaluate
from abhiyogah.worker.schedule import sweep

__all__ = ["app", "cron_for", "reevaluate_complaint", "reevaluate_open"]


def cron_for(minutes: int) -> str:
    """A cron expression that fires every ``minutes`` minutes (1-59) or hours (multiples of 60)."""
    if minutes < 1:
        raise ValueError("the re-evaluation period must be at least one minute")
    if minutes < 60:
        return f"*/{minutes} * * * *"
    if minutes % 60 == 0 and minutes // 60 < 24:
        return f"0 */{minutes // 60} * * *"
    raise ValueError("use a period under 60 minutes or a whole number of hours under 24")


def _connector(settings: Settings) -> procrastinate.BaseConnector:
    """PostgreSQL when configured; otherwise an in-memory queue (tests and demos)."""
    if settings.database_url:
        conninfo = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        return procrastinate.PsycopgConnector(conninfo=conninfo)
    from procrastinate.testing import InMemoryConnector

    return InMemoryConnector()


@cache
def _runtime() -> tuple[Store, EngineContext]:
    """The store and engine context, built once per worker process from the environment."""
    settings = Settings.from_env()
    store: Store
    if settings.database_url:
        from abhiyogah.store.sql import SqlStore, make_engine

        store = SqlStore(make_engine(settings.database_url))
    else:
        store = MemoryStore()
    ctx = EngineContext(
        obligations=load_obligations(settings.rules_dir),
        calendar=load_bank_calendar(),
        profile=settings.profile,
    )
    return store, ctx


_settings = Settings.from_env()
app = procrastinate.App(connector=_connector(_settings))
"""The process-wide procrastinate app."""


@app.periodic(cron=cron_for(_settings.reevaluate_minutes), periodic_id="reevaluate_open")
@app.task(name="reevaluate_open", queueing_lock="reevaluate_open")
def reevaluate_open(timestamp: int) -> int:
    """Sweep complaints whose results time can change; return how many records were appended."""
    store, ctx = _runtime()
    as_of = datetime.fromtimestamp(timestamp, UTC)
    return sum(len(r.appended) for r in sweep(store, ctx, as_of))


@app.task(name="reevaluate_complaint")
def reevaluate_complaint(complaint_id: str) -> int:
    """Re-evaluate one complaint now; return how many records were appended."""
    store, ctx = _runtime()
    return len(reevaluate(store, ctx, complaint_id, datetime.now(UTC)).appended)
