"""Sync CSV, Parquet, and CDF science files into database.

This package provides both a CLI tool and programmatic API for syncing
CSV, Parquet, and CDF files into a database (PostgreSQL or SQLite).

CLI Usage:
    crump sync <file> <config> <job> --db-url <url>
    crump prepare <file> <config> <job>
    crump inspect <file>
    crump extract <file> --output-dir <dir>

Programmatic Usage:
    from crump import sync_file_to_db, analyze_tabular_file_types_and_nullable
    from pathlib import Path

    # Sync a tabular file (CSV or Parquet)
    sync_file_to_db(
        file_path=Path("data.parquet"),
        job=job_config,
        db_connection_string="postgresql://localhost/mydb"
    )
"""

__version__ = "0.1.0"

# Export main API functions
from crump.config import (
    ColumnMapping,
    CrumpConfig,
    CrumpJob,
    Index,
    IndexColumn,
)
from crump.database import (
    DryRunSummary,
    sync_file_to_db,
    sync_file_to_db_dry_run,
)
from crump.type_detection import (
    analyze_tabular_file_types_and_nullable,
    suggest_id_column,
)

__all__ = [
    "__version__",
    # Configuration
    "CrumpConfig",
    "CrumpJob",
    "ColumnMapping",
    "Index",
    "IndexColumn",
    # Database operations
    "sync_file_to_db",
    "sync_file_to_db_dry_run",
    "DryRunSummary",
    # Type detection
    "analyze_tabular_file_types_and_nullable",
    "suggest_id_column",
]
