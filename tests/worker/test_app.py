"""The procrastinate app registers the tasks docker-compose expects and runs them."""

from datetime import UTC, datetime

import pytest

from abhiyogah.store import MemoryStore
from abhiyogah.worker import app as worker
from abhiyogah.worker.reevaluate import reevaluate
from tests.api.conftest import CTX
from tests.workflow.builders import RECEIVED, outcome


def test_tasks_and_periodic_schedule_are_registered() -> None:
    """Both tasks exist; the sweep is periodic on the default 15-minute cron."""
    assert {"reevaluate_open", "reevaluate_complaint"} <= set(worker.app.tasks)
    periodic = worker.app.periodic_registry.periodic_tasks
    crons = {p.cron for p in periodic.values()}
    assert crons == {"*/15 * * * *"}


@pytest.mark.parametrize(
    ("minutes", "cron"), [(1, "*/1 * * * *"), (15, "*/15 * * * *"), (120, "0 */2 * * *")]
)
def test_cron_for(minutes: int, cron: str) -> None:
    """Periods map to cron expressions."""
    assert worker.cron_for(minutes) == cron


@pytest.mark.parametrize("minutes", [0, 90, 24 * 60])
def test_cron_for_refuses_unschedulable_periods(minutes: int) -> None:
    """A period cron cannot express is a configuration error."""
    with pytest.raises(ValueError, match=r"minute|hours"):
        worker.cron_for(minutes)


def test_periodic_task_sweeps_the_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running the periodic task at a later timestamp appends the breach."""
    store = MemoryStore()
    store.append_events([RECEIVED, outcome("WHOLLY_REJECTED")])
    reevaluate(store, CTX, "CMP-WF-1", datetime(2026, 8, 10, 12, tzinfo=UTC))
    monkeypatch.setattr(worker, "_runtime", lambda: (store, CTX))
    late = int(datetime(2026, 8, 25, 12, tzinfo=UTC).timestamp())
    assert worker.reevaluate_open(late) == 1
    assert worker.reevaluate_open(late) == 0
