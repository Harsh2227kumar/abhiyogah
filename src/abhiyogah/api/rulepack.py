"""Loading the rule pack for the API and worker.

Uses the registry loader (``abhiyogah.registry.loader.load_registry``) when the rule-pack stream
has delivered it; until then, a minimal fallback reads every ``*.yaml`` (skipping ``_*`` files) into
``Obligation`` and refuses duplicate IDs, which is the loader's documented contract.
"""

import importlib
from collections.abc import Callable
from pathlib import Path

import yaml

from abhiyogah.registry.schema import Obligation

__all__ = ["load_obligations"]


def _fallback(directory: Path) -> dict[str, Obligation]:
    """Read ``*.yaml`` into obligations keyed by ID; duplicates are an error."""
    out: dict[str, Obligation] = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        ob = Obligation.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if ob.obligation_id in out:
            raise ValueError(f"duplicate obligation {ob.obligation_id} in {path}")
        out[ob.obligation_id] = ob
    return out


def _registry_loader() -> Callable[[Path], dict[str, Obligation]] | None:
    """The registry's ``load_registry``, if it exists yet."""
    try:
        module = importlib.import_module("abhiyogah.registry.loader")
    except ModuleNotFoundError:
        return None
    loader: Callable[[Path], dict[str, Obligation]] = module.load_registry
    return loader


def load_obligations(directory: Path) -> list[Obligation]:
    """Every obligation under ``directory``, sorted by ID; none if the directory is missing."""
    if not directory.is_dir():
        return []
    load = _registry_loader() or _fallback
    registry = load(directory)
    return [registry[k] for k in sorted(registry)]
