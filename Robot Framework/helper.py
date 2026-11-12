"""Python keywords and utilities for the Robot Framework assignment."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import math
from pathlib import Path
import re

import pandas as pd
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement


EXPECTED_HEADERS = (
    "Facility Type",
    "Visit Date",
    "Average Time Spent",
)
_TRANSLATE_Y = re.compile(
    r"translate\(\s*[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
    r"(?:\s*,\s*|\s+)"
    r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\)"
)


class HtmlTableExtractionError(ValueError):
    """Raised when the rendered Plotly table is incomplete or malformed."""


class ParquetDataError(ValueError):
    """Raised when source Parquet data cannot produce a valid report dataset."""


def _vertical_position(element: WebElement) -> float:
    """Return the SVG element's translated Y position."""

    transform = element.get_attribute("transform") or ""
    if not transform:
        return 0.0

    match = _TRANSLATE_Y.search(transform)
    if match is None:
        raise HtmlTableExtractionError(
            f"Unsupported Plotly SVG transform: {transform!r}."
        )
    return float(match.group(1))


def _read_column(column: WebElement, column_number: int) -> list[str]:
    """Read one Plotly column in visual order, excluding its header."""

    blocks = column.find_elements(
        By.CSS_SELECTOR,
        ".column-block[id^='cells']",
    )
    if not blocks:
        raise HtmlTableExtractionError(
            f"Column {column_number} contains no Plotly data-cell blocks."
        )

    positioned_values: list[tuple[float, str]] = []
    for block in blocks:
        cells = block.find_elements(By.CSS_SELECTOR, ".column-cell")
        if not cells:
            raise HtmlTableExtractionError(
                f"Column {column_number} contains an empty data-cell block."
            )

        block_position = _vertical_position(block)
        for cell in cells:
            try:
                text_element = cell.find_element(By.CSS_SELECTOR, ".cell-text")
            except NoSuchElementException as error:
                raise HtmlTableExtractionError(
                    f"Column {column_number} contains a cell with no text element."
                ) from error

            value = text_element.text.strip()
            if not value:
                raise HtmlTableExtractionError(
                    f"Column {column_number} contains a missing or empty cell value."
                )
            positioned_values.append(
                (block_position + _vertical_position(cell), value)
            )

    positioned_values.sort(key=lambda item: item[0])
    return [value for _, value in positioned_values]


def read_html_table(table_element: WebElement) -> pd.DataFrame:
    """Extract the supplied Plotly SVG table into a string-valued DataFrame."""

    columns = table_element.find_elements(By.CLASS_NAME, "y-column")
    if len(columns) != len(EXPECTED_HEADERS):
        raise HtmlTableExtractionError(
            f"Expected {len(EXPECTED_HEADERS)} Plotly columns, found {len(columns)}."
        )

    headers: list[str] = []
    values_by_column: list[list[str]] = []
    for index, column in enumerate(columns, start=1):
        try:
            header = column.find_element(By.ID, "header")
            header_text = header.find_element(
                By.CSS_SELECTOR,
                ".cell-text",
            ).text.strip()
        except NoSuchElementException as error:
            raise HtmlTableExtractionError(
                f"Header is missing from Plotly column {index}."
            ) from error

        if not header_text:
            raise HtmlTableExtractionError(
                f"Header is empty for Plotly column {index}."
            )
        headers.append(header_text)
        values_by_column.append(_read_column(column, index))

    if tuple(headers) != EXPECTED_HEADERS:
        raise HtmlTableExtractionError(
            f"Unexpected Plotly headers {headers}; expected {list(EXPECTED_HEADERS)}."
        )

    column_lengths = [len(values) for values in values_by_column]
    if len(set(column_lengths)) != 1:
        raise HtmlTableExtractionError(
            f"Plotly columns have inconsistent data lengths: {column_lengths}."
        )
    if not column_lengths or column_lengths[0] == 0:
        raise HtmlTableExtractionError("The Plotly table contains no data rows.")

    return pd.DataFrame(dict(zip(headers, values_by_column, strict=True))).astype(
        "string"
    )


def _parse_filter_date(filter_date: str) -> pd.Timestamp:
    """Parse a strict YYYY-MM-DD filter value."""

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", filter_date):
        raise ParquetDataError(
            f"Invalid filter date {filter_date!r}; expected YYYY-MM-DD."
        )
    try:
        return pd.Timestamp(datetime.strptime(filter_date, "%Y-%m-%d").date())
    except ValueError as error:
        raise ParquetDataError(
            f"Invalid filter date {filter_date!r}; expected a real calendar date."
        ) from error


def _format_report_number(value: object) -> str:
    """Match Plotly's observed number display without applying new rounding."""

    number = float(value)
    if not math.isfinite(number):
        raise ParquetDataError(
            f"Average Time Spent contains a non-finite value: {value!r}."
        )
    text = str(number)
    return text[:-2] if text.endswith(".0") else text


def read_parquet_data(
    folder: str | Path,
    filter_date: str | None = None,
) -> pd.DataFrame:
    """Load and transform the partitioned source data shown in the report."""

    folder_path = Path(folder).expanduser()
    if not folder_path.is_dir():
        raise ParquetDataError(
            f"Parquet dataset folder does not exist: {folder_path}."
        )

    try:
        source = pd.read_parquet(folder_path, engine="pyarrow")
    except Exception as error:
        raise ParquetDataError(
            f"Failed to read partitioned Parquet dataset {folder_path}: {error}"
        ) from error

    required_columns = {
        "facility_type",
        "visit_date",
        "avg_time_spent",
        "partition_date",
    }
    missing_columns = sorted(required_columns.difference(source.columns))
    if missing_columns:
        raise ParquetDataError(
            f"Parquet dataset is missing required columns: {missing_columns}."
        )

    data = source.loc[
        :, ["facility_type", "visit_date", "avg_time_spent"]
    ].copy()
    if data.empty:
        raise ParquetDataError("The Parquet dataset contains no rows.")
    if data["facility_type"].isna().any():
        raise ParquetDataError("facility_type contains missing values.")

    try:
        data["visit_date"] = pd.to_datetime(data["visit_date"], errors="raise")
    except (TypeError, ValueError) as error:
        raise ParquetDataError("visit_date contains invalid timestamp values.") from error
    if data["visit_date"].isna().any():
        raise ParquetDataError("visit_date contains missing values.")
    data["visit_date"] = data["visit_date"].dt.normalize()

    try:
        data["avg_time_spent"] = pd.to_numeric(
            data["avg_time_spent"], errors="raise"
        )
    except (TypeError, ValueError) as error:
        raise ParquetDataError("avg_time_spent contains invalid numeric values.") from error
    if data["avg_time_spent"].isna().any():
        raise ParquetDataError("avg_time_spent contains missing values.")

    if filter_date is None or (
        isinstance(filter_date, str) and not filter_date.strip()
    ):
        maximum_date = pd.Timestamp(data["visit_date"].max())
        minimum_date = maximum_date - timedelta(days=6)
        filtered = data[data["visit_date"].between(minimum_date, maximum_date)]
        filter_description = (
            f"default window {minimum_date:%Y-%m-%d} through "
            f"{maximum_date:%Y-%m-%d}"
        )
    else:
        if not isinstance(filter_date, str):
            raise ParquetDataError("filter_date must be a YYYY-MM-DD string or None.")
        selected_date = _parse_filter_date(filter_date.strip())
        filtered = data[data["visit_date"] == selected_date]
        filter_description = f"date {selected_date:%Y-%m-%d}"

    if filtered.empty:
        raise ParquetDataError(
            f"The Parquet dataset contains no rows for {filter_description}."
        )

    result = filtered.sort_values(
        by=["visit_date", "facility_type"],
        ascending=[False, False],
        kind="stable",
    ).reset_index(drop=True)
    result["visit_date"] = result["visit_date"].dt.strftime("%Y-%m-%d")
    result["avg_time_spent"] = result["avg_time_spent"].map(
        _format_report_number
    )
    result = result.rename(
        columns={
            "facility_type": "Facility Type",
            "visit_date": "Visit Date",
            "avg_time_spent": "Average Time Spent",
        }
    )
    return result.loc[:, list(EXPECTED_HEADERS)].astype("string")


def _normalize_comparison_value(value: object) -> str | None:
    """Normalize scalar representation without changing its displayed value."""

    missing = pd.isna(value)
    if isinstance(missing, bool) and missing:
        return None
    return str(value)


def _row_counter(dataframe: pd.DataFrame) -> Counter[tuple[str | None, ...]]:
    """Return a duplicate-preserving multiset of normalized rows."""

    return Counter(
        tuple(_normalize_comparison_value(value) for value in row)
        for row in dataframe.itertuples(index=False, name=None)
    )


def _format_row(
    columns: list[object],
    row: tuple[str | None, ...],
) -> str:
    values = ", ".join(
        f"{column!s}={value!r}" for column, value in zip(columns, row, strict=True)
    )
    return "{" + values + "}"


def _format_row_difference(
    label: str,
    differences: Counter[tuple[str | None, ...]],
    columns: list[object],
    sample_limit: int = 5,
) -> str:
    total = sum(differences.values())
    ordered = sorted(differences.items(), key=lambda item: repr(item[0]))
    samples = "; ".join(
        f"count={count} {_format_row(columns, row)}"
        for row, count in ordered[:sample_limit]
    )
    omitted = len(ordered) - sample_limit
    suffix = f"; {omitted} additional unique row(s) omitted" if omitted > 0 else ""
    return (
        f"{label}: {total} occurrence(s) across {len(differences)} unique row(s). "
        f"Sample: {samples}{suffix}."
    )


def compare_dataframes(
    html_df: pd.DataFrame,
    parquet_df: pd.DataFrame,
) -> tuple[bool, str]:
    """Compare report and Parquet rows exactly while ignoring row order."""

    if not isinstance(html_df, pd.DataFrame) or not isinstance(
        parquet_df, pd.DataFrame
    ):
        raise TypeError("html_df and parquet_df must both be pandas DataFrames.")

    html_columns = list(html_df.columns)
    parquet_columns = list(parquet_df.columns)
    if html_columns != parquet_columns:
        details = [
            "Schema mismatch.",
            f"HTML columns: {html_columns!r}.",
            f"Parquet columns: {parquet_columns!r}.",
        ]
        html_column_counts = Counter(html_columns)
        parquet_column_counts = Counter(parquet_columns)
        missing_columns = list((html_column_counts - parquet_column_counts).elements())
        extra_columns = list((parquet_column_counts - html_column_counts).elements())
        if missing_columns:
            details.append(f"Missing from Parquet: {missing_columns!r}.")
        if extra_columns:
            details.append(f"Extra in Parquet: {extra_columns!r}.")
        if not missing_columns and not extra_columns:
            details.append("Column names match, but their order differs.")
        return False, " ".join(details)

    html_rows = _row_counter(html_df)
    parquet_rows = _row_counter(parquet_df)
    if html_rows == parquet_rows:
        return (
            True,
            f"DataFrames match exactly: {len(html_df)} row occurrence(s), "
            f"{len(html_columns)} column(s).",
        )

    missing_rows = html_rows - parquet_rows
    extra_rows = parquet_rows - html_rows
    details = ["Data mismatch."]
    if len(html_df) != len(parquet_df):
        details.append(
            f"Row counts differ: HTML={len(html_df)}, Parquet={len(parquet_df)}."
        )
    details.append(
        "Value differences are represented by missing and extra row occurrences."
    )
    if missing_rows:
        details.append(
            _format_row_difference(
                "Missing from Parquet",
                missing_rows,
                html_columns,
            )
        )
    if extra_rows:
        details.append(
            _format_row_difference(
                "Extra in Parquet",
                extra_rows,
                html_columns,
            )
        )
    details.append(
        "Mismatch totals: "
        f"missing={sum(missing_rows.values())}, "
        f"extra={sum(extra_rows.values())}."
    )
    return False, " ".join(details)
