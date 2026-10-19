"""The scheduler re-evaluates what time can change and appends only changed results."""

from datetime import UTC, date, datetime

import pytest

from abhiyogah.domain.decision import DecisionResult
from abhiyogah.domain.events import ComplaintEvent, EventType
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext, reevaluate
from abhiyogah.worker.schedule import needs_reevaluation, sweep
from tests.api.conftest import CTX
from tests.evaluator.builders import obligation, ordinary_limb
from tests.workflow.builders import RECEIVED, ev, outcome

T0 = datetime(2026, 8, 10, 12, tzinfo=UTC)
LATE = datetime(2026, 8, 25, 12, tzinfo=UTC)


def seeded(*extra: ComplaintEvent) -> MemoryStore:
    """Receipt 3 Aug and a rejection on 10 Aug, evaluated at T0."""
    store = MemoryStore()
    store.append_events([RECEIVED, outcome("WHOLLY_REJECTED"), *extra])
    reevaluate(store, CTX, "CMP-WF-1", T0)
    return store


def test_running_clock_is_swept_and_breach_is_appended() -> None:
    """Past day 20 the sweep appends the breached result, once."""
    store = seeded()
    first = sweep(store, CTX, LATE)
    assert [r.result for res in first for r in res.appended] == [DecisionResult.BREACHED]
    again = sweep(store, CTX, LATE)
    assert sum(len(r.appended) for r in again) == 0


def test_breach_grows_daily_so_each_day_appends() -> None:
    """Days late is material: a new day, a new record."""
    store = seeded()
    sweep(store, CTX, LATE)
    later = sweep(store, CTX, datetime(2026, 8, 26, 12, tzinfo=UTC))
    (rec,) = [r for res in later for r in res.appended]
    assert rec.breach is not None
    assert rec.breach.days_late == 3


def test_stopped_complaint_is_not_swept() -> None:
    """Once every clock stopped, time cannot change the result."""
    store = seeded(ev(4, EventType.IO_REFERRED, date(2026, 8, 12)))
    reevaluate(store, CTX, "CMP-WF-1", datetime(2026, 8, 12, 12, tzinfo=UTC))
    assert not needs_reevaluation(store.decisions("CMP-WF-1"), CTX.obligations, LATE)
    assert sweep(store, CTX, LATE) == []


def test_unevaluated_obligation_or_new_rule_version_is_due() -> None:
    """A missing record, or a record made under another version of the rule, is due."""
    store = seeded(ev(4, EventType.IO_REFERRED, date(2026, 8, 12)))
    reevaluate(store, CTX, "CMP-WF-1", datetime(2026, 8, 12, 12, tzinfo=UTC))
    chain = store.decisions("CMP-WF-1")
    changed = [ordinary_limb().model_copy(update={"subject": "bank (edited)"})]
    assert needs_reevaluation(chain, changed, LATE)
    extra = [*CTX.obligations, obligation(obligation_id="IO-CB-2026-14-9-x")]
    assert needs_reevaluation(chain, extra, LATE)


@pytest.mark.parametrize(
    ("valid_from", "due"), [(date(2026, 8, 20), True), (date(2026, 9, 1), False)]
)
def test_future_dated_rule_coming_into_force_is_due(valid_from: date, due: bool) -> None:
    """A valid_from between the last evaluation and now makes the complaint due."""
    future = obligation(obligation_id="IO-CB-2026-14-1-z", valid_from=valid_from)
    ctx = EngineContext(obligations=[future], calendar=CTX.calendar, profile=CTX.profile)
    store = MemoryStore()
    store.append_events([RECEIVED, ev(4, EventType.IO_REFERRED, date(2026, 8, 5))])
    reevaluate(store, ctx, "CMP-WF-1", T0)
    (record,) = store.decisions("CMP-WF-1")
    assert record.result is DecisionResult.NOT_APPLICABLE
    assert needs_reevaluation([record], [future], LATE) is due
