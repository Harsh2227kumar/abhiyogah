"""API and worker settings, read from the environment once at start-up.

- ``DATABASE_URL``: PostgreSQL URL; unset means an in-memory store (demo and tests only).
- ``ABHIYOGAH_API_KEYS``: ``"<actor>:<role>:<key>;..."`` (see ``api.auth``). Unset: every call 401.
- ``ABHIYOGAH_RULES_DIR``: obligation YAML directory, default ``rules/obligations``.
- ``ABHIYOGAH_PROFILE``: the entity profile as JSON, e.g.
  ``{"entity_type": "COMMERCIAL_BANK", "outlets": 120, "outlets_as_on": "2025-03-31"}``.
  Default: a commercial bank with an unknown outlet count, so outlet-gated obligations report
  ``INSUFFICIENT_FACTS`` rather than assume one.
- ``ABHIYOGAH_REEVALUATE_MINUTES``: scheduler period, default 15.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from abhiyogah.domain.enums import EntityType
from abhiyogah.evaluator import EntityProfile

__all__ = ["Settings"]

DEFAULT_RULES_DIR = Path("rules/obligations")


@dataclass(frozen=True)
class Settings:
    """Start-up configuration."""

    database_url: str | None = None
    api_keys: str = ""
    rules_dir: Path = DEFAULT_RULES_DIR
    profile: EntityProfile = field(
        default_factory=lambda: EntityProfile(entity_type=EntityType.COMMERCIAL_BANK)
    )
    reevaluate_minutes: int = 15

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """Read the settings from environment variables."""
        profile = env.get("ABHIYOGAH_PROFILE")
        return cls(
            database_url=env.get("DATABASE_URL") or None,
            api_keys=env.get("ABHIYOGAH_API_KEYS", ""),
            rules_dir=Path(env.get("ABHIYOGAH_RULES_DIR", str(DEFAULT_RULES_DIR))),
            profile=(
                EntityProfile.model_validate_json(profile)
                if profile
                else EntityProfile(entity_type=EntityType.COMMERCIAL_BANK)
            ),
            reevaluate_minutes=int(env.get("ABHIYOGAH_REEVALUATE_MINUTES", "15")),
        )
