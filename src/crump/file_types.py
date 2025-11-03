"""File type enumerations for Crump."""

from __future__ import annotations

from enum import Enum


class OutputFileType(Enum):
    """Supported output file formats for data extraction."""

    CSV = "csv"
    PARQUET = "parquet"

    @classmethod
    def from_extension(cls, extension: str) -> OutputFileType:
        """Determine output file type from file extension.

        Args:
            extension: File extension (with or without leading dot)

        Returns:
            OutputFileType enum value

        Raises:
            ValueError: If extension is not supported
        """
        ext = extension.lower().lstrip(".")
        if ext == "csv":
            return cls.CSV
        elif ext in ["parquet", "pq"]:
            return cls.PARQUET
        else:
            raise ValueError(f"Unsupported output file extension: {extension}")

    @classmethod
    def from_path(cls, path: str) -> OutputFileType:
        """Determine output file type from file path.

        Args:
            path: File path

        Returns:
            OutputFileType enum value

        Raises:
            ValueError: If path extension is not supported
        """
        from pathlib import Path

        return cls.from_extension(Path(path).suffix)


class InputFileType(Enum):
    """Supported input file formats for data processing."""

    CSV = "csv"
    PARQUET = "parquet"
    CDF = "cdf"

    @classmethod
    def from_extension(cls, extension: str, default: InputFileType | None = None) -> InputFileType:
        """Determine input file type from file extension.

        Args:
            extension: File extension (with or without leading dot)
            default: Default value to return if extension not recognized

        Returns:
            InputFileType enum value

        Raises:
            ValueError: If extension is not supported and no default provided
        """
        ext = extension.lower().lstrip(".")
        if ext == "csv":
            return cls.CSV
        elif ext in ["parquet", "pq"]:
            return cls.PARQUET
        elif ext == "cdf":
            return cls.CDF
        elif default is not None:
            return default
        else:
            raise ValueError(f"Unsupported input file extension: {extension}")

    @classmethod
    def from_path(cls, path: str, default: InputFileType | None = None) -> InputFileType:
        """Determine input file type from file path.

        Args:
            path: File path
            default: Default value to return if extension not recognized

        Returns:
            InputFileType enum value

        Raises:
            ValueError: If path extension is not supported and no default provided
        """
        from pathlib import Path

        return cls.from_extension(Path(path).suffix, default=default)
