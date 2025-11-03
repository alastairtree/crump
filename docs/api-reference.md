# API Reference

Use crump programmatically as a Python library.

## Overview

The `crump` package can be imported and used in your Python applications. This is useful for:

- Building custom ETL pipelines
- Integrating with existing applications
- Automating data synchronization workflows
- Creating custom tools on top of crump

## Installation

```bash
pip install crump
```

## Quick Example

```python
from pathlib import Path
from crump import sync_file_to_db, CrumpConfig

# Load configuration
config = CrumpConfig.from_yaml(Path("crump_config.yml"))
job = config.get_job("my_job")

# Sync a tabular file (CSV or Parquet)
rows_synced = sync_file_to_db(
    file_path=Path("users.parquet"),
    job=job,
    db_connection_string="sqlite:///test.db"
)
print(f"Synced {rows_synced} rows")
```

## Core Functions

### sync_file_to_db

Sync a tabular file (CSV or Parquet) to a database (PostgreSQL or SQLite).

File format is automatically detected from the file extension.

```python
def sync_file_to_db(
    file_path: Path,
    job: CrumpJob,
    db_connection_string: str,
    filename_values: dict[str, str] | None = None,
    enable_history: bool = False
) -> int
```

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_path` | `Path` | Path to the tabular file (CSV or Parquet) to sync |
| `job` | `CrumpJob` | Configuration for the sync job |
| `db_connection_string` | `str` | Database connection string (PostgreSQL or SQLite) |
| `filename_values` | `dict[str, str] \| None` | Extracted values from filename (optional) |
| `enable_history` | `bool` | Whether to record sync history (default: False) |

**Returns**: Number of rows synced (int)

**Raises**:
- `FileNotFoundError`: File doesn't exist
- `ValueError`: Invalid configuration or data
- `DatabaseError`: Database connection or query errors

**Example**:

```python
from pathlib import Path
from crump import sync_file_to_db, CrumpConfig

config = CrumpConfig.from_yaml(Path("crump_config.yml"))
job = config.get_job("users_sync")

# Sync CSV file
rows = sync_file_to_db(
    file_path=Path("users.csv"),
    job=job,
    db_connection_string="sqlite:///test.db"
    # OR db_connection_string="postgresql://localhost:5432/mydb"
)

# Sync Parquet file (format auto-detected from extension)
rows = sync_file_to_db(
    file_path=Path("users.csv"),
    crump_job=job,
    db_connection_string="sqlite:///test.db"
)

# With filename extraction
filename_values = {"date": "2024-01-15"}
rows = sync_csv_to_db(
    file_path=Path("users.csv"),
    crump_job=job,
    db_connection_string="sqlite:///test.db",
    filename_values=filename_values
)
```

### sync_csv_to_db_dry_run

Preview sync without making database changes.

```python
def sync_csv_to_db_dry_run(
    file_path: Path,
    crump_job: CrumpJob,
    db_connection_string: str,
    filename_values: dict[str, str] | None = None
) -> DryRunSummary
```

**Parameters**: Same as `sync_csv_to_db`

**Returns**: `DryRunSummary` object with:

| Attribute | Type | Description |
|-----------|------|-------------|
| `table_name` | `str` | Name of the target table |
| `table_exists` | `bool` | Whether table already exists |
| `new_columns` | `list[tuple[str, str]]` | Columns to be added (name, type) |
| `new_indexes` | `list[str]` | Indexes to be created |
| `rows_to_sync` | `int` | Number of rows to insert/update |
| `rows_to_delete` | `int` | Number of stale rows to delete |

**Example**:

```python
from pathlib import Path
from crump import sync_csv_to_db_dry_run, CrumpConfig

config = CrumpConfig.from_yaml(Path("crump_config.yml"))
job = config.get_job("my_job")

summary = sync_csv_to_db_dry_run(
    file_path=Path("users.csv"),
    crump_job=job,
    db_connection_string="sqlite:///test.db"
)

print(f"Table exists: {summary.table_exists}")
print(f"New columns: {summary.new_columns}")
print(f"Rows to sync: {summary.rows_to_sync}")
print(f"Rows to delete: {summary.rows_to_delete}")

# Check before proceeding
if summary.new_columns:
    print("Warning: New columns will be added!")
    for col_name, col_type in summary.new_columns:
        print(f"  - {col_name}: {col_type}")
```

### analyze_csv_types_and_nullable

Analyze CSV file to detect column types.

```python
def analyze_csv_types_and_nullable(
    file_path: Path
) -> dict[str, tuple[str, bool]]
```

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_path` | `Path` | Path to the CSV file |

**Returns**: Dictionary mapping column names to (type, nullable) tuples

**Example**:

```python
from pathlib import Path
from crump import analyze_csv_types_and_nullable

column_info = analyze_csv_types_and_nullable(Path("users.csv"))

for col_name, (data_type, nullable) in column_info.items():
    null_str = "NULL" if nullable else "NOT NULL"
    print(f"{col_name}: {data_type} {null_str}")
```

Output:
```
user_id: INTEGER NOT NULL
name: TEXT NOT NULL
email: TEXT NOT NULL
age: INTEGER NULL
created_at: DATE NULL
```

### suggest_id_column

Suggest an ID column from a list of columns.

```python
def suggest_id_column(columns: list[str]) -> str
```

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `columns` | `list[str]` | List of column names |

**Returns**: Suggested ID column name (str)

**Logic**:
1. Looks for columns ending with `_id` or `_key`
2. Prefers shorter names
3. Falls back to first column if none found

**Example**:

```python
from crump import suggest_id_column

columns = ["user_id", "name", "email", "created_at"]
id_col = suggest_id_column(columns)
print(f"Suggested ID: {id_col}")  # Output: user_id

columns = ["name", "email"]
id_col = suggest_id_column(columns)
print(f"Suggested ID: {id_col}")  # Output: name (first column)
```

## Configuration Classes

### CrumpConfig

Main configuration container.

```python
class CrumpConfig:
    def __init__(self, jobs: dict[str, CrumpJob]) -> None

    @classmethod
    def from_yaml(cls, config_path: Path) -> CrumpConfig

    def save_to_yaml(self, config_path: Path) -> None

    def get_job(self, job_name: str) -> CrumpJob | None

    def add_or_update_job(self, job: CrumpJob, force: bool = False) -> None
```

**Example**:

```python
from pathlib import Path
from crump import CrumpConfig

# Load from file
config = CrumpConfig.from_yaml(Path("crump_config.yml"))

# Get a job
job = config.get_job("my_job")
if job:
    print(f"Target table: {job.target_table}")

# Create new config
from crump import CrumpJob, ColumnMapping

new_config = CrumpConfig(jobs={})
job = CrumpJob(
    name="users",
    target_table="users",
    id_mapping=[ColumnMapping("user_id", "id", "integer")]
)
new_config.add_or_update_job(job)
new_config.save_to_yaml(Path("new_crump_config.yml"))
```

### CrumpJob

Configuration for a single sync job.

```python
class CrumpJob:
    def __init__(
        self,
        name: str,
        target_table: str,
        id_mapping: list[ColumnMapping],
        columns: list[ColumnMapping] | None = None,
        filename_to_column: FilenameToColumn | None = None,
        indexes: list[Index] | None = None,
    ) -> None
```

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Job name |
| `target_table` | `str` | Target database table |
| `id_mapping` | `list[ColumnMapping]` | Primary key mapping |
| `columns` | `list[ColumnMapping]` | Column mappings (None = sync all) |
| `filename_to_column` | `FilenameToColumn \| None` | Filename extraction config |
| `indexes` | `list[Index]` | Database indexes to create |

**Example**:

```python
from crump import CrumpJob, ColumnMapping, Index, IndexColumn

job = CrumpJob(
    name="users_sync",
    target_table="users",
    id_mapping=[
        ColumnMapping("user_id", "id", "integer")
    ],
    columns=[
        ColumnMapping("name", "full_name", "text"),
        ColumnMapping("email", "email", "text"),
    ],
    indexes=[
        Index(
            name="idx_email",
            columns=[IndexColumn("email", "ASC")]
        )
    ]
)
```

### ColumnMapping

Mapping for a single column.

```python
class ColumnMapping:
    def __init__(
        self,
        csv_column: str,
        db_column: str,
        data_type: str | None = None
    ) -> None
```

**Example**:

```python
from crump import ColumnMapping

mapping = ColumnMapping(
    csv_column="user_id",
    db_column="id",
    data_type="integer"
)
```

### FilenameToColumn

Configuration for extracting values from filenames.

```python
class FilenameToColumn:
    def __init__(
        self,
        columns: dict[str, FilenameColumnMapping],
        template: str | None = None,
        regex: str | None = None,
    ) -> None

    def extract_values_from_filename(
        self,
        filename: str | Path
    ) -> dict[str, str] | None

    def get_delete_key_columns(self) -> list[str]
```

**Example**:

```python
from crump import FilenameToColumn, FilenameColumnMapping

ftc = FilenameToColumn(
    template="sales_[date].csv",
    columns={
        "date": FilenameColumnMapping(
            name="date",
            db_column="sync_date",
            data_type="date",
            use_to_delete_old_rows=True
        )
    }
)

# Extract values
values = ftc.extract_values_from_filename("sales_2024-01-15.csv")
print(values)  # {'date': '2024-01-15'}

# Get delete key columns
delete_cols = ftc.get_delete_key_columns()
print(delete_cols)  # ['sync_date']
```

### Index

Database index configuration.

```python
class Index:
    def __init__(
        self,
        name: str,
        columns: list[IndexColumn]
    ) -> None
```

**Example**:

```python
from crump import Index, IndexColumn

# Single column index
idx1 = Index(
    name="idx_created_at",
    columns=[IndexColumn("created_at", "DESC")]
)

# Multi-column index
idx2 = Index(
    name="idx_user_date",
    columns=[
        IndexColumn("user_id", "ASC"),
        IndexColumn("created_at", "DESC")
    ]
)
```

## Complete Example

Here's a complete example demonstrating various API features:

```python
from pathlib import Path
from crump import (
    CrumpConfig,
    CrumpJob,
    ColumnMapping,
    FilenameToColumn,
    FilenameColumnMapping,
    Index,
    IndexColumn,
    sync_csv_to_db,
    sync_csv_to_db_dry_run,
    analyze_csv_types_and_nullable,
    suggest_id_column,
)

# Analyze a CSV file
csv_path = Path("users.csv")
column_info = analyze_csv_types_and_nullable(csv_path)
columns = list(column_info.keys())
id_column = suggest_id_column(columns)

print(f"Detected columns: {columns}")
print(f"Suggested ID: {id_column}")

# Create a job programmatically
job = CrumpJob(
    name="daily_sales",
    target_table="sales",
    id_mapping=[
        ColumnMapping(id_column, "id", "integer")
    ],
    columns=[
        ColumnMapping("product_id", "product_id", "integer"),
        ColumnMapping("amount", "amount", "float"),
    ],
    filename_to_column=FilenameToColumn(
        template="sales_[date].csv",
        columns={
            "date": FilenameColumnMapping(
                name="date",
                db_column="sync_date",
                data_type="date",
                use_to_delete_old_rows=True
            )
        }
    ),
    indexes=[
        Index(
            name="idx_sync_date",
            columns=[IndexColumn("sync_date", "DESC")]
        )
    ]
)

# Create config and save
config = CrumpConfig(jobs={})
config.add_or_update_job(job)
config.save_to_yaml(Path("crump_config.yml"))

# Extract filename values
filename_values = job.filename_to_column.extract_values_from_filename(csv_path)

# Dry-run first
summary = sync_csv_to_db_dry_run(
    file_path=csv_path,
    crump_job=job,
    db_connection_string="sqlite:///test.db",
    filename_values=filename_values
)

print(f"\nDry-run results:")
print(f"  Table exists: {summary.table_exists}")
print(f"  Rows to sync: {summary.rows_to_sync}")
print(f"  Rows to delete: {summary.rows_to_delete}")

# Confirm and sync
if input("Proceed with sync? (y/n): ").lower() == "y":
    rows = sync_csv_to_db(
        file_path=csv_path,
        crump_job=job,
        db_connection_string="sqlite:///test.db",
        filename_values=filename_values
    )
    print(f"\nSynced {rows} rows successfully!")
```

## Error Handling

```python
from pathlib import Path
from crump import sync_csv_to_db, CrumpConfig

try:
    config = CrumpConfig.from_yaml(Path("crump_config.yml"))
    job = config.get_job("my_job")

    if not job:
        print("Job not found in configuration")
        exit(1)

    rows = sync_csv_to_db(
        file_path=Path("users.csv"),
        crump_job=job,
        db_connection_string="sqlite:///test.db"
    )
    print(f"Success: {rows} rows synced")

except FileNotFoundError as e:
    print(f"File not found: {e}")
except ValueError as e:
    print(f"Configuration error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Type Hints

All functions include full type hints for IDE autocomplete and type checking:

```python
from pathlib import Path
from crump import sync_csv_to_db, CrumpJob

# Type checker knows the types
def sync_data(csv_file: Path, job: CrumpJob) -> None:
    rows: int = sync_csv_to_db(
        file_path=csv_file,
        crump_job=job,
        db_connection_string="sqlite:///test.db"
    )
    # rows is guaranteed to be int
    print(f"Synced {rows} rows")
```

## Next Steps

- [Configuration Guide](configuration.md) - Learn about YAML configuration
- [Features](features.md) - Detailed feature documentation
- [Development](development.md) - Contributing to crump
