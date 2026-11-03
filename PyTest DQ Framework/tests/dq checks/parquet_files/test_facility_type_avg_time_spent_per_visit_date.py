"""
Description: Data Quality checks for facility_type_avg_time_spent_per_visit_date dataset.
Requirement(s): Step 3.2
Author(s): Dyuti60
"""

import pytest


@pytest.fixture(scope="module")
def source_data(db_connection):
    source_query = """
        SELECT
            f.facility_type AS facility_type,
            v.visit_timestamp::date AS visit_date,
            ROUND(AVG(v.duration_minutes), 2) AS avg_time_spent
        FROM public.visits AS v
        JOIN public.facilities AS f
            ON v.facility_id = f.id
        GROUP BY
            f.facility_type,
            v.visit_timestamp::date
    """
    return db_connection.get_data_sql(source_query)


@pytest.fixture(scope="module")
def target_data(parquet_reader):
    target_path = "/parquet_data/facility_type_avg_time_spent_per_visit_date"
    return parquet_reader.process(target_path, include_subfolders=True)


@pytest.mark.parquet_data
@pytest.mark.smoke
@pytest.mark.facility_type_avg_time_spent_per_visit_date
def test_check_dataset_is_not_empty(target_data, data_quality_library):
    data_quality_library.check_dataset_is_not_empty(target_data)


@pytest.mark.parquet_data
@pytest.mark.facility_type_avg_time_spent_per_visit_date
def test_check_data_completeness(source_data, target_data, data_quality_library):
    data_quality_library.check_data_completeness(source_data, target_data)


@pytest.mark.parquet_data
@pytest.mark.facility_type_avg_time_spent_per_visit_date
def test_check_count(source_data, target_data, data_quality_library):
    data_quality_library.check_count(source_data, target_data)


@pytest.mark.parquet_data
@pytest.mark.facility_type_avg_time_spent_per_visit_date
def test_check_uniqueness(target_data, data_quality_library):
    data_quality_library.check_duplicates(
        target_data,
        ["facility_type", "visit_date"],
    )


@pytest.mark.parquet_data
@pytest.mark.facility_type_avg_time_spent_per_visit_date
def test_check_not_null_values(target_data, data_quality_library):
    data_quality_library.check_not_null_values(
        target_data,
        ["facility_type", "visit_date", "avg_time_spent"],
    )
