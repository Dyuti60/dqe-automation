"""Focused unit tests for Plotly table extraction."""

from unittest.mock import Mock

import pandas as pd
import pytest
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from helper import (
    HtmlTableExtractionError,
    ParquetDataError,
    compare_dataframes,
    read_html_table,
    read_parquet_data,
)


def _cell(value: str, y_position: int) -> Mock:
    cell = Mock()
    text_element = Mock()
    text_element.text = value
    cell.find_element.return_value = text_element
    cell.get_attribute.return_value = f"translate(0,{y_position})"
    return cell


def _column(header_text: str, values: list[str]) -> Mock:
    header = Mock()
    header_text_element = Mock()
    header_text_element.text = header_text
    header.find_element.return_value = header_text_element

    block = Mock()
    block.get_attribute.return_value = "translate(0,100)"
    # Reverse DOM order to prove that SVG positions determine row order.
    cells = [_cell(value, index * 20) for index, value in enumerate(values)]
    block.find_elements.return_value = list(reversed(cells))

    column = Mock()
    column.find_element.return_value = header
    column.find_elements.return_value = [block]
    return column


def test_read_html_table_reconstructs_rows_and_preserves_duplicates() -> None:
    table = Mock()
    table.find_elements.return_value = [
        _column("Facility Type", ["Hospital", "Clinic", "Hospital"]),
        _column("Visit Date", ["2026-10-11", "2026-10-10", "2026-10-11"]),
        _column("Average Time Spent", ["42.2", "59", "42.2"]),
    ]

    result = read_html_table(table)

    expected = pd.DataFrame(
        {
            "Facility Type": ["Hospital", "Clinic", "Hospital"],
            "Visit Date": ["2026-10-11", "2026-10-10", "2026-10-11"],
            "Average Time Spent": ["42.2", "59", "42.2"],
        },
        dtype="string",
    )
    pd.testing.assert_frame_equal(result, expected)
    table.find_elements.assert_called_once_with(By.CLASS_NAME, "y-column")


def test_read_html_table_rejects_missing_header() -> None:
    malformed_column = Mock()
    malformed_column.find_element.side_effect = NoSuchElementException()
    table = Mock()
    table.find_elements.return_value = [malformed_column, Mock(), Mock()]

    with pytest.raises(HtmlTableExtractionError, match="Header is missing"):
        read_html_table(table)


def test_read_html_table_rejects_inconsistent_column_lengths() -> None:
    table = Mock()
    table.find_elements.return_value = [
        _column("Facility Type", ["Hospital", "Clinic"]),
        _column("Visit Date", ["2026-10-11"]),
        _column("Average Time Spent", ["42.2", "59"]),
    ]

    with pytest.raises(HtmlTableExtractionError, match="inconsistent data lengths"):
        read_html_table(table)


@pytest.fixture
def parquet_folder(tmp_path):
    folder = tmp_path / "report_data"
    source = pd.DataFrame(
        {
            "facility_type": [
                "Hospital",
                "Clinic",
                "Hospital",
                "Clinic",
                "Hospital",
            ],
            "visit_date": pd.to_datetime(
                [
                    "2026-01-03",
                    "2026-01-04",
                    "2026-01-05",
                    "2026-01-10",
                    "2026-01-10",
                ]
            ),
            "avg_time_spent": [99.0, 10.0, 12.5, 9.25, 15.0],
        }
    )
    source["partition_date"] = source["visit_date"].dt.strftime("%Y-%m")
    source.to_parquet(
        folder,
        engine="pyarrow",
        partition_cols=["partition_date"],
        index=False,
    )
    return folder


def test_read_parquet_data_uses_default_seven_day_window(parquet_folder) -> None:
    result = read_parquet_data(parquet_folder)

    expected = pd.DataFrame(
        {
            "Facility Type": ["Hospital", "Clinic", "Hospital", "Clinic"],
            "Visit Date": [
                "2026-01-10",
                "2026-01-10",
                "2026-01-05",
                "2026-01-04",
            ],
            "Average Time Spent": ["15", "9.25", "12.5", "10"],
        },
        dtype="string",
    )
    pd.testing.assert_frame_equal(result, expected)


def test_read_parquet_data_filters_one_exact_date(parquet_folder) -> None:
    result = read_parquet_data(parquet_folder, "2026-01-10")

    assert result.to_dict(orient="records") == [
        {
            "Facility Type": "Hospital",
            "Visit Date": "2026-01-10",
            "Average Time Spent": "15",
        },
        {
            "Facility Type": "Clinic",
            "Visit Date": "2026-01-10",
            "Average Time Spent": "9.25",
        },
    ]


@pytest.mark.parametrize("filter_date", ["2026/01/10", "2026-02-30"])
def test_read_parquet_data_rejects_malformed_dates(
    parquet_folder,
    filter_date,
) -> None:
    with pytest.raises(ParquetDataError, match="Invalid filter date"):
        read_parquet_data(parquet_folder, filter_date)


def test_read_parquet_data_rejects_empty_filter_results(parquet_folder) -> None:
    with pytest.raises(ParquetDataError, match="contains no rows for date"):
        read_parquet_data(parquet_folder, "2025-01-01")


def test_read_parquet_data_rejects_missing_folder(tmp_path) -> None:
    with pytest.raises(ParquetDataError, match="folder does not exist"):
        read_parquet_data(tmp_path / "missing")


def test_read_parquet_data_rejects_missing_schema(tmp_path) -> None:
    folder = tmp_path / "bad_schema"
    pd.DataFrame(
        {
            "facility_type": ["Hospital"],
            "partition_date": ["2026-01"],
        }
    ).to_parquet(folder, engine="pyarrow", partition_cols=["partition_date"])

    with pytest.raises(ParquetDataError, match="missing required columns"):
        read_parquet_data(folder)


def _comparison_frame(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=[
        "Facility Type",
        "Visit Date",
        "Average Time Spent",
    ])


def test_compare_dataframes_accepts_exact_match() -> None:
    html = _comparison_frame([("Hospital", "2026-10-11", "42.2")])
    parquet = html.astype("string")

    is_match, differences = compare_dataframes(html, parquet)

    assert is_match is True
    assert "match exactly" in differences


def test_compare_dataframes_ignores_row_order() -> None:
    rows = [
        ("Hospital", "2026-10-11", "42.2"),
        ("Clinic", "2026-10-10", "59"),
    ]

    is_match, _ = compare_dataframes(
        _comparison_frame(rows),
        _comparison_frame(list(reversed(rows))),
    )

    assert is_match is True


def test_compare_dataframes_reports_value_mismatch() -> None:
    html = _comparison_frame([("Hospital", "2026-10-11", "42.2")])
    parquet = _comparison_frame([("Hospital", "2026-10-11", "42.3")])

    is_match, differences = compare_dataframes(html, parquet)

    assert is_match is False
    assert "42.2" in differences
    assert "42.3" in differences
    assert "missing=1, extra=1" in differences


def test_compare_dataframes_reports_missing_row() -> None:
    html = _comparison_frame(
        [
            ("Hospital", "2026-10-11", "42.2"),
            ("Clinic", "2026-10-10", "59"),
        ]
    )
    parquet = html.iloc[:1].copy()

    is_match, differences = compare_dataframes(html, parquet)

    assert is_match is False
    assert "Row counts differ: HTML=2, Parquet=1" in differences
    assert "Missing from Parquet" in differences


def test_compare_dataframes_preserves_duplicate_counts() -> None:
    row = ("Hospital", "2026-10-11", "42.2")
    html = _comparison_frame([row, row])
    parquet = _comparison_frame([row])

    is_match, differences = compare_dataframes(html, parquet)

    assert is_match is False
    assert "Missing from Parquet: 1 occurrence" in differences
    assert "count=1" in differences


def test_compare_dataframes_reports_schema_mismatch() -> None:
    html = _comparison_frame([("Hospital", "2026-10-11", "42.2")])
    parquet = html[["Visit Date", "Facility Type", "Average Time Spent"]]

    is_match, differences = compare_dataframes(html, parquet)

    assert is_match is False
    assert "Schema mismatch" in differences
    assert "order differs" in differences


def test_compare_dataframes_handles_empty_dataframes() -> None:
    html = _comparison_frame([])
    parquet = _comparison_frame([]).astype("string")

    is_match, differences = compare_dataframes(html, parquet)

    assert is_match is True
    assert "0 row occurrence" in differences
