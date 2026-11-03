"""Dataset-agnostic unit tests for the Step 1 framework components."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from src.connectors.file_system.parquet_reader import ParquetReader
from src.connectors.postgres.postgres_connector import PostgresConnectorContextManager
from src.data_quality.data_quality_validation_library import DataQualityLibrary


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = 0
        self.rollback_called = False

    def close(self) -> None:
        self.closed = 1

    def rollback(self) -> None:
        self.rollback_called = True


@pytest.mark.example
def test_postgres_connector_context_and_query(monkeypatch) -> None:
    connection = _FakeConnection()
    expected = pd.DataFrame({"value": [1]})
    monkeypatch.setattr(
        "src.connectors.postgres.postgres_connector.psycopg2.connect",
        lambda **_kwargs: connection,
    )
    monkeypatch.setattr(
        "src.connectors.postgres.postgres_connector.pd.read_sql_query",
        lambda sql, active_connection: expected
        if sql == "SELECT 1" and active_connection is connection
        else None,
    )

    with PostgresConnectorContextManager(
        db_host="postgres",
        db_name="mydatabase",
        db_port=5432,
        db_user="user",
        db_password="password",
    ) as connector:
        result = connector.get_data_sql("SELECT 1")

    pd.testing.assert_frame_equal(result, expected)
    assert connection.closed == 1
    assert connector.connection is None


@pytest.mark.example
def test_postgres_connector_rolls_back_and_closes_after_error(monkeypatch) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(
        "src.connectors.postgres.postgres_connector.psycopg2.connect",
        lambda **_kwargs: connection,
    )

    with pytest.raises(RuntimeError, match="query failed"):
        with PostgresConnectorContextManager(
            db_host="postgres",
            db_name="mydatabase",
            db_port=5432,
            db_user="user",
            db_password="password",
        ):
            raise RuntimeError("query failed")

    assert connection.rollback_called is True
    assert connection.closed == 1


@pytest.mark.example
def test_parquet_reader_reads_partition_subdirectories(tmp_path) -> None:
    partition = tmp_path / "facility_type=Clinic"
    partition.mkdir()
    pd.DataFrame({"measure": [12.5]}).to_parquet(partition / "part.parquet", index=False)

    result = ParquetReader().process(tmp_path, include_subfolders=True)

    assert result.to_dict(orient="records") == [{"measure": 12.5, "facility_type": "Clinic"}]
    assert result.attrs["parquet_partition_columns"] == ("facility_type",)
    assert result.attrs["technical_partition_columns"] == ()
    with pytest.raises(AssertionError, match=r"unexpected in actual: \['facility_type'\]"):
        DataQualityLibrary.check_data_completeness(
            pd.DataFrame({"measure": [12.5]}), result
        )


@pytest.mark.example
def test_technical_partition_column_is_preserved_but_not_compared_as_business_data(
    tmp_path,
) -> None:
    partition = tmp_path / "partition_date=2026-11-03"
    partition.mkdir()
    pd.DataFrame({"id": [1], "measure": [12.5]}).to_parquet(
        partition / "part.parquet", index=False
    )

    actual = ParquetReader().process(tmp_path, include_subfolders=True)
    expected = pd.DataFrame({"id": [1], "measure": [12.5]})

    assert "partition_date" in actual.columns
    assert actual.attrs["technical_partition_columns"] == ("partition_date",)
    DataQualityLibrary.check_data_completeness(expected, actual)


@pytest.mark.example
def test_data_quality_library_accepts_matching_data_in_any_row_order() -> None:
    expected = pd.DataFrame({"id": [1, 2], "value": ["a", "b"]})
    actual = pd.DataFrame({"value": ["b", "a"], "id": [2, 1]})

    DataQualityLibrary.check_dataset_is_not_empty(actual)
    DataQualityLibrary.check_data_completeness(expected, actual)
    DataQualityLibrary.check_count(expected, actual)
    DataQualityLibrary.check_duplicates(actual, ["id"])
    DataQualityLibrary.check_not_null_values(actual, ["id", "value"])


@pytest.mark.example
def test_completeness_preserves_duplicate_row_multiplicity() -> None:
    expected = pd.DataFrame({"id": [1, 1, 2], "value": ["a", "a", "b"]})
    reordered = pd.DataFrame({"value": ["b", "a", "a"], "id": [2, 1, 1]})
    wrong_multiplicity = pd.DataFrame({"id": [1, 2, 2], "value": ["a", "b", "b"]})

    DataQualityLibrary.check_data_completeness(expected, reordered)
    with pytest.raises(AssertionError, match="duplicate-row multiplicity"):
        DataQualityLibrary.check_data_completeness(expected, wrong_multiplicity)


@pytest.mark.example
def test_completeness_accepts_equivalent_date_representations() -> None:
    expected = pd.DataFrame({"visit_date": [date(2026, 11, 3)]})
    actual = pd.DataFrame({"visit_date": [pd.Timestamp("2026-11-03 00:00:00")]})

    DataQualityLibrary.check_data_completeness(expected, actual)


@pytest.mark.example
def test_completeness_accepts_equivalent_exact_numeric_representations() -> None:
    expected = pd.DataFrame(
        {"whole": [Decimal("12.00")], "measure": [Decimal("98.2500")]}
    )
    actual = pd.DataFrame({"whole": [np.int64(12)], "measure": [np.float64(98.25)]})

    DataQualityLibrary.check_data_completeness(expected, actual)


@pytest.mark.example
def test_completeness_rejects_genuine_numeric_precision_difference() -> None:
    expected = pd.DataFrame({"measure": [Decimal("98.2501")]})
    actual = pd.DataFrame({"measure": [np.float64(98.25)]})

    with pytest.raises(AssertionError, match="Missing row occurrences: 1"):
        DataQualityLibrary.check_data_completeness(expected, actual)


@pytest.mark.example
@pytest.mark.parametrize(
    ("actual_ids", "message"),
    [([1], "Missing row occurrences: 1"), ([1, 2, 3], "Extra row occurrences: 1")],
)
def test_completeness_reports_missing_and_extra_records(actual_ids, message) -> None:
    expected = pd.DataFrame({"id": [1, 2]})
    actual = pd.DataFrame({"id": actual_ids})

    with pytest.raises(AssertionError, match=message):
        DataQualityLibrary.check_data_completeness(expected, actual)


@pytest.mark.example
def test_duplicates_detect_business_key_collisions_when_measures_differ() -> None:
    dataframe = pd.DataFrame({"business_id": [1, 1], "measure": [10.0, 20.0]})

    DataQualityLibrary.check_duplicates(dataframe)
    with pytest.raises(AssertionError, match="business_id"):
        DataQualityLibrary.check_duplicates(dataframe, ["business_id"])


@pytest.mark.example
def test_component_test_execution_does_not_require_database_credentials() -> None:
    framework_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("DQ_DB_USER", None)
    environment.pop("DQ_DB_PASSWORD", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_framework_components.py",
            "-c",
            "tests/pytest.ini",
            "-k",
            "test_data_quality_library_accepts_matching_data_in_any_row_order",
            "-q",
        ],
        cwd=framework_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.example
@pytest.mark.parametrize(
    ("check", "message"),
    [
        (
            lambda: DataQualityLibrary.check_dataset_is_not_empty(pd.DataFrame()),
            "Dataset is empty",
        ),
        (
            lambda: DataQualityLibrary.check_count(
                pd.DataFrame({"id": [1]}), pd.DataFrame({"id": [1, 2]})
            ),
            "Row count mismatch",
        ),
        (
            lambda: DataQualityLibrary.check_data_completeness(
                pd.DataFrame({"id": [1]}), pd.DataFrame({"id": [2]})
            ),
            "Data completeness check failed",
        ),
        (
            lambda: DataQualityLibrary.check_duplicates(pd.DataFrame({"id": [1, 1]})),
            "participating in duplicates",
        ),
        (
            lambda: DataQualityLibrary.check_not_null_values(
                pd.DataFrame({"id": [None]}), ["id"]
            ),
            "Null values found",
        ),
    ],
)
def test_data_quality_failures_are_diagnostic(check, message) -> None:
    with pytest.raises(AssertionError, match=message):
        check()
