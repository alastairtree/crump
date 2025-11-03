"""Tests for tabular file readers and writers."""

from pathlib import Path

import pytest

from crump.csv_file import CsvFileReader, CsvFileWriter
from crump.parquet_file import ParquetFileReader, ParquetFileWriter
from crump.tabular_file import create_reader, create_writer


def test_csv_reader_basic(tmp_path: Path) -> None:
    """Test basic CSV reading functionality."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA\n")

    with CsvFileReader(csv_file) as reader:
        assert reader.fieldnames == ["name", "age", "city"]
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0] == {"name": "Alice", "age": "30", "city": "NYC"}
        assert rows[1] == {"name": "Bob", "age": "25", "city": "LA"}


def test_csv_writer_basic(tmp_path: Path) -> None:
    """Test basic CSV writing functionality."""
    csv_file = tmp_path / "test.csv"

    with CsvFileWriter(csv_file) as writer:
        writer.writerow(["name", "age", "city"])
        writer.writerow(["Alice", 30, "NYC"])
        writer.writerow(["Bob", 25, "LA"])

    # Read back and verify
    content = csv_file.read_text()
    assert "name,age,city" in content
    assert "Alice,30,NYC" in content
    assert "Bob,25,LA" in content


def test_csv_append(tmp_path: Path) -> None:
    """Test appending to CSV file."""
    csv_file = tmp_path / "test.csv"

    # Write initial data
    with CsvFileWriter(csv_file) as writer:
        writer.writerow(["name", "age"])
        writer.writerow(["Alice", 30])

    # Append more data
    with CsvFileWriter(csv_file, append=True) as writer:
        writer.writerow(["Bob", 25])

    # Verify
    with CsvFileReader(csv_file) as reader:
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[1]["name"] == "Bob"


def test_parquet_reader_basic(tmp_path: Path) -> None:
    """Test basic Parquet reading functionality."""
    parquet_file = tmp_path / "test.parquet"

    # First write some data
    with ParquetFileWriter(parquet_file) as writer:
        writer.writerow(["name", "age", "city"])
        writer.writerow(["Alice", 30, "NYC"])
        writer.writerow(["Bob", 25, "LA"])

    # Now read it back
    with ParquetFileReader(parquet_file) as reader:
        assert reader.fieldnames == ["name", "age", "city"]
        rows = list(reader)
        assert len(rows) == 2
        # Parquet preserves types, so age will be int
        assert rows[0]["name"] == "Alice"
        assert rows[0]["age"] == 30
        assert rows[0]["city"] == "NYC"
        assert rows[1]["name"] == "Bob"
        assert rows[1]["age"] == 25
        assert rows[1]["city"] == "LA"


def test_parquet_writer_basic(tmp_path: Path) -> None:
    """Test basic Parquet writing functionality."""
    parquet_file = tmp_path / "test.parquet"

    with ParquetFileWriter(parquet_file) as writer:
        writer.writerow(["name", "age", "city"])
        writer.writerow(["Alice", 30, "NYC"])
        writer.writerow(["Bob", 25, "LA"])

    # Verify file exists and has content
    assert parquet_file.exists()
    assert parquet_file.stat().st_size > 0


def test_parquet_append(tmp_path: Path) -> None:
    """Test appending to Parquet file."""
    parquet_file = tmp_path / "test.parquet"

    # Write initial data
    with ParquetFileWriter(parquet_file) as writer:
        writer.writerow(["name", "age"])
        writer.writerow(["Alice", 30])

    # Append more data
    with ParquetFileWriter(parquet_file, append=True) as writer:
        writer.writerow(["name", "age"])  # Header again
        writer.writerow(["Bob", 25])

    # Verify
    with ParquetFileReader(parquet_file) as reader:
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[0]["age"] == 30
        assert rows[1]["name"] == "Bob"
        assert rows[1]["age"] == 25


def test_create_reader_csv_auto_detect(tmp_path: Path) -> None:
    """Test auto-detection of CSV files."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("col1,col2\nval1,val2\n")

    with create_reader(csv_file) as reader:
        assert reader.fieldnames == ["col1", "col2"]
        rows = list(reader)
        assert len(rows) == 1


def test_create_reader_parquet_auto_detect(tmp_path: Path) -> None:
    """Test auto-detection of Parquet files."""
    parquet_file = tmp_path / "test.parquet"

    # Create a parquet file
    with create_writer(parquet_file) as writer:
        writer.writerow(["col1", "col2"])
        writer.writerow(["val1", "val2"])

    # Read with auto-detection
    with create_reader(parquet_file) as reader:
        assert reader.fieldnames == ["col1", "col2"]
        rows = list(reader)
        assert len(rows) == 1


def test_create_reader_explicit_format(tmp_path: Path) -> None:
    """Test explicit format specification."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("col1\nval1\n")

    with create_reader(csv_file, file_format="csv") as reader:
        assert reader.fieldnames == ["col1"]


def test_create_writer_csv_auto_detect(tmp_path: Path) -> None:
    """Test auto-detection for CSV writer."""
    csv_file = tmp_path / "test.csv"

    with create_writer(csv_file) as writer:
        writer.writerow(["col1", "col2"])
        writer.writerow(["val1", "val2"])

    assert csv_file.exists()
    content = csv_file.read_text()
    assert "col1,col2" in content


def test_create_writer_parquet_auto_detect(tmp_path: Path) -> None:
    """Test auto-detection for Parquet writer."""
    parquet_file = tmp_path / "test.parquet"

    with create_writer(parquet_file) as writer:
        writer.writerow(["col1", "col2"])
        writer.writerow(["val1", "val2"])

    assert parquet_file.exists()
    assert parquet_file.stat().st_size > 0


def test_create_reader_unsupported_format(tmp_path: Path) -> None:
    """Test that unsupported formats default to CSV for backward compatibility."""
    # Create a CSV file with .txt extension
    bad_file = tmp_path / "test.txt"
    bad_file.write_text("col1,col2\nval1,val2\n")

    # Should default to CSV format for unknown extensions
    with create_reader(bad_file) as reader:
        assert reader.fieldnames == ["col1", "col2"]
        rows = list(reader)
        assert len(rows) == 1


def test_create_writer_unsupported_format(tmp_path: Path) -> None:
    """Test that unsupported formats raise ValueError."""
    bad_file = tmp_path / "test.txt"

    with pytest.raises(ValueError, match="Unsupported output file extension"):
        create_writer(bad_file)


def test_csv_reader_empty_file(tmp_path: Path) -> None:
    """Test CSV reader with empty file."""
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("")

    with CsvFileReader(csv_file) as reader:
        assert reader.fieldnames == []
        rows = list(reader)
        assert len(rows) == 0


def test_csv_reader_outside_context_manager(tmp_path: Path) -> None:
    """Test that using reader outside context manager raises error."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("col1\nval1\n")

    reader = CsvFileReader(csv_file)
    with pytest.raises(RuntimeError, match="must be used within a context manager"):
        _ = reader.fieldnames


def test_csv_writer_outside_context_manager(tmp_path: Path) -> None:
    """Test that using writer outside context manager raises error."""
    csv_file = tmp_path / "test.csv"

    writer = CsvFileWriter(csv_file)
    with pytest.raises(RuntimeError, match="must be used within a context manager"):
        writer.writerow(["col1"])


def test_parquet_reader_outside_context_manager(tmp_path: Path) -> None:
    """Test that using Parquet reader outside context manager raises error."""
    parquet_file = tmp_path / "test.parquet"

    # Create file first
    with create_writer(parquet_file) as writer:
        writer.writerow(["col1"])
        writer.writerow(["val1"])

    reader = ParquetFileReader(parquet_file)
    with pytest.raises(RuntimeError, match="must be used within a context manager"):
        _ = reader.fieldnames


def test_roundtrip_csv_to_parquet(tmp_path: Path) -> None:
    """Test reading CSV and writing to Parquet."""
    csv_file = tmp_path / "input.csv"
    parquet_file = tmp_path / "output.parquet"

    # Create CSV
    csv_file.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA\n")

    # Read CSV and write to Parquet
    with create_reader(csv_file) as csv_reader, create_writer(parquet_file) as parquet_writer:
        # Write header
        parquet_writer.writerow(csv_reader.fieldnames)
        # Write data rows
        for row in csv_reader:
            parquet_writer.writerow([row[col] for col in csv_reader.fieldnames])

    # Verify Parquet file
    with create_reader(parquet_file) as reader:
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"


def test_roundtrip_parquet_to_csv(tmp_path: Path) -> None:
    """Test reading Parquet and writing to CSV."""
    parquet_file = tmp_path / "input.parquet"
    csv_file = tmp_path / "output.csv"

    # Create Parquet
    with create_writer(parquet_file) as writer:
        writer.writerow(["name", "age", "city"])
        writer.writerow(["Alice", 30, "NYC"])
        writer.writerow(["Bob", 25, "LA"])

    # Read Parquet and write to CSV
    with create_reader(parquet_file) as parquet_reader, create_writer(csv_file) as csv_writer:
        # Write header
        csv_writer.writerow(parquet_reader.fieldnames)
        # Write data rows
        for row in parquet_reader:
            csv_writer.writerow([row[col] for col in parquet_reader.fieldnames])

    # Verify CSV file
    with create_reader(csv_file) as reader:
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[0]["age"] == "30"  # CSV converts to string
