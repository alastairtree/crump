# Welcome to Crump

Examines and syncs CSV, Parquet, and CDF files into PostgreSQL or SQLite databases in batched files using easy to edit configuration files.

[![CI](https://github.com/alastairtree/crump/workflows/CI/badge.svg)](https://github.com/alastairtree/crump/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## Overview

**crump** is a command-line tool and Python library for easy syncing CSV, Parquet, and CDF files to PostgreSQL or SQLite databases, and extracxting data from CDF files. It provides a declarative, configuration-based approach to data synchronization with automatic schema management..

## Key Features

### Data File Support
- **CSV Support**: Read and sync standard CSV files
- **Native CDF Processing**: Built-in support for Common Data Format (CDF) science files
- **Automatic Extraction**: Extracts CDF variables to CSV, Parquet, or directly to database
- **Array Variable Handling**: Automatically expands multi-dimensional array variables
- **Apache Parquet Support**: Built-in support for Apache Parquet files and sync Parquet files directly to database
- **Extract to Parquet**: Convert CDF files to Parquet format with `--parquet` flag

### Data Synchronization
- **Configuration-Based**: Examines your CSV files with the prepare command, and defines sync jobs in YAML with sensible column mappings
- **Column Mapping**: Sync all columns, rename them, or only sync a subset
- **Automatic Table Creation**: Creates target tables if they don't exist
- **Schema Evolution**: Automatically adds new columns as needed, never deletes existing columns. Optionally keeps a history of data changes in a history table.
- **Index Management**: Suggests and creates database indexes based on column types
- **Dual Interface**: Use as a CLI tool or import as a Python library
- **Filename-Based Extraction**: Extract values from filenames (dates, versions, etc.) and store in database columns
- **Automatic Cleanup**: Delete stale records based on extracted filename values
- **Compound Primary Keys**: Support for multi-column primary keys
- **Dry-Run Mode**: Preview all changes without modifying the database
- **Idempotent Operations**: Safe to run multiple times, uses upsert
- **Rich Output**: Beautiful terminal output with Rich library

## Quick Example

```bash
uv install crump # or pip install crump if you prefer

# Create a configuration file
crump prepare users.csv --config crump_config.yml --job users_sync

# Look at the mapping it generated for you in crump_config.yml and edit as needed. 
# Crump has mapped your columns and suggested keys and indexes

# get ready to sync - you db must be available
export DATABASE_URL="sqlite:///test.db"
# Or for Postgres
# export DATABASE_URL="postgresql://user:pass@localhost:5432/mydb"

# preview changes first (requires --db-url or DATABASE_URL)
crump sync users.csv --config crump_config.yml --job users_sync --dry-run

# Sync the file to database
crump sync users.csv --config crump_config.yml --job users_sync

# Later that day the v2 of the file arrives
# Sync the new file, old records from v1 are removed automatically, updates are applied to rows that match based on primary key
crump sync users_v2.csv --config crump_config.yml --job users_sync
```

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

📚 **[Read the full documentation](https://alastairtree.github.io/crump)**

- [Installation Guide](https://alastairtree.github.io/crump/installation/) - Install crump
- [Quick Start](https://alastairtree.github.io/crump/quick-start/) - Get started in 5 minutes
- [Configuration](https://alastairtree.github.io/crump/configuration/) - YAML configuration reference
- [CLI Reference](https://alastairtree.github.io/crump/cli-reference/) - Command-line documentation
- [Features](https://alastairtree.github.io/crump/features/) - Detailed feature documentation
- [API Reference](https://alastairtree.github.io/crump/api-reference/) - Python API documentation
- [Development](https://alastairtree.github.io/crump/development/) - Contributing guide


## Programmatic Usage

```python
from pathlib import Path
from crump import sync_csv_to_db, CrumpConfig

# Load configuration
config = CrumpConfig.from_yaml(Path("crump_config.yml"))
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
git clone https://github.com/alastairtree/crump.git
cd crump

# Install with development dependencies
uv sync --all-extras

# Run tests
uv run pytest -v

# Generate documentation locally
./generate-docs.sh
```

See the [Development Guide](https://alastairtree.github.io/crump/development/) for detailed instructions.

## Contributing

Contributions are welcome! Please see the [Contributing Guide](https://alastairtree.github.io/crump/contributing/) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 📖 [Documentation](https://alastairtree.github.io/crump)
- 🐛 [Issue Tracker](https://github.com/alastairtree/crump/issues)
- 💬 [Discussions](https://github.com/alastairtree/crump/discussions)

## Acknowledgments

Built with [Click](https://click.palletsprojects.com/), [Rich](https://rich.readthedocs.io/), [psycopg3](https://www.psycopg.org/psycopg3/), and [pytest](https://pytest.org/).
