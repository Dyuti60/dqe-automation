"""PostgreSQL connector used by the data-quality test fixtures."""

from __future__ import annotations

from types import TracebackType

import pandas as pd
import psycopg2
from psycopg2.extensions import connection as PostgreSQLConnection


class PostgresConnectorContextManager:
    """Own a PostgreSQL connection and expose query results as DataFrames."""

    def __init__(
        self,
        *,
        db_host: str,
        db_name: str,
        db_port: int,
        db_user: str,
        db_password: str,
    ) -> None:
        self.db_host = db_host
        self.db_name = db_name
        self.db_port = int(db_port)
        self.db_user = db_user
        self.db_password = db_password
        self.connection: PostgreSQLConnection | None = None

    def __enter__(self) -> PostgresConnectorContextManager:
        self.connection = psycopg2.connect(
            host=self.db_host,
            dbname=self.db_name,
            port=self.db_port,
            user=self.db_user,
            password=self.db_password,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self.connection is not None and not self.connection.closed:
            if exc_type is not None:
                self.connection.rollback()
            self.connection.close()
        self.connection = None
        return False

    def get_data_sql(self, sql: str) -> pd.DataFrame:
        """Execute a SQL query on the active connection and return its rows."""

        if self.connection is None or self.connection.closed:
            raise RuntimeError(
                "PostgreSQL connection is not open. Use the connector as a context manager."
            )
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("SQL query must be a non-empty string.")
        return pd.read_sql_query(sql, self.connection)
