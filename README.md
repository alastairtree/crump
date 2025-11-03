# CRUMP

Read and dump CSV, Parquet, and CDF science files into PostgreSQL or SQLite databases in batched files using easy to edit configuration files. Avoid writing code to examine and transform data files onto database tables, just tweak the automaticly generated crump-config.yaml file and sync all your data files into you database.

[![CI](https://github.com/alastairtree/clauddemo/workflows/CI/badge.svg)](https://github.com/alastairtree/clauddemo/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## Overview

**crump** is a command-line tool and Python library for easy syncing CSV, Parquet, and CDF (Common Data Format) files to a database (PostgreSQL or SQLite). It provides a declarative, configuration-based approach to data synchronization with some additional features that make it very fast to get up and running syncing big complex data files into a db quickly.

## Quick Start

### CSV Files

```bash
# Install
uv install crump

# or pip
pip install crump

# Create configuration by analyzing your CSV
crump prepare users.csv --config crump_config.yaml

# Preview changes (dry-run)
export DATABASE_URL="postgresql://localhost/mydb"
crump sync users.csv crump_config.yaml users_sync --dry-run

# Sync to database
crump sync users.csv crump_config.yaml users_sync
```

### Parquet Files

```bash
# Inspect Parquet file
crump inspect data.parquet --max-records 10

# Sync Parquet file to database
crump sync data.parquet crump_config.yaml --db-url postgresql://localhost/mydb

# Extract CDF to Parquet format
crump extract data.cdf --parquet --output-path ./output
```

### CDF (Science Data) Files

```bash
# Inspect CDF file contents
crump inspect data.cdf --max-records 10

# Extract CDF to CSV (optional, for preview)
crump extract data.cdf --output-path ./output --max-records 100

# Extract CDF to Parquet format
crump extract data.cdf --parquet --output-path ./output

# Create configuration from CDF file
crump prepare data.cdf --config crump_config.yaml

# Sync CDF directly to database (automatic extraction)
crump sync data.cdf crump_config.yaml vectors --db-url postgresql://localhost/mydb
```

## Key Features

- **CSV, Parquet & CDF Support**: Work with CSV files, Apache Parquet files, and NASA CDF (Common Data Format) science data files
- **Direct CDF Sync**: Sync CDF files directly to database without manual extraction
- **Parquet Format**: Extract CDF data to efficient columnar Parquet format with `--parquet` flag
- **Configuration-Based**: Define sync jobs in YAML
- **Column Mapping**: Rename columns between files and database
- **Filename Extraction**: Extract values from filenames (dates, versions, etc.)
- **Automatic Cleanup**: Delete stale records based on extracted values
- **Compound Primary Keys**: Support for multi-column primary keys
- **Dry-Run Mode**: Preview changes without modifying database
- **Record Limiting**: Limit extraction with `--max-records` for testing and quick syncs
- **Idempotent**: Safe to run multiple times
- **Type Hints**: Full type hints for IDE support
- **Well Tested**: Comprehensive test suite with real database tests

## Example Configuration

```yaml
jobs:
  daily_sales:
    target_table: sales
    id_mapping:
      sale_id: id
    filename_to_column:
      template: "sales_[date].csv"
      columns:
        date:
          db_column: sync_date
          type: date
          use_to_delete_old_rows: true
    columns:
      product_id: product_id
      amount: amount
```

This configuration:
- Syncs `sales_YYYY-MM-DD.csv` files to the `sales` table
- Extracts the date from filename and stores it in `sync_date` column
- Automatically deletes stale records for the same date after sync
- Maps CSV columns to database columns

## Documentation

📚 **[Read the full documentation](https://yourusername.github.io/crump)**

- [Installation Guide](https://yourusername.github.io/crump/installation/) - Install crump
- [Quick Start](https://yourusername.github.io/crump/quick-start/) - Get started in 5 minutes
- [Configuration](https://yourusername.github.io/crump/configuration/) - YAML configuration reference
- [CLI Reference](https://yourusername.github.io/crump/cli-reference/) - Command-line documentation
- [Features](https://yourusername.github.io/crump/features/) - Detailed feature documentation
- [API Reference](https://yourusername.github.io/crump/api-reference/) - Python API documentation
- [Development](https://yourusername.github.io/crump/development/) - Contributing guide

## Use Cases

- **Daily Data Updates**: Sync daily CSV exports with automatic date extraction and cleanup
- **Science Data Processing**: Process NASA CDF (Common Data Format) science files directly to database
- **Mission Data Pipelines**: Automated syncing of spacecraft telemetry and instrument data from CDF files
- **Data Warehousing**: Load CSV data into PostgreSQL with column transformations
- **Incremental Updates**: Replace partitioned data (by date, version, etc.) while preserving other partitions
- **Testing & Development**: Use `--max-records` to quickly test with subset of data

## Installation

```bash
# Using pip
pip install crump

# Using uv
uv pip install crump
```

Requires Python 3.11+ and PostgreSQL or SQLite.

## CLI Usage

```bash
# Analyze CSV and generate configuration
crump prepare data.csv crump_config.yaml my_job

# Sync with database
export DATABASE_URL="postgresql://user:pass@localhost/mydb"
crump sync data.csv crump_config.yaml my_job

# Preview changes without modifying database
crump sync data.csv crump_config.yaml my_job --dry-run
```

## Programmatic Usage

```python
from pathlib import Path
from crump import sync_csv_to_db, CrumpConfig

# Load configuration
config = CrumpConfig.from_yaml(Path("crump_config.yaml"))
job = config.get_job("my_job")

# Sync CSV to database (PostgreSQL or SQLite)
rows_synced = sync_csv_to_db(
    csv_path=Path("data.csv"),
    job=job,
    db_connection_string="postgresql://localhost/mydb"
)
print(f"Synced {rows_synced} rows")
```

## Development

```bash
# Clone repository
git clone https://github.com/yourusername/crump.git
cd crump

# Install with development dependencies
uv sync --all-extras

# Run tests
uv run pytest -v

# Generate documentation locally
./generate-docs.sh
```

See the [Development Guide](https://yourusername.github.io/crump/development/) for detailed instructions.

## Contributing

Contributions are welcome! Please see the [Contributing Guide](https://yourusername.github.io/crump/contributing/) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 📖 [Documentation](https://yourusername.github.io/crump)
- 🐛 [Issue Tracker](https://github.com/yourusername/crump/issues)
- 💬 [Discussions](https://github.com/yourusername/crump/discussions)

## Acknowledgments

Built with [Click](https://click.palletsprojects.com/), [Rich](https://rich.readthedocs.io/), [psycopg3](https://www.psycopg.org/psycopg3/), and [pytest](https://pytest.org/).
