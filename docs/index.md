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

## Use Cases

- **Rapid data ingestion**: Quickly get lots of data files dumpoed into a database with minimal setup and no code.
- **Daily Data Updates**: Sync daily CSV exports with automatic date extraction and cleanup
- **Science Data Processing**: Process CDF science files with metadata extraction
- **Data Warehousing**: Load CSV data into PostgreSQL with column transformations
- **Incremental Updates**: Replace partitioned data (by date, version, etc.) while preserving other partitions
- **Configuration-Driven ETL**: Define data pipelines in YAML without writing code

## Next Steps

- [Installation Guide](installation.md) - Install crump
- [Quick Start](quick-start.md) - Get started in 5 minutes
- [Configuration](configuration.md) - Learn about YAML configuration
- [CLI Reference](cli-reference.md) - Command-line interface documentation
- [Features](features.md) - Detailed feature documentation
- [API Reference](api-reference.md) - Use crump as a Python library

## Support

If you have any questions or run into issues, please [open an issue](https://github.com/alastairtree/crump/issues) on GitHub.

