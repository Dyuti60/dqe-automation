"""Tests for the contents of ``src/data/data.csv``."""

from __future__ import annotations

import re
from typing import Any

import pytest


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


def _row_for_id(rows: list[dict[str, str]], player_id: int) -> dict[str, str]:
    matching_rows = [row for row in rows if row["id"] == str(player_id)]
    assert matching_rows, f"Expected one row for id={player_id}, but no row was found"
    assert len(matching_rows) == 1, (
        f"Expected one row for id={player_id}, but found {len(matching_rows)} rows"
    )
    return matching_rows[0]


def _parse_boolean(value: str, player_id: int) -> bool:
    normalized_value = value.strip().lower()
    assert normalized_value in {"true", "false"}, (
        f"Expected is_active for id={player_id} to be True or False, got {value!r}"
    )
    return normalized_value == "true"


def test_file_not_empty(csv_file_data: dict[str, Any]) -> None:
    rows = csv_file_data["rows"]
    assert rows, f"CSV file contains a header but no data rows: {csv_file_data['path']}"


@pytest.mark.validate_csv
def test_validate_schema(validate_schema: bool) -> None:
    assert validate_schema, "CSV schema validation fixture did not return a successful result"


@pytest.mark.validate_csv
@pytest.mark.skip(reason="Age validation is intentionally skipped for this assignment")
def test_age_column_valid(csv_file_data: dict[str, Any]) -> None:
    for row_number, row in enumerate(csv_file_data["rows"], start=2):
        try:
            age = int(row["age"])
        except (TypeError, ValueError) as error:
            pytest.fail(
                f"Row {row_number} has a non-integer age value: {row['age']!r}",
                pytrace=False,
            )
            raise AssertionError from error

        assert 0 <= age <= 100, (
            f"Row {row_number} has age {age}; expected an integer from 0 through 100"
        )


@pytest.mark.validate_csv
def test_email_column_valid(csv_file_data: dict[str, Any]) -> None:
    for row_number, row in enumerate(csv_file_data["rows"], start=2):
        assert EMAIL_PATTERN.fullmatch(row["email"]), (
            f"Row {row_number} has an invalid email address: {row['email']!r}"
        )


@pytest.mark.validate_csv
@pytest.mark.xfail(reason="The supplied CSV contains a known duplicate row", strict=False)
def test_no_duplicate_rows(csv_file_data: dict[str, Any]) -> None:
    rows = csv_file_data["rows"]
    normalized_rows = [tuple(row.items()) for row in rows]
    assert len(normalized_rows) == len(set(normalized_rows)), (
        "CSV contains duplicate data rows; every row must be unique"
    )


@pytest.mark.parametrize("player_id, expected_is_active", [(1, False), (2, True)])
def test_active_players(
    csv_file_data: dict[str, Any], player_id: int, expected_is_active: bool
) -> None:
    row = _row_for_id(csv_file_data["rows"], player_id)
    actual_is_active = _parse_boolean(row["is_active"], player_id)
    assert actual_is_active is expected_is_active, (
        f"Expected is_active={expected_is_active} for id={player_id}, "
        f"got {actual_is_active}"
    )


def test_active_player_without_parametrize(csv_file_data: dict[str, Any]) -> None:
    player_id = 2
    expected_is_active = True
    row = _row_for_id(csv_file_data["rows"], player_id)
    actual_is_active = _parse_boolean(row["is_active"], player_id)
    assert actual_is_active is expected_is_active, (
        f"Expected is_active={expected_is_active} for id={player_id}, "
        f"got {actual_is_active}"
    )
