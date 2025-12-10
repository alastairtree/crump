# CLI Reference

Complete reference for the `crump` command-line interface.

## Global Options

```bash
crump [OPTIONS] COMMAND [ARGS]...
```

### Options

| Option | Description |
|--------|-------------|
| `--version` | Show version number and exit |
| `--help` | Show help message and exit |

## Commands

### sync

Sync a CSV, Parquet, or CDF file to the database using a configuration.

```bash
crump sync FILE_PATH [OPTIONS]
```

#### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `FILE_PATH` | Path | Yes | Path to the CSV, Parquet, or CDF file to sync |

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config, -c` | Path | - | Path to the YAML configuration file (required) |
| `--job, -j` | String | Auto-detect | Name of the job to run from config (optional if config has only one job) |
| `--db-url TEXT` | String | `$DATABASE_URL` | PostgreSQL connection string |
| `--dry-run` | Flag | False | Simulate sync without making database changes |
| `--max-records INTEGER` | Integer | None (all) | Maximum number of records to extract per variable from CDF files |
| `--history/--no-history` | Flag | False | Record sync history in `_crump_history` table |

#### Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (alternative to `--db-url`) |

#### Examples

**Basic CSV sync:**

```bash
crump sync data.csv --config crump_config.yml --job my_job --db-url postgresql://localhost/mydb
```

**Sync Parquet file (using short option names):**

```bash
crump sync data.parquet -c crump_config.yml -j my_job --db-url postgresql://localhost/mydb
```

**Sync with auto-detected job (when config has only one job):**

```bash
crump sync data.csv --config crump_config.yml --db-url postgresql://localhost/mydb
```

**Sync CDF file (automatic extraction):**

```bash
crump sync science_data.cdf -c crump_config.yml -j vectors --db-url postgresql://localhost/mydb
```

**Sync CDF with limited records (for testing):**

```bash
crump sync science_data.cdf --config crump_config.yml --job vectors --db-url postgresql://localhost/mydb --max-records 200
```

**Using environment variable:**

```bash
export DATABASE_URL=postgresql://localhost/mydb
crump sync data.csv --config crump_config.yml --job my_job
```

**Dry-run mode:**

```bash
crump sync data.csv -c crump_config.yml -j my_job --dry-run
```

**Dry-run CDF with limited records:**

```bash
crump sync data.cdf --config crump_config.yml --job my_job --dry-run --max-records 100
```

**Enable history tracking:**

```bash
crump sync data.csv --config crump_config.yml --job my_job --history
```

#### Output

**Normal mode:**

```
Syncing data.csv using job 'my_job'...
  Extracted values: {'date': '2024-01-15'}
✓ Successfully synced 100 rows
  Table: my_table
  File: data.csv
  Extracted values: {'date': '2024-01-15'}
  History recorded in _crump_history table
```

**Note**: The history message only appears when `--history` flag is used.

**Dry-run mode:**

```
DRY RUN: Simulating sync of data.csv using job 'my_job'...

Dry-run Summary
────────────────────────────────────────────────────────────
  • Table 'my_table' would be CREATED

Data Changes:
  • 100 row(s) would be inserted/updated
  • No stale rows to delete

✓ Dry-run complete - no changes made to database
  File: data.csv
  Extracted values: {'date': '2024-01-15'}
```

#### Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | Error occurred |

---

### prepare

Analyze a CSV or CDF file and generate or update a configuration file.

```bash
crump prepare FILE_PATH... CONFIG [JOB] [OPTIONS]
```

#### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `FILE_PATH` | Path(s) | Yes | Path to the CSV or CDF file(s) to analyze |
| `CONFIG` | Path | Yes | Path to the YAML configuration file (created if doesn't exist) |
| `JOB` | String | No | Name for the job (auto-generated from filename if omitted) |

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--force` | Flag | False | Overwrite existing job if it exists |

#### Behavior

1. **Analyzes CSV file**:
   - Detects column types (integer, float, text, date, etc.)
   - Identifies nullable columns
   - Suggests an ID column

2. **Detects filename patterns**:
   - Looks for date patterns (YYYYMMDD, YYYY-MM-DD, YYYY_MM_DD)
   - Suggests `filename_to_column` configuration if found

3. **Suggests indexes**:
   - Date/datetime columns → descending indexes
   - Columns ending in `_id` or `_key` → ascending indexes

4. **Generates job name** (if not provided):
   - Removes file extension
   - Removes numbers
   - Collapses multiple underscores/hyphens
   - Strips trailing separators
   - Converts to lowercase
   - Example: `Sales_Data_2024.csv` → `sales_data`

#### Examples

**Auto-generate job name from CSV:**

```bash
crump prepare users.csv --config crump_config.yml
```

**Prepare CDF file:**

```bash
crump prepare science_data.cdf --config crump_config.yml
```

**Specify job name:**

```bash
crump prepare users.csv --config crump_config.yml --job my_custom_job
```

**Multiple files (auto-names each):**

```bash
crump prepare file1.csv file2.csv --config crump_config.yml
```

**Update existing job:**

```bash
crump prepare users.csv --config crump_config.yml --job users_sync --force
```

#### Output

```
Analyzing users_2024.csv...
  Found 5 columns
  Suggested ID column: user_id
  Detected date pattern in filename: users_[date].csv
  Suggested 2 index(es)

┌──────────────────────────────────────────────┐
│ Column Analysis                              │
├──────────────┬─────────────┬──────────────┤
│ Column       │ Type        │ Nullable     │
├──────────────┼─────────────┼──────────────┤
│ user_id      │ INTEGER     │ NOT NULL     │
│ name         │ TEXT        │ NOT NULL     │
│ email        │ TEXT        │ NOT NULL     │
│ created_at   │ DATE        │ NULL         │
│ status       │ TEXT        │ NULL         │
└──────────────┴─────────────┴──────────────┘

┌──────────────────────────────────────────────┐
│ Suggested Indexes                            │
├──────────────┬─────────────┬──────────────┤
│ Index Name   │ Column      │ Order        │
├──────────────┼─────────────┼──────────────┤
│ idx_created_at│ created_at │ DESC         │
└──────────────┴─────────────┴──────────────┘

✓ Created job 'users' in crump_config.yml
  Target table: users
  ID column: user_id → id
  Filename pattern detected: users_[date].csv
```

#### Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | Error occurred (e.g., job exists and --force not used) |

---

### inspect

Inspect CSV, Parquet, or CDF files and display summary information.

```bash
crump inspect FILES... [OPTIONS]
```

#### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `FILES` | Path(s) | Yes | One or more CSV, Parquet, or CDF file paths to inspect |

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--max-records`, `-n` | Integer | 10 | Number of sample records to display |

#### Examples

**Inspect a single CSV file:**

```bash
crump inspect users.csv
```

**Inspect a Parquet file:**

```bash
crump inspect users.parquet
```

**Inspect a CDF file:**

```bash
crump inspect science_data.cdf
```

**Inspect with custom record count:**

```bash
crump inspect data.csv --max-records 20
crump inspect data.cdf -n 5
```

**Inspect multiple files:**

```bash
crump inspect file1.csv file2.cdf file3.csv
```

#### Output

Displays:
- File format and size
- For CSV: column names, types, row count, sample data
- For CDF: variables, record counts, dimensions, attributes

---

### extract

Extract data from CDF files to CSV or Parquet format.

Supports two modes:
1. **Raw extraction** (default): Extracts all CDF variables with automatic column naming
2. **Config-based extraction**: Uses job configuration to select, rename, and transform columns (same as `sync` command but outputs to file)

Output format is determined by the filename extension (.csv for CSV, .parquet or .pq for Parquet) or by using the `--parquet` flag.

```bash
crump extract FILES... [OPTIONS]
```

#### Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `FILES` | Path(s) | Yes | One or more CDF files to extract |

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output-path`, `-o` | Path | Current directory | Output directory for files |
| `--filename` | String | `[SOURCE_FILE]-[VARIABLE_NAME].csv` | Template for output filenames (extension determines format) |
| `--parquet` | Flag | False | Output to Parquet format instead of CSV |
| `--automerge` | Flag | True | Merge variables with same record count (raw mode only) |
| `--no-automerge` | Flag | - | Create separate file for each variable (raw mode only) |
| `--append` | Flag | False | Append to existing files (raw mode only) |
| `--variables`, `-v` | String(s) | All | Specific variable names to extract (raw mode only) |
| `--max-records` | Integer | None (all) | Maximum number of records to extract per variable |
| `--config`, `-c` | Path | None | YAML configuration file (requires `--job`) |
| `--job`, `-j` | String | None | Job name from config (requires `--config`) |

#### Examples

**Raw Extraction Mode:**

**Extract all variables:**

```bash
crump extract science_data.cdf
```

**Extract to specific directory:**

```bash
crump extract data.cdf --output-path ./output
```

**Extract with limited records (for testing):**

```bash
crump extract data.cdf --max-records 100
```

**Extract specific variables:**

```bash
crump extract data.cdf --variables Epoch --variables B_field
```

**Extract without automerge:**

```bash
crump extract data.cdf --no-automerge
```

**Extract to Parquet format:**

```bash
crump extract data.cdf --parquet
```

**Extract to Parquet using filename extension:**

```bash
crump extract data.cdf --filename "[SOURCE_FILE]-[VARIABLE_NAME].parquet"
```

**Config-Based Extraction Mode:**

**Extract with column mapping (same transformations as sync):**

```bash
crump extract science_data.cdf --config crump_config.yml --job vectors_job
```

**Extract to specific directory with config:**

```bash
crump extract data.cdf -o output/ --config crump_config.yml --job my_job
```

**Config-based with limited records:**

```bash
crump extract data.cdf --config crump_config.yml --job my_job --max-records 100
```

**Multiple files with config:**

```bash
crump extract *.cdf --config crump_config.yml --job my_job -o output/
```

#### Output

**Raw mode** creates CSV files with:
- One CSV per group of variables (with automerge)
- Or one CSV per variable (without automerge)
- Column names derived from variable labels or names
- Array variables expanded into multiple columns

**Config mode** creates CSV files with:
- Columns selected and renamed according to job configuration
- Same transformations (lookup, expression, function) as `sync` command
- Metadata from filename extraction (if configured)
- One CSV file per CDF file (named after source file)

---

## Connection String Format

The `--db-url` option accepts standard PostgreSQL connection strings:

### Basic Format

```
postgresql://[user[:password]@][host][:port][/dbname]
```

### Examples

**Local database:**

```bash
postgresql://localhost/mydb
postgresql://localhost:5432/mydb
```

**With authentication:**

```bash
postgresql://user:password@localhost/mydb
postgresql://user:password@localhost:5432/mydb
```

**Cloud providers:**

```bash
# AWS RDS
postgresql://user:pass@mydb.abc123.us-east-1.rds.amazonaws.com:5432/mydb

# Google Cloud SQL
postgresql://user:pass@10.1.2.3:5432/mydb

# Supabase
postgresql://postgres:pass@db.abc123.supabase.co:5432/postgres
```

**SQLite (alternative):**

```bash
sqlite:///path/to/database.db
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Default database connection string | `postgresql://localhost/mydb` |

## Common Workflows

### Initial Setup

```bash
# 1. Analyze CSV and create config
crump prepare data.csv --config crump_config.yml --job my_job

# 2. Review generated crump_config.yml
cat crump_config.yml

# 3. Test with dry-run
crump sync data.csv --config crump_config.yml --job my_job --dry-run

# 4. Run actual sync
crump sync data.csv --config crump_config.yml --job my_job
```

### Daily Updates

```bash
# Setup (once)
export DATABASE_URL="postgresql://localhost/mydb"

# Daily sync (idempotent)
crump sync sales_$(date +%Y-%m-%d).csv --config crump_config.yml --job daily_sales
```

### Batch Processing

```bash
# Process multiple files
for file in data/*.csv; do
  crump sync "$file" --config crump_config.yml --job my_job
done
```

### Configuration Updates

```bash
# Update existing job with --force
crump prepare new_data.csv --config crump_config.yml --job my_job --force

# Review changes
git diff crump_config.yml

# Test new config
crump sync new_data.csv --config crump_config.yml --job my_job --dry-run
```

## Troubleshooting

### Job not found

```
Error: Job 'my_job' not found in config
Available jobs: users_sync, daily_sales
```

**Solution**: Check job name spelling or use `prepare` to create it.

### Filename pattern mismatch

```
Error: Could not extract values from filename 'data.csv'
  Pattern: sales_[date].csv
```

**Solution**: Rename file to match pattern or update `filename_to_column` configuration.

### Database connection failed

```
Error: could not connect to server
```

**Solution**: Verify `DATABASE_URL` is correct and database is running.

## Next Steps

- [Configuration Guide](configuration.md) - Learn about YAML configuration
- [Features](features.md) - Detailed feature documentation
- [API Reference](api-reference.md) - Use crump programmatically
