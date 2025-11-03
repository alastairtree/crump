"""Parquet file reader and writer implementations using pyarrow."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

try:
    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]
except ImportError as e:
    raise ImportError(
        "pyarrow is required for Parquet file support. Install it with: pip install pyarrow"
    ) from e

from .tabular_file import TabularFileReader, TabularFileWriter


class ParquetFileReader(TabularFileReader):
    """Parquet file reader implementation.

    Uses pyarrow to read Parquet files and provide a consistent interface
    for reading tabular data files. Reads the entire file into memory as
    a PyArrow Table, then iterates through batches for memory efficiency.
    """

    def __init__(self, file_path: str | Path):
        """Initialize Parquet file reader.

        Args:
            file_path: Path to the Parquet file
        """
        super().__init__(file_path)
        self._table: Any = None
        self._fieldnames: list[str] | None = None

    def __enter__(self) -> ParquetFileReader:
        """Open the Parquet file and read the schema.

        Returns:
            Self for use in with statement
        """
        # Read the entire Parquet file into a PyArrow Table
        self._table = pq.read_table(str(self.file_path))
        self._fieldnames = self._table.schema.names
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Cleanup resources.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        self._table = None
        self._fieldnames = None

    @property
    def fieldnames(self) -> list[str]:
        """Get column names from the Parquet file.

        Returns:
            List of column names

        Raises:
            RuntimeError: If called outside of context manager
        """
        if self._fieldnames is None:
            raise RuntimeError("Reader must be used within a context manager (with statement)")
        return self._fieldnames

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate through Parquet rows as dictionaries.

        Converts each row to a dictionary mapping column names to values.
        For memory efficiency, processes the table in batches.

        Yields:
            Dictionary mapping column names to values for each row

        Raises:
            RuntimeError: If called outside of context manager
        """
        if self._table is None:
            raise RuntimeError("Reader must be used within a context manager (with statement)")

        # Convert table to list of dictionaries
        # We use to_pylist() which converts the entire table to Python dicts
        # This is memory intensive but matches the CSV interface behavior
        yield from self._table.to_pylist()


class ParquetFileWriter(TabularFileWriter):
    """Parquet file writer implementation.

    Uses pyarrow to write Parquet files. Accumulates rows in memory
    and writes them all at once when the context manager exits.
    """

    def __init__(self, file_path: str | Path, append: bool = False):
        """Initialize Parquet file writer.

        Args:
            file_path: Path to the Parquet file
            append: If True, append to existing file. If False, overwrite.

        Note:
            Append mode for Parquet files works by reading the existing file,
            combining it with new data, and writing the result. This is less
            efficient than CSV append but maintains Parquet's columnar format.
        """
        super().__init__(file_path, append)
        self._rows: list[list[Any]] = []
        self._header: list[Any] | None = None
        self._existing_table: Any = None

    def __enter__(self) -> ParquetFileWriter:
        """Prepare for writing.

        If appending to an existing file, reads it into memory.

        Returns:
            Self for use in with statement
        """
        # If appending and file exists, read the existing data
        if self.append and self.file_path.exists():
            self._existing_table = pq.read_table(str(self.file_path))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Write accumulated rows to the Parquet file.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        # Only write if no exception occurred and we have data
        if exc_type is None and self._rows:
            self._write_parquet()

        # Cleanup
        self._rows = []
        self._header = None
        self._existing_table = None

    def writerow(self, row: list[Any]) -> None:
        """Accumulate a row to be written to the Parquet file.

        The first row is treated as the header (column names).
        Subsequent rows are treated as data.

        Args:
            row: List of values to write
        """
        if self._header is None:
            # First row is the header
            self._header = row
        else:
            # Subsequent rows are data
            self._rows.append(row)

    def _write_parquet(self) -> None:
        """Write the accumulated rows to the Parquet file.

        Combines with existing data if appending.
        """
        if not self._header:
            raise ValueError("Cannot write Parquet file without header row")

        # Convert rows to PyArrow Table
        if self._rows:
            # Create a dictionary of column_name -> list_of_values
            data: dict[Any, list[Any]] = {col: [] for col in self._header}
            for row in self._rows:
                for col, value in zip(self._header, row, strict=False):
                    data[col].append(value)

            # Create PyArrow Table from dictionary
            new_table = pa.Table.from_pydict(data)
        else:
            # No data rows, create empty table with schema
            schema = pa.schema([(col, pa.string()) for col in self._header])
            new_table = pa.Table.from_pydict({col: [] for col in self._header}, schema=schema)

        # If appending, combine with existing table
        if self._existing_table is not None:
            # Verify schemas match
            if self._existing_table.schema.names != new_table.schema.names:
                raise ValueError(
                    f"Cannot append to {self.file_path}: "
                    f"column names don't match. "
                    f"Existing: {self._existing_table.schema.names}, "
                    f"New: {new_table.schema.names}"
                )

            # Combine tables
            combined_table = pa.concat_tables([self._existing_table, new_table])
            pq.write_table(combined_table, str(self.file_path))
        else:
            # Write new table
            pq.write_table(new_table, str(self.file_path))
