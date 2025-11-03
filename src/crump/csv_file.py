"""CSV file reader and writer implementations."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .tabular_file import TabularFileReader, TabularFileWriter


class CsvFileReader(TabularFileReader):
    """CSV file reader implementation.

    Wraps Python's csv.DictReader to provide a consistent interface
    for reading tabular data files.
    """

    def __init__(self, file_path: str | Path, encoding: str = "utf-8", errors: str = "strict"):
        """Initialize CSV file reader.

        Args:
            file_path: Path to the CSV file
            encoding: Character encoding (default: utf-8)
            errors: How to handle encoding errors (default: strict, can be 'replace')
        """
        super().__init__(file_path)
        self.encoding = encoding
        self.errors = errors
        self._file_handle: Any = None
        self._reader: csv.DictReader[str] | None = None

    def __enter__(self) -> CsvFileReader:
        """Open the CSV file and create a DictReader.

        Returns:
            Self for use in with statement
        """
        self._file_handle = open(self.file_path, encoding=self.encoding, errors=self.errors)
        self._reader = csv.DictReader(self._file_handle)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the CSV file.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
            self._reader = None

    @property
    def fieldnames(self) -> list[str]:
        """Get column names from the CSV file.

        Returns:
            List of column names

        Raises:
            RuntimeError: If called outside of context manager
        """
        if self._reader is None:
            raise RuntimeError("Reader must be used within a context manager (with statement)")
        return list(self._reader.fieldnames or [])

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate through CSV rows as dictionaries.

        Yields:
            Dictionary mapping column names to values for each row

        Raises:
            RuntimeError: If called outside of context manager
        """
        if self._reader is None:
            raise RuntimeError("Reader must be used within a context manager (with statement)")
        yield from self._reader


class CsvFileWriter(TabularFileWriter):
    """CSV file writer implementation.

    Wraps Python's csv.writer to provide a consistent interface
    for writing tabular data files.
    """

    def __init__(self, file_path: str | Path, append: bool = False, encoding: str = "utf-8"):
        """Initialize CSV file writer.

        Args:
            file_path: Path to the CSV file
            append: If True, append to existing file. If False, overwrite.
            encoding: Character encoding (default: utf-8)
        """
        super().__init__(file_path, append)
        self.encoding = encoding
        self._file_handle: Any = None
        self._writer: Any = None

    def __enter__(self) -> CsvFileWriter:
        """Open the CSV file and create a writer.

        Returns:
            Self for use in with statement
        """
        mode = "a" if self.append and self.file_path.exists() else "w"
        self._file_handle = open(self.file_path, mode, newline="", encoding=self.encoding)
        self._writer = csv.writer(self._file_handle)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the CSV file.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
            self._writer = None

    def writerow(self, row: list[Any]) -> None:
        """Write a single row to the CSV file.

        Args:
            row: List of values to write

        Raises:
            RuntimeError: If called outside of context manager
        """
        if self._writer is None:
            raise RuntimeError("Writer must be used within a context manager (with statement)")
        self._writer.writerow(row)
