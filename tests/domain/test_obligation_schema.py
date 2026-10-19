"""registry.schema: the obligation file model."""

from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from abhiyogah.domain.enums import RuleStatus, Verification
from abhiyogah.domain.events import EventType
from abhiyogah.registry.schema import Obligation

# The report's example (A13 ordinary limb) as an agent must write it: DRAFT, no signed_off_by.
EXAMPLE = """
obligation_id: IO-CB-2026-14-1-b
deontic: OBLIGATION
subject: bank
instrument: "RBI (Commercial Banks – Internal Ombudsman) Directions, 2026"
instrument_ref: "RBI/CEPD/2025-26/381; CEPD.PRD.No.S1027/13.01.019/2025-26"
clause: "14(1)(b)"
source_url: "https://sbi.bank.in/documents/53471/53742/11082026_Annexure+I-RBI+Commercial+Banks-Internal+Ombudsman+Directions+2026.pdf/7a497eab-60d3-155f-e5cd-357b80ebda24"
applies_to: {entity_type: COMMERCIAL_BANK, min_outlets: 10, outlets_as_on: 2025-03-31}
trigger: {event: OUTCOME_SET, condition: "outcome in [PARTIALLY_RESOLVED, WHOLLY_REJECTED]"}
clock: {start: BANK_RECEIVED, stop: IO_REFERRED, basis: CALENDAR, basis_status: INFERRED,
        tz: Asia/Kolkata}
parameters:
  max_days:
    "2026-01-14": {value: 20, reference: "cl. 14(1)(b)", verification: PRIMARY_TEXT_READ,
                   open_question: Q4}
overridden_by: [IO-CB-2026-14-1-a]
valid_from: 2026-01-14
valid_to: null
status: DRAFT
verification: PRIMARY_TEXT_READ
supersedes_note: "MD-IO 2023 (29 Dec 2023); clause mapping not verified"
tests: [io_20d_ordinary_breach.yaml]
"""


def load(**overrides: Any) -> Obligation:
    """Parse the example with top-level overrides."""
    data = yaml.safe_load(EXAMPLE)
    data.update(overrides)
    return Obligation.model_validate(data)


def test_example_parses() -> None:
    """The report's example parses into the model."""
    ob = load()
    assert ob.clock is not None
    assert ob.clock.start is EventType.BANK_RECEIVED
    assert ob.clock.stop == [EventType.IO_REFERRED]
    assert ob.clock.pause is None
    (value,) = ob.parameters["max_days"].values()
    assert value.value == 20
    assert ob.signed_off_by is None


def test_in_force_needs_sign_off_and_primary_text() -> None:
    """Hard rule 1: IN_FORCE without sign-off or primary-text verification is refused."""
    with pytest.raises(ValidationError):
        load(status=RuleStatus.IN_FORCE)
    with pytest.raises(ValidationError):
        load(
            status=RuleStatus.IN_FORCE,
            signed_off_by="owner",
            verification=Verification.SECONDARY_ONLY,
        )
    assert load(status="IN_FORCE", signed_off_by="owner").status is RuleStatus.IN_FORCE


def test_clock_can_start_from_a_date_fact() -> None:
    """The failed-transaction clock starts at fact T, not an event."""
    ob = load(
        clock={
            "start": "transaction_date_t",
            "stop": "REVERSAL_POSTED",
            "basis": "CALENDAR",
            "basis_status": "EXPLICIT",
        }
    )
    assert ob.clock is not None
    assert ob.clock.start == "transaction_date_t"


@pytest.mark.parametrize(
    "overrides",
    [
        {"obligation_id": "io 20 days"},
        {"clock": {"start": "whenever", "basis": "CALENDAR", "basis_status": "INFERRED"}},
        {"anchor": "not_a_fact"},
        {"valid_to": "2025-01-01"},
        {"parameters": {"max_days": {}}},
        {"unknown_field": 1},
        {"applies_to": {"entity_type": "commercial_bank"}},
    ],
)
def test_malformed_obligations_are_rejected(overrides: dict[str, Any]) -> None:
    """Structural errors fail validation."""
    with pytest.raises(ValidationError):
        load(**overrides)
