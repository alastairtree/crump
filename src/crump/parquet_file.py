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
            # When appending, we already have a header from the existing file
            # Set it so that subsequent writerow() calls are treated as data
            self._header = self._existing_table.schema.names
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Write accumulated rows to the Parquet file.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        # Only write if no exception occurred and we have a header
        # (we write even if there are no data rows, to create an empty table with schema)
        if exc_type is None and self._header is not None:
            self._write_parquet()

        # Cleanup
        self._rows = []
        self._header = None
        self._existing_table = None

    def writerow(self, row: list[Any]) -> None:
        """Accumulate a row to be written to the Parquet file.

        The first row is treated as the header (column names).
        Subsequent rows are treated as data.

        When appending, if the first row matches the existing header,
        it is validated and skipped.

        Args:
            row: List of values to write
        """
        if self._header is None:
            # First row is the header (when creating new file)
            self._header = row
        elif self._existing_table is not None and len(self._rows) == 0:
            # When appending, the first data row might be a header row
            # If it matches the existing header, skip it (validation happens in _write_parquet)
            # If it doesn't match, treat it as data
            if row == self._header:
                # Header matches, skip it
                return
            else:
                # Not a header, treat as data
                self._rows.append(row)
        else:
            # Subsequent rows are data
            self._rows.append(row)

    def _write_parquet(self) -> None:
        """Write the accumulated rows to the Parquet file.

        Combines with existing data if appending.
        """
        if not self._header:
            raise ValueError("Cannot write Parquet file without header row")

        # If appending, use the existing table's schema for type compatibility
        if self._existing_table is not None:
            # Verify column names match
            if self._existing_table.schema.names != self._header:
                raise ValueError(
                    f"Cannot append to {self.file_path}: "
                    f"column names don't match. "
                    f"Existing: {self._existing_table.schema.names}, "
                    f"New: {self._header}"
                )

            # Use existing schema for new data
            schema = self._existing_table.schema
        else:
            # No existing schema, let PyArrow infer from data
            schema = None

        # Convert rows to PyArrow Table
        if self._rows:
            # Create a dictionary of column_name -> list_of_values
            data: dict[Any, list[Any]] = {col: [] for col in self._header}
            for row in self._rows:
                for col, value in zip(self._header, row, strict=False):
                    data[col].append(value)

            # Create PyArrow Table from dictionary with schema
            if schema is not None:
                new_table = pa.Table.from_pydict(data, schema=schema)
            else:
                new_table = pa.Table.from_pydict(data)
        else:
            # No data rows, create empty table with schema
            if schema is None:
                schema = pa.schema([(col, pa.string()) for col in self._header])
            new_table = pa.Table.from_pydict({col: [] for col in self._header}, schema=schema)

        # If appending, combine with existing table
        if self._existing_table is not None:
            # Combine tables
            combined_table = pa.concat_tables([self._existing_table, new_table])
            pq.write_table(combined_table, str(self.file_path))
        else:
            # Write new table
            pq.write_table(new_table, str(self.file_path))
