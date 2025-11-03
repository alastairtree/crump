# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Dependencies and Environment
```bash
# Install dependencies with development extras
uv sync --all-extras

# OR using pip (but do not use pip unless you have to - prefer uv for dependency management)
pip install -e ".[dev]"
```

### Testing

Always write unit tests for new features and bug fixes. Ensure all tests pass before committing code.
Also add integration tests that exercise crump at the cli level using cli_runner - see tests/test_cli.py for examples.
Tests should be passing before you commit code.

```bash

# Start with fast unit tests and sqlite only as these are fast to run (and no Docker required)
uv run pytest tests -k "not [postgres]" -v

# Then run the postgres tests (these are slower) - you should use the version of postgres that is already installed locally
pytest tests -k "[postgres]" -v

# Or run all tests
uv run pytest -v
```

Other useful testing commands:

```bash

# Run all tests with coverage
uv run pytest --cov=src --cov-report=term-missing

# database integration tests for sqlite only so VERY FAST (and no Docker required)
uv run pytest tests -k database -k "[sqlite]" -v

# Integration tests only (requires Docker)
uv run pytest tests/test_database_integration.py -v

# Run specific test
uv run pytest tests/test_config.py::TestCrumpConfig::test_load_from_yaml -v
```

### Code Quality - linting and Type Checking

Always check code quality before committing code. Use the commands below to format, lint, and type check your code.

```bash
# Format code
uv run ruff format .

# Check and fix linting
uv run ruff check --fix .

# Type checking
uv run mypy src
```

### Documentation

Documentation is in markdown files in docs/ folder. All new features should be documented. Documentation should include code and CLI examples. The code and cli examples will be tested in the test suite automatically to ensure they are valid.

```bash
# Generate and serve documentation locally
./generate-docs.sh build

# OR manually
uv run mkdocs serve
```

## Project Architecture

### Core Components

**CLI Interface** (`cli.py`, `cli_*.py`):
- Main entry point with Click-based commands
- Commands: `sync`, `prepare`, `inspect`, `extract`
- Each command has dedicated module (e.g., `cli_sync.py`)
- `extract` command supports both raw CDF dump and config-based extraction with column mapping

**Configuration System** (`config.py`):
- YAML-based job configuration with `CrumpConfig` and `CrumpJob` classes
- Column mappings between CSV and database
- Filename extraction patterns for metadata (dates, versions, etc.)
- Compound primary key support via `id_mapping`

**Database Operations** (`database.py`):
- PostgreSQL sync with `sync_csv_to_postgres()`
- Dry-run mode for previewing changes
- Automatic table creation and schema updates
- Stale record cleanup based on filename-extracted values

**Type Detection** (`type_detection.py`):
- Automatic CSV analysis for data types and nullable columns
- Primary key suggestion based on column characteristics

**CDF Support** (`cdf_*.py`):
- Reading and extracting CDF (Common Data Format) science files
- Conversion to CSV for database sync
- Config-based extraction with column mapping and transformations
- Two extraction modes: raw dump or config-based with same transformations as sync

### Key Features

See README.md and docs/index.md for detailed feature list.

### Configuration Structure

```yaml
jobs:
  job_name:
    target_table: "table_name"
    id_mapping:                    # Compound primary key
      csv_col1: db_col1
      csv_col2: db_col2
    filename_to_column:            # Extract from filename
      template: "data_[date]_[version].csv"
      columns:
        date:
          db_column: sync_date
          type: date
          use_to_delete_old_rows: true
    columns:                       # Column mappings
      csv_col: db_col
```

### Dependencies

- **Click**: CLI framework
- **Rich**: Terminal output formatting
- **PyYAML**: Configuration parsing
- **psycopg**: PostgreSQL adapter
- **cdflib**: CDF file reading
- **testcontainers**: Integration testing with real databases
- **pyarrow**: Parquet file support