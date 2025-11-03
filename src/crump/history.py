"""History tracking for crump sync operations."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crump.database import DatabaseBackend


class SyncHistoryEntry:
    """Represents a single sync history entry."""

    def __init__(
        self,
        timestamp: datetime,
        filename: str,
        table_name: str,
        rows_upserted: int,
        rows_deleted: int,
        data_hash: str,
        schema_changed: bool,
        duration_seconds: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Initialize a sync history entry.

        Args:
            timestamp: UTC timestamp when sync started for this file
            filename: Name of the file being synced
            table_name: Target table name for the sync
            rows_upserted: Number of rows inserted or updated
            rows_deleted: Number of rows deleted
            data_hash: Hash of the data file
            schema_changed: Whether schema changes were made
            duration_seconds: Duration of the sync in seconds
            success: Whether the sync succeeded
            error: Error message if sync failed, None otherwise
        """
        self.timestamp = timestamp
        self.filename = filename
        self.table_name = table_name
        self.rows_upserted = rows_upserted
        self.rows_deleted = rows_deleted
        self.data_hash = data_hash
        self.schema_changed = schema_changed
        self.duration_seconds = duration_seconds
        self.success = success
        self.error = error


def _calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file.

    Args:
        file_path: Path to the file to hash

    Returns:
        Hexadecimal string representation of the SHA256 hash
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in 64kb chunks to handle large files
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _ensure_history_table_exists(backend: DatabaseBackend) -> None:
    """Create the _crump_history table if it doesn't exist.

    Args:
        backend: Database backend to use
    """
    columns = {
        "timestamp": backend.map_data_type("timestamp") + " NOT NULL",
        "filename": backend.map_data_type("text") + " NOT NULL",
        "table_name": backend.map_data_type("text") + " NOT NULL",
        "rows_upserted": backend.map_data_type("integer") + " NOT NULL",
        "rows_deleted": backend.map_data_type("integer") + " NOT NULL",
        "data_hash": backend.map_data_type("text") + " NOT NULL",
        "schema_changed": "BOOLEAN NOT NULL",
        "duration_seconds": backend.map_data_type("float") + " NOT NULL",
        "success": "BOOLEAN NOT NULL",
        "error": backend.map_data_type("text"),
    }

    backend.create_table_if_not_exists("_crump_history", columns, primary_keys=["timestamp"])
    backend.commit()


def record_sync_history(
    backend: DatabaseBackend,
    file_path: Path,
    table_name: str,
    rows_upserted: int,
    rows_deleted: int,
    schema_changed: bool,
    start_time: datetime,
    end_time: datetime,
    success: bool,
    error: str | None = None,
) -> None:
    """Record a sync operation to the history table.

    Args:
        backend: Database backend to use
        file_path: Path to the file that was synced
        table_name: Target table name for the sync
        rows_upserted: Number of rows inserted or updated
        rows_deleted: Number of rows deleted
        schema_changed: Whether schema changes were made
        start_time: When the sync started (UTC)
        end_time: When the sync ended (UTC)
        success: Whether the sync succeeded
        error: Error message if sync failed, None otherwise
    """
    # Ensure history table exists
    _ensure_history_table_exists(backend)

    # Calculate file hash
    data_hash = _calculate_file_hash(file_path)

    # Calculate duration
    duration_seconds = (end_time - start_time).total_seconds()

    # Create history entry
    entry = SyncHistoryEntry(
        timestamp=start_time,
        filename=file_path.name,
        table_name=table_name,
        rows_upserted=rows_upserted,
        rows_deleted=rows_deleted,
        data_hash=data_hash,
        schema_changed=schema_changed,
        duration_seconds=duration_seconds,
        success=success,
        error=error,
    )

    # Insert into database
    row_data = {
        "timestamp": entry.timestamp,
        "filename": entry.filename,
        "table_name": entry.table_name,
        "rows_upserted": entry.rows_upserted,
        "rows_deleted": entry.rows_deleted,
        "data_hash": entry.data_hash,
        "schema_changed": entry.schema_changed,
        "duration_seconds": entry.duration_seconds,
        "success": entry.success,
        "error": entry.error,
    }

    # Use upsert to handle potential timestamp conflicts (though unlikely)
    backend.upsert_row("_crump_history", ["timestamp"], row_data)
    backend.commit()


def get_utc_now() -> datetime:
    """Get current UTC datetime.

    Returns:
        Current UTC datetime with timezone info
    """
    return datetime.now(UTC)
