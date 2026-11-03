"""Shared command-line options and session fixtures for DQ tests."""

from __future__ import annotations

import os

import pytest

from src.connectors.file_system.parquet_reader import ParquetReader
from src.connectors.postgres.postgres_connector import PostgresConnectorContextManager
from src.data_quality.data_quality_validation_library import DataQualityLibrary


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("database", "PostgreSQL connection options")
    group.addoption("--db_host", action="store", default="localhost", help="Database host")
    group.addoption(
        "--db_port",
        action="store",
        default=5438,
        type=int,
        help="Database port (local Docker Desktop default: 5438)",
    )
    group.addoption("--db_name", action="store", default="mydatabase", help="Database name")
    group.addoption("--db_user", action="store", default=None, help="Database username")
    group.addoption(
        "--db_password",
        action="store",
        default=None,
        help="Database password (use Jenkins Credentials Store in CI)",
    )


@pytest.fixture(scope="session")
def db_connection(request: pytest.FixtureRequest):
    db_user = request.config.getoption("db_user") or os.getenv("DQ_DB_USER")
    db_password = request.config.getoption("db_password") or os.getenv("DQ_DB_PASSWORD")
    missing = [
        name
        for name, value in (("database user", db_user), ("database password", db_password))
        if not value
    ]
    if missing:
        pytest.fail(
            "PostgreSQL credentials are required only by tests requesting db_connection. "
            "Provide --db_user/--db_password locally or DQ_DB_USER/DQ_DB_PASSWORD "
            f"through the environment. Missing: {', '.join(missing)}.",
            pytrace=False,
        )

    connector = PostgresConnectorContextManager(
        db_host=request.config.getoption("db_host"),
        db_name=request.config.getoption("db_name"),
        db_port=request.config.getoption("db_port"),
        db_user=db_user,
        db_password=db_password,
    )
    try:
        connector.__enter__()
    except Exception as error:
        pytest.fail(f"Failed to initialize PostgreSQL connection: {error}", pytrace=True)
    try:
        yield connector
    finally:
        connector.__exit__(None, None, None)


@pytest.fixture(scope="session")
def parquet_reader() -> ParquetReader:
    return ParquetReader()


@pytest.fixture(scope="session")
def data_quality_library() -> DataQualityLibrary:
    return DataQualityLibrary()
