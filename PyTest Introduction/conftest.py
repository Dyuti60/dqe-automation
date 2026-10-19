"""Shared fixtures and collection hooks for the CSV validation tests."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def path_to_file() -> Path:
    """Return the CSV path independently of the current working directory."""

    return PROJECT_ROOT / "src" / "data" / "data.csv"


@pytest.fixture(scope="session")
def csv_file_data(path_to_file: Path) -> dict[str, Any]:
    """Read the configured CSV file once and return its schema and rows."""

    assert path_to_file.is_file(), f"CSV file was not found: {path_to_file}"

    with path_to_file.open(mode="r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return {
            "path": path_to_file,
            "fieldnames": reader.fieldnames or [],
            "rows": list(reader),
        }


@pytest.fixture(scope="session")
def actual_schema(csv_file_data: dict[str, Any]) -> list[str]:
    """Return the schema read from the CSV header."""

    return csv_file_data["fieldnames"]


@pytest.fixture(scope="session")
def expected_schema() -> list[str]:
    """Return the schema required by the assignment."""

    return ["id", "name", "age", "email", "is_active"]


@pytest.fixture(scope="session")
def validate_schema(actual_schema: list[str], expected_schema: list[str]) -> bool:
    """Validate the actual CSV schema and make the result reusable by tests."""

    assert actual_schema == expected_schema, (
        f"CSV schema mismatch: expected {expected_schema}, got {actual_schema}"
    )
    return True


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply the custom ``unmarked`` mark to tests with no explicit marks."""

    for item in items:
        if not list(item.iter_markers()):
            item.add_marker(pytest.mark.unmarked)
