"""Reusable assertion-based checks for pandas DataFrames."""

from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Sequence
from datetime import date, datetime
from decimal import Decimal
import math
from numbers import Integral, Real

import numpy as np
import pandas as pd


class DataQualityLibrary:
    """Provide diagnostic data-quality assertions for PyTest modules."""

    @staticmethod
    def _require_dataframe(dataframe: pd.DataFrame, argument_name: str) -> None:
        assert isinstance(dataframe, pd.DataFrame), (
            f"{argument_name} must be a pandas DataFrame, "
            f"got {type(dataframe).__name__}."
        )

    @staticmethod
    def _require_columns(dataframe: pd.DataFrame, column_names: Sequence[str]) -> list[str]:
        columns = list(column_names)
        assert columns, "At least one column name must be supplied."
        missing = [column for column in columns if column not in dataframe.columns]
        assert not missing, (
            f"Columns required for the data-quality check are missing: {missing}. "
            f"Available columns: {list(dataframe.columns)}."
        )
        return columns

    @staticmethod
    def _is_null(value: object) -> bool:
        """Return whether a scalar value is null without treating containers as scalars."""

        try:
            result = pd.isna(value)
        except (TypeError, ValueError):
            return False
        return isinstance(result, (bool, np.bool_)) and bool(result)

    @classmethod
    def _canonical_value(cls, value: object) -> Hashable:
        """Normalize source/target scalar representations without losing precision."""

        if cls._is_null(value):
            return ("null",)
        if isinstance(value, (pd.Timestamp, np.datetime64, datetime)):
            timestamp = pd.Timestamp(value)
            if (
                timestamp.tzinfo is None
                and timestamp.hour == 0
                and timestamp.minute == 0
                and timestamp.second == 0
                and timestamp.microsecond == 0
                and timestamp.nanosecond == 0
            ):
                return ("date", timestamp.date().isoformat())
            return ("datetime", timestamp.isoformat())
        if isinstance(value, date):
            return ("date", value.isoformat())
        if isinstance(value, (bool, np.bool_)):
            return ("bool", bool(value))
        if isinstance(value, Decimal):
            if not value.is_finite():
                return ("number", str(value))
            return ("number", value)
        if isinstance(value, Integral):
            return ("number", Decimal(int(value)))
        if isinstance(value, Real):
            numeric = float(value)
            if math.isinf(numeric):
                return ("number", "Infinity" if numeric > 0 else "-Infinity")
            # Decimal(str(...)) compares the represented value exactly. No
            # rounding or tolerance is applied, so genuine precision defects fail.
            return ("number", Decimal(str(value)))
        if isinstance(value, Hashable):
            return (type(value).__name__, value)
        return (type(value).__name__, repr(value))

    @classmethod
    def _row_counter(
        cls,
        dataframe: pd.DataFrame,
        columns: Sequence[str],
    ) -> Counter[tuple[Hashable, ...]]:
        return Counter(
            tuple(cls._canonical_value(value) for value in row)
            for row in dataframe.loc[:, list(columns)].itertuples(index=False, name=None)
        )

    @staticmethod
    def _counter_sample(counter: Counter[tuple[Hashable, ...]]) -> list[dict[str, object]]:
        return [
            {"row": row, "occurrences": occurrences}
            for row, occurrences in counter.most_common(5)
        ]

    @classmethod
    def check_data_completeness(
        cls,
        df_expected: pd.DataFrame,
        df_actual: pd.DataFrame,
    ) -> None:
        """Assert that expected and actual contain the same data, ignoring row order."""

        cls._require_dataframe(df_expected, "df_expected")
        cls._require_dataframe(df_actual, "df_actual")
        expected_columns = list(df_expected.columns)
        actual_columns = list(df_actual.columns)
        assert len(expected_columns) == len(set(expected_columns)), (
            f"Expected data contains duplicate column names: {expected_columns}."
        )
        assert len(actual_columns) == len(set(actual_columns)), (
            f"Actual data contains duplicate column names: {actual_columns}."
        )
        expected_column_set = set(expected_columns)
        actual_column_set = set(actual_columns)
        technical_columns = set(df_actual.attrs.get("technical_partition_columns", ()))
        ignored_technical_columns = (actual_column_set - expected_column_set) & technical_columns
        missing_columns = expected_column_set - actual_column_set
        unexpected_columns = (
            actual_column_set - expected_column_set - ignored_technical_columns
        )
        assert not missing_columns and not unexpected_columns, (
            "Data completeness column mismatch. "
            f"Missing from actual: {sorted(missing_columns)}; "
            f"unexpected in actual: {sorted(unexpected_columns)}; "
            "technical Parquet partition columns retained but excluded from the "
            f"business comparison: {sorted(ignored_technical_columns)}."
        )

        expected_rows = cls._row_counter(df_expected, expected_columns)
        actual_rows = cls._row_counter(df_actual, expected_columns)
        missing_rows = expected_rows - actual_rows
        extra_rows = actual_rows - expected_rows
        assert not missing_rows and not extra_rows, (
            "Data completeness check failed after ignoring row order while preserving "
            "duplicate-row multiplicity. Values were compared exactly after safe date "
            "and numeric representation normalization. "
            f"Expected rows: {len(df_expected)}; actual rows: {len(df_actual)}. "
            f"Missing row occurrences: {sum(missing_rows.values())}; "
            f"sample: {cls._counter_sample(missing_rows)}. "
            f"Extra row occurrences: {sum(extra_rows.values())}; "
            f"sample: {cls._counter_sample(extra_rows)}. "
            "Comparison columns: "
            f"{expected_columns}; ignored technical partition columns: "
            f"{sorted(ignored_technical_columns)}."
        )

    @classmethod
    def check_count(cls, df_expected: pd.DataFrame, df_actual: pd.DataFrame) -> None:
        """Assert that expected and actual contain the same number of rows."""

        cls._require_dataframe(df_expected, "df_expected")
        cls._require_dataframe(df_actual, "df_actual")
        expected_count = len(df_expected)
        actual_count = len(df_actual)
        assert expected_count == actual_count, (
            "Row count mismatch: "
            f"expected {expected_count} rows, actual dataset contains {actual_count} rows."
        )

    @classmethod
    def check_duplicates(
        cls,
        dataframe: pd.DataFrame,
        column_names: Sequence[str] | None = None,
    ) -> None:
        """Assert that a DataFrame has no duplicate rows for the selected grain."""

        cls._require_dataframe(dataframe, "dataframe")
        columns = None if column_names is None else cls._require_columns(dataframe, column_names)
        duplicate_mask = dataframe.duplicated(subset=columns, keep=False)
        duplicates = dataframe.loc[duplicate_mask]
        grain = columns or list(dataframe.columns)
        assert duplicates.empty, (
            f"Found {len(duplicates)} rows participating in duplicates for columns {grain}. "
            f"Duplicate sample: {duplicates.head(10).to_dict(orient='records')}."
        )

    @classmethod
    def check_not_null_values(
        cls,
        dataframe: pd.DataFrame,
        column_names: Sequence[str],
    ) -> None:
        """Assert that selected columns contain no null values."""

        cls._require_dataframe(dataframe, "dataframe")
        columns = cls._require_columns(dataframe, column_names)
        null_counts = dataframe[columns].isna().sum()
        failing_counts = {
            column: int(count) for column, count in null_counts.items() if int(count) > 0
        }
        assert not failing_counts, (
            f"Null values found in required columns: {failing_counts}. "
            "Counts are reported per column."
        )

    @classmethod
    def check_dataset_is_not_empty(cls, dataframe: pd.DataFrame) -> None:
        """Assert that the target dataset contains at least one row."""

        cls._require_dataframe(dataframe, "dataframe")
        assert not dataframe.empty, (
            f"Dataset is empty. Columns discovered: {list(dataframe.columns)}."
        )
