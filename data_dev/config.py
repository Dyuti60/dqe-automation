from dataclasses import dataclass
from typing import List, Tuple
from datetime import datetime


@dataclass
class PostgresConfig:
    """
    A dataclass to store PostgreSQL database configuration settings.

    Attributes:
        user (str): The username for the PostgreSQL database.
        password (str): The password for the PostgreSQL database.
        db (str): The name of the database to connect to.
        port (int): The port number on which the PostgreSQL server is running.
        host (str): The hostname or IP address of the PostgreSQL server.
    """
    user: str
    password: str
    db: str
    port: int
    host: str


@dataclass
class DataGeneratorConfig:
    """
    A dataclass to store configuration settings for a data generation process.

    Attributes:
        num_patients (int): The number of patients to generate data for.
        start_date (str): The start date for the data generation period (formatted as a string).
        end_date (str): The end date for the data generation period (formatted as a string).
        date_format (str): The format of the date strings (e.g., '%Y-%m-%d').
        facility_types (List[str]): A list of facility types (e.g., "Hospital", "Clinic").
        visits_per_day (Tuple[int, int]): A tuple specifying the range (min, max) of visits per day.
    """
    num_patients: int
    start_date: str
    end_date: str
    date_format: str
    facility_types: List[str]
    visits_per_day: Tuple[int, int]


@dataclass
class ParquetStorageConfig:
    """
    Configuration class for Parquet storage.

    Attributes:
        storage_path_facility_type_avg_time_spent_per_visit_date (str):
        The file system path where Parquet files for facility_type_avg_time_spent_per_visit_date will be stored.
        storage_path_patient_sum_treatment_cost_per_facility_type (str):
        The file system path where Parquet files for patient_sum_treatment_cost_per_facility_type will be stored.
        storage_path_facility_name_min_time_spent_per_visit_date (str):
        The file system path where Parquet files for facility_name_min_time_spent_per_visit_date will be stored.
    """
    storage_path_facility_type_avg_time_spent_per_visit_date: str
    storage_path_patient_sum_treatment_cost_per_facility_type: str
    storage_path_facility_name_min_time_spent_per_visit_date: str


@dataclass
class LoadConfig:
    """
    LoadConfig is a configuration class used to store config related to data loading processes.

    Attributes:
        last_date (str): The last date for which data should be successfully loaded.
                         This is typically used to track the progress of incremental data loads.
                         The date should be in the format 'YYYY-MM-DD'.
    """
    date_scope: str


@dataclass
class ReportGeneratorConfig:
    """
    ReportGeneratorConfig is a configuration class used to define settings for report generation.

    Attributes:
        storage_path (str): The file system path where the generated reports will be stored.
                            This path is typically a directory.
        parquet_files_path (str): Location of source files.
    """
    storage_path: str
    parquet_files_path: str


# Instance of LoadConfig
load_config = LoadConfig(
    date_scope=datetime.now().date().strftime('%Y-%m-%d')  # Example: '2025-01-01'
)

# Instance of PostgresConfig
postgres_config = PostgresConfig(
    user='myuser',
    password='mypassword',
    db='mydatabase',
    port=5438,  # localhost:5434,  podman_network:5432
    host='localhost'  # localhost:localhost, podman_network:postgres
)

# Instance of GeneratorConfig
data_generator_config = DataGeneratorConfig(
    num_patients=30,
    start_date='2000-01-01',
    end_date='2030-01-01',
    date_format='%Y-%m-%d',
    facility_types=['Hospital', 'Clinic', 'Urgent Care', 'Specialty Center'],
    visits_per_day=(7, 10)
)

# Instance of ParquetStorageConfig
parquet_storage_config = ParquetStorageConfig(
    storage_path_facility_type_avg_time_spent_per_visit_date='/parquet_data/'
                                                             'facility_type_avg_time_spent_per_visit_date',
    storage_path_patient_sum_treatment_cost_per_facility_type='/parquet_data/'
                                                              'patient_sum_treatment_cost_per_facility_type',
    storage_path_facility_name_min_time_spent_per_visit_date='/parquet_data/'
                                                             'facility_name_min_time_spent_per_visit_date'
)

# Instance of ReportGeneratorConfig
report_generator_config = ReportGeneratorConfig(
    storage_path='/generated_report',
    parquet_files_path='/parquet_data/facility_type_avg_time_spent_per_visit_date'
)
