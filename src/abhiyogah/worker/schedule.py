"""Which complaints the scheduler re-evaluates, and the sweep that does it.

A complaint is due for re-evaluation when time alone can change a result:

- an obligation's latest record is ``RUNNING`` (it may breach), ``BREACHED`` (days late and
  compensation grow) or ``INSUFFICIENT_FACTS``;
- an obligation has no record yet, or its record was made under another version of the rule
  (the rule pack changed);
- an obligation's ``valid_from`` or ``valid_to`` boundary fell between the last evaluation and now
  (a future-dated rule came into force, or a rule lapsed).

Results that only events can change (``NOT_TRIGGERED``, ``STOPPED_*``, ``DETERMINED``) are left to
the re-evaluation that runs on each new event. Appending stays "only when the result changed"
(``worker.reevaluate``), so a sweep that finds nothing new writes nothing.
"""

import logging
from collections.abc import Sequence
from datetime import datetime

from abhiyogah.domain.decision import DecisionRecord, DecisionResult
from abhiyogah.domain.errors import DomainError
from abhiyogah.domain.tz import ist_date
from abhiyogah.evaluator import obligation_version
from abhiyogah.registry.schema import Obligation
from abhiyogah.store import Store
from abhiyogah.worker.reevaluate import (
    EngineContext,
    ReevaluationResult,
    latest_by_obligation,
    reevaluate,
)

__all__ = ["TIME_SENSITIVE", "needs_reevaluation", "sweep"]

log = logging.getLogger(__name__)

TIME_SENSITIVE = frozenset(
    {DecisionResult.RUNNING, DecisionResult.BREACHED, DecisionResult.INSUFFICIENT_FACTS}
)


def _boundary_crossed(ob: Obligation, last: datetime, now: datetime) -> bool:
    """A validity date fell in (last evaluation date, now date]."""
    then, today = ist_date(last), ist_date(now)
    edges = [ob.valid_from] + ([ob.valid_to] if ob.valid_to is not None else [])
    return any(then < edge <= today for edge in edges)


def needs_reevaluation(
    chain: Sequence[DecisionRecord], obligations: Sequence[Obligation], as_of: datetime
) -> bool:
    """True if time or a rule-pack change can alter one of this complaint's results."""
    latest = latest_by_obligation(chain)
    for ob in obligations:
        record = latest.get(ob.obligation_id)
        if record is None or record.result in TIME_SENSITIVE:
            return True
        if record.obligation_version != obligation_version(ob):
            return True
        if _boundary_crossed(ob, record.as_of, as_of):
            return True
    return False


def sweep(store: Store, ctx: EngineContext, as_of: datetime) -> list[ReevaluationResult]:
    """Re-evaluate every complaint that needs it; one failing complaint does not stop the rest."""
    results = []
    for cid in store.complaint_ids():
        if not needs_reevaluation(store.decisions(cid), ctx.obligations, as_of):
            continue
        try:
            results.append(reevaluate(store, ctx, cid, as_of))
        except DomainError as exc:
            log.warning("re-evaluation of %s failed: %s", cid, exc)
            results.append(ReevaluationResult(cid, error=str(exc)))
    return results
