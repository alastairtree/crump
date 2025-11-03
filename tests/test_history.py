"""Tests for sync history tracking."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crump.config import CrumpConfig
from crump.database import DatabaseConnection, sync_file_to_db
from crump.history import (
    SyncHistoryEntry,
    _calculate_file_hash,
    _ensure_history_table_exists,
    get_utc_now,
    record_sync_history,
)
from tests.db_test_utils import execute_query, get_table_columns
from tests.test_helpers import create_config_file, create_csv_file


class TestHistoryUtils:
    """Unit tests for history utility functions."""

    def test_calculate_file_hash(self, tmp_path: Path) -> None:
        """Test file hash calculation."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("id,name\n1,Alice\n2,Bob\n")

        hash1 = _calculate_file_hash(test_file)
        assert len(hash1) == 64  # SHA256 produces 64 hex characters
        assert hash1.isalnum()

        # Same file should produce same hash
        hash2 = _calculate_file_hash(test_file)
        assert hash1 == hash2

        # Different content should produce different hash
        test_file.write_text("id,name\n1,Alice\n2,Charlie\n")
        hash3 = _calculate_file_hash(test_file)
        assert hash1 != hash3

    def test_get_utc_now(self) -> None:
        """Test UTC timestamp generation."""
        now = get_utc_now()
        assert now.tzinfo == UTC
        assert isinstance(now, datetime)

    def test_sync_history_entry(self) -> None:
        """Test SyncHistoryEntry creation."""
        timestamp = datetime.now(UTC)
        entry = SyncHistoryEntry(
            timestamp=timestamp,
            filename="test.csv",
            table_name="test_table",
            rows_upserted=10,
            rows_deleted=2,
            data_hash="abc123",
            schema_changed=True,
            duration_seconds=1.5,
            success=True,
            error=None,
        )

        assert entry.timestamp == timestamp
        assert entry.filename == "test.csv"
        assert entry.table_name == "test_table"
        assert entry.rows_upserted == 10
        assert entry.rows_deleted == 2
        assert entry.data_hash == "abc123"
        assert entry.schema_changed is True
        assert entry.duration_seconds == 1.5
        assert entry.success is True
        assert entry.error is None

    def test_sync_history_entry_with_error(self) -> None:
        """Test SyncHistoryEntry with error."""
        timestamp = datetime.now(UTC)
        entry = SyncHistoryEntry(
            timestamp=timestamp,
            filename="test.csv",
            table_name="test_table",
            rows_upserted=0,
            rows_deleted=0,
            data_hash="abc123",
            schema_changed=False,
            duration_seconds=0.5,
            success=False,
            error="Test error message",
        )

        assert entry.success is False
        assert entry.error == "Test error message"
        assert entry.table_name == "test_table"


class TestHistoryIntegration:
    """Integration tests for history tracking with real databases."""

    def test_ensure_history_table_exists(self, db_url: str) -> None:
        """Test history table creation."""
        with DatabaseConnection(db_url) as db:
            assert db.backend is not None
            _ensure_history_table_exists(db.backend)

            # Verify table was created
            assert db.table_exists("_crump_history")

            # Verify columns
            columns = get_table_columns(db_url, "_crump_history")
            assert "timestamp" in columns
            assert "filename" in columns
            assert "table_name" in columns
            assert "rows_upserted" in columns
            assert "rows_deleted" in columns
            assert "data_hash" in columns
            assert "schema_changed" in columns
            assert "duration_seconds" in columns
            assert "success" in columns
            assert "error" in columns

    def test_record_sync_history_success(self, tmp_path: Path, db_url: str) -> None:
        """Test recording a successful sync to history."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("id,name\n1,Alice\n")

        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(microseconds=500000)

        with DatabaseConnection(db_url) as db:
            assert db.backend is not None
            record_sync_history(
                backend=db.backend,
                file_path=test_file,
                table_name="test_table",
                rows_upserted=1,
                rows_deleted=0,
                schema_changed=True,
                start_time=start_time,
                end_time=end_time,
                success=True,
                error=None,
            )

        # Verify history record
        rows = execute_query(
            db_url,
            "SELECT filename, table_name, rows_upserted, rows_deleted, schema_changed, success, error "
            "FROM _crump_history ORDER BY timestamp DESC LIMIT 1",
        )
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == "test.csv"  # filename
        assert row[1] == "test_table"  # table_name
        assert row[2] == 1  # rows_upserted
        assert row[3] == 0  # rows_deleted
        # SQLite stores booleans as 0/1, PostgreSQL stores as True/False
        assert row[4] in (True, 1)  # schema_changed (BOOLEAN)
        assert row[5] in (True, 1)  # success (BOOLEAN)
        assert row[6] is None  # error

    def test_record_sync_history_failure(self, tmp_path: Path, db_url: str) -> None:
        """Test recording a failed sync to history."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("id,name\n1,Alice\n")

        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(microseconds=100000)

        with DatabaseConnection(db_url) as db:
            assert db.backend is not None
            record_sync_history(
                backend=db.backend,
                file_path=test_file,
                table_name="test_table",
                rows_upserted=0,
                rows_deleted=0,
                schema_changed=False,
                start_time=start_time,
                end_time=end_time,
                success=False,
                error="Test error message",
            )

        # Verify history record
        rows = execute_query(
            db_url,
            "SELECT filename, table_name, rows_upserted, success, error "
            "FROM _crump_history ORDER BY timestamp DESC LIMIT 1",
        )
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == "test.csv"
        assert row[1] == "test_table"
        assert row[2] == 0
        # SQLite stores booleans as 0/1, PostgreSQL stores as True/False
        assert row[3] in (False, 0)  # success
        assert row[4] == "Test error message"

    def test_sync_with_history_enabled(self, tmp_path: Path, db_url: str) -> None:
        """Test that sync records history when history is enabled."""
        csv_file = tmp_path / "data.csv"
        create_csv_file(
            csv_file, ["id", "name"], [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
        )

        config_file = tmp_path / "config.yml"
        create_config_file(config_file, "test_job", "test_table", {"id": "id"})

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None

        # Sync with history enabled
        rows_synced = sync_file_to_db(csv_file, job, db_url, enable_history=True)
        assert rows_synced == 2

        # Verify history was recorded
        rows = execute_query(db_url, "SELECT COUNT(*) FROM _crump_history")
        assert rows[0][0] == 1

        # Verify history details
        history_rows = execute_query(
            db_url,
            "SELECT filename, table_name, rows_upserted, rows_deleted, schema_changed, success, error "
            "FROM _crump_history ORDER BY timestamp DESC LIMIT 1",
        )
        assert len(history_rows) == 1
        row = history_rows[0]
        assert row[0] == "data.csv"
        assert row[1] == "test_table"  # table_name
        assert row[2] == 2  # rows_upserted
        assert row[3] == 0  # rows_deleted
        # SQLite stores booleans as 0/1, PostgreSQL stores as True/False
        assert row[4] in (True, 1)  # schema_changed (new table)
        assert row[5] in (True, 1)  # success
        assert row[6] is None  # no error

    def test_sync_with_history_disabled(self, tmp_path: Path, db_url: str) -> None:
        """Test that sync does not record history when history is disabled."""
        csv_file = tmp_path / "data.csv"
        create_csv_file(csv_file, ["id", "name"], [{"id": "1", "name": "Alice"}])

        config_file = tmp_path / "config.yml"
        create_config_file(config_file, "test_job", "test_table", {"id": "id"})

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None

        # Sync with history disabled
        rows_synced = sync_file_to_db(csv_file, job, db_url, enable_history=False)
        assert rows_synced == 1

        # Verify history table doesn't exist
        with DatabaseConnection(db_url) as db:
            assert not db.table_exists("_crump_history")

    def test_sync_tracks_schema_changes(self, tmp_path: Path, db_url: str) -> None:
        """Test that history correctly tracks schema changes."""
        csv_file = tmp_path / "data.csv"
        create_csv_file(csv_file, ["id", "name"], [{"id": "1", "name": "Alice"}])

        config_file = tmp_path / "config.yml"
        create_config_file(config_file, "test_job", "test_table", {"id": "id"})

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None

        # First sync - creates table (schema change)
        sync_file_to_db(csv_file, job, db_url, enable_history=True)

        history_rows = execute_query(
            db_url,
            "SELECT schema_changed FROM _crump_history ORDER BY timestamp DESC LIMIT 1",
        )
        # SQLite stores booleans as 0/1, PostgreSQL stores as True/False
        assert history_rows[0][0] in (True, 1)  # First sync created table

        # Second sync - no schema changes
        create_csv_file(csv_file, ["id", "name"], [{"id": "2", "name": "Bob"}])
        sync_file_to_db(csv_file, job, db_url, enable_history=True)

        history_rows = execute_query(
            db_url,
            "SELECT schema_changed FROM _crump_history ORDER BY timestamp DESC LIMIT 1",
        )
        # SQLite stores booleans as 0/1, PostgreSQL stores as True/False
        assert history_rows[0][0] in (False, 0)  # Second sync had no schema changes

    def test_sync_tracks_deletions(self, tmp_path: Path, db_url: str) -> None:
        """Test that history tracks row deletions."""
        csv_file = tmp_path / "data_2024-01-01.csv"
        create_csv_file(
            csv_file, ["id", "name"], [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
        )

        # Create config with filename extraction for deletion tracking
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      id: id
    filename_to_column:
      template: "data_[date].csv"
      columns:
        date:
          db_column: sync_date
          type: date
          use_to_delete_old_rows: true
"""
        )

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None

        # First sync with date 2024-01-01 (2 rows)
        filename_values = {"date": "2024-01-01"}
        sync_file_to_db(csv_file, job, db_url, filename_values, enable_history=True)

        # Second sync with SAME date but only one row (should delete the other row for that date)
        csv_file2 = tmp_path / "data_2024-01-01_corrected.csv"
        create_csv_file(csv_file2, ["id", "name"], [{"id": "1", "name": "Alice Updated"}])
        filename_values2 = {"date": "2024-01-01"}
        sync_file_to_db(csv_file2, job, db_url, filename_values2, enable_history=True)

        # Check history for deletions - second sync should delete 1 row (Bob)
        history_rows = execute_query(
            db_url,
            "SELECT rows_upserted, rows_deleted FROM _crump_history ORDER BY timestamp DESC LIMIT 1",
        )
        assert history_rows[0][0] == 1  # upserted 1 row (Alice Updated)
        assert history_rows[0][1] == 1  # deleted 1 old row (Bob)

    def test_sync_records_hash(self, tmp_path: Path, db_url: str) -> None:
        """Test that history records file hash."""
        csv_file = tmp_path / "data.csv"
        create_csv_file(csv_file, ["id", "name"], [{"id": "1", "name": "Alice"}])

        config_file = tmp_path / "config.yml"
        create_config_file(config_file, "test_job", "test_table", {"id": "id"})

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None

        # Calculate expected hash
        expected_hash = _calculate_file_hash(csv_file)

        # Sync with history
        sync_file_to_db(csv_file, job, db_url, enable_history=True)

        # Verify hash in history
        history_rows = execute_query(
            db_url, "SELECT data_hash FROM _crump_history ORDER BY timestamp DESC LIMIT 1"
        )
        assert history_rows[0][0] == expected_hash

    def test_sync_records_duration(self, tmp_path: Path, db_url: str) -> None:
        """Test that history records sync duration."""
        csv_file = tmp_path / "data.csv"
        create_csv_file(csv_file, ["id", "name"], [{"id": "1", "name": "Alice"}])

        config_file = tmp_path / "config.yml"
        create_config_file(config_file, "test_job", "test_table", {"id": "id"})

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None

        # Sync with history
        sync_file_to_db(csv_file, job, db_url, enable_history=True)

        # Verify duration is recorded and reasonable
        history_rows = execute_query(
            db_url,
            "SELECT duration_seconds FROM _crump_history ORDER BY timestamp DESC LIMIT 1",
        )
        duration = history_rows[0][0]
        assert duration > 0
        assert duration < 60  # Should complete in less than 60 seconds

    def test_multiple_sync_history_entries(self, tmp_path: Path, db_url: str) -> None:
        """Test that multiple syncs create multiple history entries."""
        csv_file = tmp_path / "data.csv"
        config_file = tmp_path / "config.yml"
        create_config_file(config_file, "test_job", "test_table", {"id": "id"})

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None

        # Sync 3 times
        for i in range(3):
            create_csv_file(csv_file, ["id", "name"], [{"id": str(i), "name": f"User{i}"}])
            sync_file_to_db(csv_file, job, db_url, enable_history=True)

        # Verify 3 history entries
        rows = execute_query(db_url, "SELECT COUNT(*) FROM _crump_history")
        assert rows[0][0] == 3

    def test_sync_history_on_error(self, tmp_path: Path, db_url: str) -> None:
        """Test that history is recorded even when sync fails."""
        csv_file = tmp_path / "data.csv"
        # Create CSV with invalid data that will cause an error
        csv_file.write_text("id,name\n1,Alice\n")

        config_file = tmp_path / "config.yml"
        # Create config that references a column that doesn't exist
        config_file.write_text(
            """
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      missing_column: id
"""
        )

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None

        # Sync should fail
        with pytest.raises(ValueError):
            sync_file_to_db(csv_file, job, db_url, enable_history=True)

        # Verify history was still recorded
        rows = execute_query(db_url, "SELECT COUNT(*) FROM _crump_history")
        assert rows[0][0] == 1

        # Verify error details
        history_rows = execute_query(
            db_url,
            "SELECT success, error FROM _crump_history ORDER BY timestamp DESC LIMIT 1",
        )
        # SQLite stores booleans as 0/1, PostgreSQL stores as True/False
        assert history_rows[0][0] in (False, 0)  # success = False
        assert history_rows[0][1] is not None  # error message exists
        assert "missing_column" in history_rows[0][1]  # error mentions missing column
