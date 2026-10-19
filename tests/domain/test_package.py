"""Smoke tests that the package and every subpackage import."""

import importlib

import pytest

import abhiyogah

SUBPACKAGES = [
    "domain",
    "registry",
    "calendar",
    "clocks",
    "evaluator",
    "calculators",
    "workflow",
    "ledger",
    "store",
    "api",
    "worker",
    "perception",
    "mcp",
    "regwatch",
    "reporting",
]


def test_package_has_version() -> None:
    """The package exposes a version string."""
    assert abhiyogah.__version__


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports_with_docstring(name: str) -> None:
    """Each subpackage imports and documents itself."""
    module = importlib.import_module(f"abhiyogah.{name}")
    assert module.__doc__
