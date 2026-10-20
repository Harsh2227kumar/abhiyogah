"""What counts as a change worth a new decision record (issue #40)."""

from datetime import UTC, date, datetime

from abhiyogah.api.rulepack import load_obligations
from abhiyogah.calendar import load_bank_calendar
from abhiyogah.domain.decision import DecisionResult, ParameterUse
from abhiyogah.domain.enums import Verification
from abhiyogah.store import MemoryStore
from abhiyogah.worker.reevaluate import EngineContext, material, reevaluate
from abhiyogah.worker.schedule import sweep
from tests.api.test_rulepack_end_to_end import PROFILE, RULES
from tests.domain.test_decision import make_record
from tests.workflow.builders import RECEIVED, outcome


def test_anchor_date_alone_is_not_material() -> None:
    """Same record with another as_of and anchor date: nothing to append."""
    a = make_record()
    b = a.model_copy(
        update={"as_of": datetime(2026, 9, 3, tzinfo=UTC), "anchor_date": date(2026, 9, 3)}
    )
    assert material(a) == material(b)


def test_a_new_parameter_version_is_material() -> None:
    """When the anchor selects another parameter version, the parameters differ."""
    a = make_record()
    newer = ParameterUse(
        name="max_days",
        value=20,
        effective_date=date(2026, 9, 1),
        reference="test",
        verification=Verification.PRIMARY_TEXT_READ,
    )
    b = a.model_copy(update={"anchor_date": date(2026, 9, 3), "parameters": [newer]})
    assert material(a) != material(b)


def test_daily_sweep_appends_only_real_changes_on_the_rule_pack() -> None:
    """Issue #40's reproduction: A3 and the A15 check are no longer re-appended each day."""
    ctx = EngineContext(load_obligations(RULES), load_bank_calendar(), PROFILE)
    store = MemoryStore()
    store.append_events([RECEIVED, outcome("WHOLLY_REJECTED")])
    reevaluate(store, ctx, "CMP-WF-1", datetime(2026, 8, 10, 12, tzinfo=UTC))
    sweep(store, ctx, datetime(2026, 9, 2, 12, tzinfo=UTC))
    day3 = sweep(store, ctx, datetime(2026, 9, 3, 12, tzinfo=UTC))
    appended = {r.obligation_id: r.result for res in day3 for r in res.appended}
    assert "RBIOS-2026-10-1-g" not in appended
    assert "IO-CB-2026-14-3-4-review" not in appended
    assert appended["IO-CB-2026-14-1-b"] is DecisionResult.BREACHED  # days late grew
