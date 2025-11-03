"""Abstract base classes for tabular file formats (CSV, Parquet, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class TabularFileReader(ABC):
    """Abstract base class for reading tabular file formats.

    Provides a common interface for reading different tabular file formats
    like CSV and Parquet. Designed to work as a context manager and iterator,
    similar to csv.DictReader.

    Example usage:
        with TabularFileReader(file_path) as reader:
            print(f"Columns: {reader.fieldnames}")
            for row in reader:
                print(row)  # row is a dict
    """

    def __init__(self, file_path: str | Path):
        """Initialize the reader with a file path.

        Args:
            file_path: Path to the file to read
        """
        self.file_path = Path(file_path)

    @abstractmethod
    def __enter__(self) -> TabularFileReader:
        """Enter context manager and prepare for reading.

        Returns:
            Self for use in with statement
        """
        pass

    @abstractmethod
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and cleanup resources.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        pass

    @property
    @abstractmethod
    def fieldnames(self) -> list[str]:
        """Get column names from the file.

        Returns:
            List of column names
        """
        pass

    @abstractmethod
    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate through rows as dictionaries.

        Yields:
            Dictionary mapping column names to values for each row
        """
        pass


class TabularFileWriter(ABC):
    """Abstract base class for writing tabular file formats.

    Provides a common interface for writing different tabular file formats
    like CSV and Parquet. Designed to work as a context manager, similar to
    csv.writer.

    Example usage:
        with TabularFileWriter(file_path, append=False) as writer:
            writer.writerow(['col1', 'col2'])  # header
            writer.writerow(['val1', 'val2'])  # data row
    """

    def __init__(self, file_path: str | Path, append: bool = False):
        """Initialize the writer with a file path.

        Args:
            file_path: Path to the file to write
            append: If True, append to existing file. If False, overwrite.
        """
        self.file_path = Path(file_path)
        self.append = append

    @abstractmethod
    def __enter__(self) -> TabularFileWriter:
        """Enter context manager and prepare for writing.

        Returns:
            Self for use in with statement
        """
        pass

    @abstractmethod
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and cleanup resources.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        pass

    @abstractmethod
    def writerow(self, row: list[Any]) -> None:
        """Write a single row to the file.

        Args:
            row: List of values to write (can be header or data row)
        """
        pass


def create_reader(file_path: str | Path, file_format: str | None = None) -> TabularFileReader:
    """Factory function to create appropriate reader based on file format.

    Args:
        file_path: Path to the file to read
        file_format: File format ('csv' or 'parquet'). If None, auto-detect from extension.

    Returns:
        TabularFileReader instance for the file format

    Raises:
        ValueError: If file format is not supported or cannot be detected
    """
    from .csv_file import CsvFileReader
    from .parquet_file import ParquetFileReader

    path = Path(file_path)

    # Auto-detect format from extension if not specified
    if file_format is None:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            file_format = "csv"
        elif suffix in [".parquet", ".pq"]:
            file_format = "parquet"
        else:
            raise ValueError(
                f"Cannot auto-detect file format from extension '{suffix}'. "
                f"Please specify file_format parameter."
            )

    # Create appropriate reader
    if file_format.lower() == "csv":
        return CsvFileReader(path)
    elif file_format.lower() == "parquet":
        return ParquetFileReader(path)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def create_writer(
    file_path: str | Path, file_format: str | None = None, append: bool = False
) -> TabularFileWriter:
    """Factory function to create appropriate writer based on file format.

    Args:
        file_path: Path to the file to write
        file_format: File format ('csv' or 'parquet'). If None, auto-detect from extension.
        append: If True, append to existing file. If False, overwrite.

    Returns:
        TabularFileWriter instance for the file format

    Raises:
        ValueError: If file format is not supported or cannot be detected
    """
    from .csv_file import CsvFileWriter
    from .parquet_file import ParquetFileWriter

    path = Path(file_path)

    # Auto-detect format from extension if not specified
    if file_format is None:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            file_format = "csv"
        elif suffix in [".parquet", ".pq"]:
            file_format = "parquet"
        else:
            raise ValueError(
                f"Cannot auto-detect file format from extension '{suffix}'. "
                f"Please specify file_format parameter."
            )

    # Create appropriate writer
    if file_format.lower() == "csv":
        return CsvFileWriter(path, append=append)
    elif file_format.lower() == "parquet":
        return ParquetFileWriter(path, append=append)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")
