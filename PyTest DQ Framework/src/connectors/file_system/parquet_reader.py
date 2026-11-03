"""File-system connector for Parquet datasets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class ParquetReader:
    """Read a Parquet file or a directory-backed Parquet dataset."""

    def process(
        self,
        file_path: str | Path,
        *,
        include_subfolders: bool = False,
    ) -> pd.DataFrame:
        """Return Parquet data, optionally including partition subdirectories."""

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Parquet path does not exist: {path}")

        if path.is_file():
            if path.suffix.lower() != ".parquet":
                raise ValueError(f"Expected a .parquet file, got: {path}")
            return pd.read_parquet(path, engine="pyarrow")

        pattern = "**/*.parquet" if include_subfolders else "*.parquet"
        parquet_files = sorted(path.glob(pattern))
        if not parquet_files:
            scope = "including subdirectories" if include_subfolders else "in the directory"
            raise FileNotFoundError(f"No Parquet files found {scope}: {path}")

        if include_subfolders:
            # Reading the dataset root lets PyArrow restore Hive partition columns.
            dataframe = pd.read_parquet(path, engine="pyarrow")
            partition_columns = sorted(
                {
                    part.split("=", 1)[0]
                    for parquet_file in parquet_files
                    for part in parquet_file.relative_to(path).parts[:-1]
                    if "=" in part
                }
            )
            dataframe.attrs["parquet_partition_columns"] = tuple(partition_columns)
            # Keep every restored partition column in the returned data. Mark only
            # conventionally technical fields so completeness can exclude those
            # from a business-column comparison without hiding mapped columns.
            dataframe.attrs["technical_partition_columns"] = tuple(
                column
                for column in partition_columns
                if column.startswith("partition_") or column.endswith("_partition")
            )
            return dataframe

        frames = [pd.read_parquet(parquet_file, engine="pyarrow") for parquet_file in parquet_files]
        return pd.concat(frames, ignore_index=True)
