"""Smoke test that the package imports."""

import abhiyogah


def test_package_has_version() -> None:
    """The package exposes a version string."""
    assert abhiyogah.__version__
