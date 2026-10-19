"""Shared pytest configuration: skips `db`-marked tests when DATABASE_URL is unset."""

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip tests marked `db` unless a DATABASE_URL is configured."""
    if os.environ.get("DATABASE_URL"):
        return
    skip_db = pytest.mark.skip(reason="DATABASE_URL is not set")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)
