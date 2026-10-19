"""The regulated entity a complaint is against, used for applicability checks."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from abhiyogah.domain.enums import EntityType

__all__ = ["EntityProfile"]


class EntityProfile(BaseModel):
    """Entity type, outlet count (with its as-on date) and default home-branch state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: EntityType
    outlets: int | None = Field(default=None, ge=0)
    outlets_as_on: date | None = None
    home_branch_state: str | None = Field(
        default=None,
        description="Used when the complaint has no home_branch_state fact of its own.",
    )
