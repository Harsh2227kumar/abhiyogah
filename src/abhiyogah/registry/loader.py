"""Load the rule pack: every ``rules/obligations/*.yaml`` into ``Obligation`` models.

Files whose name starts with ``_`` are skipped (notes and templates). Two files with the same
``obligation_id`` are an error, so the pack can never hold two competing versions of a rule.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from abhiyogah.registry.errors import DuplicateObligationError, ObligationFileError
from abhiyogah.registry.schema import Obligation

__all__ = ["Registry", "load_obligation", "load_registry", "obligation_files"]

type Registry = dict[str, Obligation]
"""Obligations keyed by ``obligation_id``."""


def obligation_files(directory: Path) -> list[Path]:
    """The obligation YAML files in ``directory``, sorted by name, skipping ``_*`` files."""
    return sorted(p for p in directory.glob("*.yaml") if not p.name.startswith("_"))


def load_obligation(path: Path) -> Obligation:
    """Parse and validate one obligation file."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ObligationFileError(path, f"cannot read YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ObligationFileError(path, "top level is not a mapping")
    try:
        return Obligation.model_validate(data)
    except ValidationError as exc:
        raise ObligationFileError(path, str(exc)) from exc


def load_registry(directory: Path) -> Registry:
    """Load every obligation in ``directory``; a duplicate ``obligation_id`` is an error."""
    registry: Registry = {}
    origin: dict[str, Path] = {}
    for path in obligation_files(directory):
        ob = load_obligation(path)
        if ob.obligation_id in registry:
            raise DuplicateObligationError(ob.obligation_id, origin[ob.obligation_id], path)
        registry[ob.obligation_id] = ob
        origin[ob.obligation_id] = path
    return registry
