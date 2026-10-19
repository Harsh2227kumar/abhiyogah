"""Required-action codes: what the bank must do to stop a running or breached clock.

One action per obligation, named after the business event that stops its clock: the first stop
event in the clock spec. The codes follow ``rules/obligations/_conventions.md``; a stop event
without one in the table uses its own name. A ``PERMISSION`` (a complainant's right, such as the
RBI filing window) produces no actions.
"""

from abhiyogah.domain.events import EventType

__all__ = ["ACTION_FOR_STOP", "action_code"]

ACTION_FOR_STOP: dict[EventType, str] = {
    EventType.ACKNOWLEDGED: "ACKNOWLEDGE_COMPLAINT",
    EventType.OUTCOME_SET: "SET_OUTCOME",
    EventType.IO_REFERRED: "REFER_TO_IO",
    EventType.IO_DECIDED: "OBTAIN_IO_DECISION",
    EventType.FINAL_REPLY_SENT: "SEND_FINAL_DECISION",
    EventType.WRITTEN_RESPONSE_FILED: "FILE_WRITTEN_RESPONSE",
    EventType.COMPLIANCE_INTIMATED: "COMPLY_WITH_AWARD_OR_APPEAL",
    EventType.APPEAL_FILED: "COMPLY_WITH_AWARD_OR_APPEAL",
    EventType.REVERSAL_POSTED: "REVERSE_TRANSACTION",
    EventType.SHADOW_CREDITED: "SHADOW_CREDIT",
    EventType.LIABILITY_DETERMINED: "COMPENSATE_PER_PARAS_67_72",
    EventType.SENIOR_REVIEWED: "SENIOR_REVIEW",
    EventType.CLAIM_SETTLED: "SETTLE_CLAIM",
    EventType.DOCUMENTS_RELEASED: "RELEASE_DOCUMENTS",
}


def action_code(stop: EventType) -> str:
    """The action code that the ``stop`` event fulfils."""
    return ACTION_FOR_STOP.get(stop, stop.value)
