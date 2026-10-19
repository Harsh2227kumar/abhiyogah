"""Pydantic model of one obligation YAML file in ``rules/obligations/``.

The shape follows the report's example obligation (section "A deterministic core wrapped by LLM
perception"); ``rules/README.md`` documents every field. This module checks structure only. Policy
checks (missing citations, overlapping validity, pause rules, scenario coverage) belong to the
registry linter, with one exception that is enforced here as well because it must never be
bypassed: an ``IN_FORCE`` obligation needs ``verification: PRIMARY_TEXT_READ`` and a
``signed_off_by`` (CLAUDE.md hard rule 1).
"""

from datetime import date
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from abhiyogah.domain.complaint import ComplaintFacts
from abhiyogah.domain.enums import (
    BasisStatus,
    DayBasis,
    Deontic,
    EntityType,
    RuleStatus,
    Verification,
)
from abhiyogah.domain.events import EventType

__all__ = [
    "OBLIGATION_ID_PATTERN",
    "AppliesTo",
    "ClockPause",
    "ClockSpec",
    "Obligation",
    "ParameterValue",
    "Trigger",
]

OBLIGATION_ID_PATTERN = r"^[A-Z][A-Z0-9]*(-[A-Za-z0-9]+)+$"
"""``<SOURCE>-<YEAR>-<CLAUSE>``, for example ``IO-CB-2026-14-1-b`` or ``TAT-2019-UPI-P2P``."""

_DATE_FACTS = frozenset(
    name for name in ComplaintFacts.model_fields if name.endswith(("_date", "_date_t", "_date_r"))
)


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AppliesTo(_Strict):
    """Applicability profile: which regulated entities the obligation binds."""

    entity_type: EntityType | list[EntityType]
    min_outlets: int | None = Field(default=None, ge=0)
    outlets_as_on: date | None = None

    def entity_types(self) -> list[EntityType]:
        """The entity types as a list."""
        return self.entity_type if isinstance(self.entity_type, list) else [self.entity_type]


class Trigger(_Strict):
    """The event (and optional condition over complaint facts) that makes the obligation bite."""

    event: EventType
    condition: str | None = Field(
        default=None, description="Condition over ComplaintFacts, e.g. 'outcome in [...]'."
    )


class ClockPause(_Strict):
    """A pause rule. No obligation may use one until open question Q3 is resolved by the owner."""

    on: EventType
    resume: EventType
    open_question: str = Field(description="Open-question ID authorising the pause, e.g. 'Q3'.")


class ClockSpec(_Strict):
    """When the clock starts and stops, and how its days are counted.

    ``start`` is an event type, or the name of a ``ComplaintFacts`` date field when the anchor is a
    fact rather than an event (for example ``transaction_date_t`` for the failed-transaction TAT).
    ``stop`` lists the events that stop the clock; any one of them is enough.
    """

    start: EventType | str
    stop: list[EventType] = Field(default_factory=list)
    basis: DayBasis
    basis_status: BasisStatus
    tz: Literal["Asia/Kolkata"] = "Asia/Kolkata"
    pause: ClockPause | None = None

    @field_validator("start")
    @classmethod
    def _start_is_event_or_date_fact(cls, v: EventType | str) -> EventType | str:
        """A non-event start must name a ComplaintFacts date field."""
        if v in EventType.__members__:
            return EventType(v)
        if v in _DATE_FACTS:
            return v
        raise ValueError(f"clock start {v!r} is neither an EventType nor a ComplaintFacts date")

    @field_validator("stop", mode="before")
    @classmethod
    def _stop_as_list(cls, v: object) -> object:
        """Accept a single stop event as well as a list."""
        return [] if v is None else [v] if isinstance(v, str) else v


class ParameterValue(_Strict):
    """One dated value of a rule parameter."""

    value: JsonValue
    reference: str = Field(min_length=1, description="Clause or source of this value.")
    verification: Verification
    open_question: str | None = Field(
        default=None, description="Open-question ID when the value is flagged, e.g. 'Q5'."
    )


class Obligation(_Strict):
    """One obligation file. Field order mirrors the report's example YAML."""

    obligation_id: str = Field(pattern=OBLIGATION_ID_PATTERN)
    deontic: Deontic
    subject: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    instrument_ref: str | None = None
    clause: str = Field(min_length=1)
    source_url: AnyHttpUrl
    applies_to: AppliesTo
    trigger: Trigger
    clock: ClockSpec | None = None
    anchor: str | None = Field(
        default=None,
        description="ComplaintFacts date that selects parameter versions; default: clock start.",
    )
    parameters: dict[str, dict[date, ParameterValue]] = Field(default_factory=dict)
    overridden_by: list[str] = Field(default_factory=list)
    valid_from: date
    valid_to: date | None = None
    status: RuleStatus
    verification: Verification
    signed_off_by: str | None = None
    supersedes_note: str | None = None
    tests: list[str] = Field(default_factory=list)

    @field_validator("anchor")
    @classmethod
    def _anchor_is_date_fact(cls, v: str | None) -> str | None:
        """The anchor must name a ComplaintFacts date field."""
        if v is not None and v not in _DATE_FACTS:
            raise ValueError(f"anchor {v!r} is not a ComplaintFacts date field")
        return v

    @field_validator("parameters")
    @classmethod
    def _parameters_have_history(
        cls, v: dict[str, dict[date, ParameterValue]]
    ) -> dict[str, dict[date, ParameterValue]]:
        """Every parameter has at least one dated value."""
        empty = [name for name, history in v.items() if not history]
        if empty:
            raise ValueError(f"parameters without any dated value: {empty}")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        """Validity dates are ordered; IN_FORCE requires primary-text verification and sign-off."""
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to is before valid_from")
        if self.status is RuleStatus.IN_FORCE and (
            self.verification is not Verification.PRIMARY_TEXT_READ or not self.signed_off_by
        ):
            raise ValueError("IN_FORCE needs verification PRIMARY_TEXT_READ and signed_off_by")
        return self
