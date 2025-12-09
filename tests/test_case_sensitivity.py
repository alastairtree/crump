"""Tests for case sensitivity in table and index names."""

import csv
from pathlib import Path

from crump.config import (
    ColumnMapping,
    CrumpJob,
    Index,
    IndexColumn,
)
from crump.database import DatabaseConnection, sync_file_to_db_dry_run


def test_mixed_case_table_name_index_detection(db_url: str, tmp_path: Path) -> None:
    """Test that indexes are correctly detected on tables with mixed case names.

    This is a regression test for the bug where dry-run would incorrectly report
    that indexes need to be created when they already exist, if the table name
    had mixed case characters.

    The bug occurred because PostgreSQL stores table names with their original case
    (when quoted as identifiers) in system catalogs (pg_indexes, information_schema.tables,
    information_schema.columns), but the queries were using case-sensitive comparison.
    """
    # Create a CSV file
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["time_met_iso", "data"])
        writer.writeheader()
        writer.writerow({"time_met_iso": "2024-01-01T00:00:00", "data": "value1"})
        writer.writerow({"time_met_iso": "2024-01-02T00:00:00", "data": "value2"})

    # Create job with mixed case table name and indexes
    job = CrumpJob(
        name="test_job",
        target_table="HskProcStat",  # Mixed case table name
        id_mapping=[ColumnMapping("time_met_iso", "time_met_iso")],
        columns=[ColumnMapping("data", "data")],
        indexes=[
            Index("idx_time_met_iso", [IndexColumn("time_met_iso", "ASC")]),
        ],
    )

    # First sync - create table and indexes
    with DatabaseConnection(db_url) as db:
        rows = db.sync_tabular_file(csv_file, job)
        assert rows == 2

        # Verify indexes were created
        indexes = db.get_existing_indexes(job.target_table)
        assert "idx_time_met_iso" in indexes

    # Run dry-run - should NOT suggest creating indexes again
    summary = sync_file_to_db_dry_run(csv_file, job, db_url)

    assert summary.table_exists
    assert len(summary.new_columns) == 0
    # This is the key assertion - dry-run should NOT report the index as new
    assert len(summary.new_indexes) == 0, (
        f"Dry-run incorrectly reports indexes as new: {summary.new_indexes}. "
        f"This is a regression of the case sensitivity bug."
    )


def test_lowercase_table_name_works(db_url: str, tmp_path: Path) -> None:
    """Test that lowercase table names still work correctly."""
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name"])
        writer.writeheader()
        writer.writerow({"id": "1", "name": "Alice"})

    job = CrumpJob(
        name="test_job",
        target_table="lowercase_table",
        id_mapping=[ColumnMapping("id", "id")],
        columns=[ColumnMapping("name", "name")],
        indexes=[Index("idx_name", [IndexColumn("name", "ASC")])],
    )

    # Sync and verify
    with DatabaseConnection(db_url) as db:
        rows = db.sync_tabular_file(csv_file, job)
        assert rows == 1

    # Dry-run should not report new indexes
    summary = sync_file_to_db_dry_run(csv_file, job, db_url)
    assert summary.table_exists
    assert len(summary.new_indexes) == 0


def test_uppercase_table_name_works(db_url: str, tmp_path: Path) -> None:
    """Test that uppercase table names work correctly."""
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "value"])
        writer.writeheader()
        writer.writerow({"id": "1", "value": "100"})

    job = CrumpJob(
        name="test_job",
        target_table="UPPERCASE_TABLE",
        id_mapping=[ColumnMapping("id", "id")],
        columns=[ColumnMapping("value", "value")],
        indexes=[Index("idx_value", [IndexColumn("value", "ASC")])],
    )

    # Sync and verify
    with DatabaseConnection(db_url) as db:
        rows = db.sync_tabular_file(csv_file, job)
        assert rows == 1

    # Dry-run should not report new indexes
    summary = sync_file_to_db_dry_run(csv_file, job, db_url)
    assert summary.table_exists
    assert len(summary.new_indexes) == 0


def test_get_existing_columns_case_insensitive(db_url: str, tmp_path: Path) -> None:
    """Test that get_existing_columns works correctly with mixed case table names."""
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "email"])
        writer.writeheader()
        writer.writerow({"id": "1", "name": "Alice", "email": "alice@example.com"})

    job = CrumpJob(
        name="test_job",
        target_table="MixedCaseTable",
        id_mapping=[ColumnMapping("id", "id")],
        columns=[
            ColumnMapping("name", "name"),
            ColumnMapping("email", "email"),
        ],
    )

    # Create the table
    with DatabaseConnection(db_url) as db:
        db.sync_tabular_file(csv_file, job)

    # Check that we can get existing columns
    with DatabaseConnection(db_url) as db:
        columns = db.get_existing_columns("MixedCaseTable")
        assert "id" in columns
        assert "name" in columns
        assert "email" in columns
