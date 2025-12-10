# Features

Detailed documentation of all crump features.

## Idempotent Operations

Running sync multiple times is safe - it uses PostgreSQL's `INSERT ... ON CONFLICT DO UPDATE` (upsert).

### How it Works

```bash
# First run: inserts 3 rows
crump sync users.csv --config crump_config.yml --job sync_users

# Second run: updates existing rows, no duplicates
crump sync users.csv --config crump_config.yml --job sync_users
```

The same rows are updated, not duplicated. This makes crump safe for:

- Automated scripts
- Cron jobs
- CI/CD pipelines
- Re-running after failures

### Benefits

- **No duplicate data**: Primary key conflicts are handled automatically
- **Safe retries**: Failures can be retried without cleanup
- **Incremental updates**: Update only changed rows
- **Atomic operations**: Each sync is a single transaction

## Column Mapping

Map CSV columns to different database column names.

### Basic Mapping

```yaml
columns:
  name: full_name      # CSV: name → DB: full_name
  email: email_address # CSV: email → DB: email_address
```

### Use Cases

- **Database conventions**: Map to snake_case or camelCase
- **Legacy schemas**: Adapt to existing table structures
- **Conflict resolution**: Rename columns that conflict with SQL keywords
- **Data normalization**: Standardize column names across sources

### Example

**CSV file** (`users.csv`):
```csv
user_id,name,email
1,Alice,alice@example.com
```

**Configuration**:
```yaml
id_mapping:
  user_id: id
columns:
  name: full_name
  email: email_address
```

**Database table**:
```sql
SELECT id, full_name, email_address FROM users;
```

## Selective Syncing

Choose which columns to sync, ignoring others in the CSV.

### Configuration

```yaml
columns:
  name: full_name
  email: email
  # internal_notes column is NOT synced
```

### Use Cases

- **Privacy**: Exclude sensitive columns
- **Optimization**: Reduce data size by excluding unused columns
- **Partial updates**: Update only specific fields
- **Data filtering**: Skip temporary or internal columns

### Sync All Columns

To sync all columns with their original names, omit the `columns` field:

```yaml
jobs:
  my_job:
    target_table: users
    id_mapping:
      user_id: id
    # No columns field = sync all columns
```

## Filename-Based Value Extraction

Extract values from filenames (dates, versions, mission names, etc.) and store them in database columns.

### Template Syntax

Use `[column_name]` placeholders:

```yaml
filename_to_column:
  template: "sales_[date].csv"
  columns:
    date:
      db_column: sync_date
      type: date
      use_to_delete_old_rows: true
```

**Matches**: `sales_2024-01-15.csv`
**Extracts**: `date = '2024-01-15'`

### Regex Syntax

For complex patterns, use regex with named groups:

```yaml
filename_to_column:
  regex: '(?P<mission>[a-z]+)_level2_(?P<sensor>[a-z]+)_(?P<date>\d{8})_v(?P<version>\d+)\.cdf'
  columns:
    mission:
      db_column: mission_name
      type: varchar(10)
    sensor:
      db_column: sensor_type
      type: varchar(20)
    date:
      db_column: observation_date
      type: date
      use_to_delete_old_rows: true
    version:
      db_column: file_version
      type: varchar(10)
```

**Matches**: `imap_level2_primary_20240115_v002.cdf`
**Extracts**:
- `mission = 'imap'`
- `sensor = 'primary'`
- `date = '20240115'`
- `version = '002'`

### Use Cases

- **Time-series data**: Extract dates from daily/weekly/monthly files
- **Versioned data**: Track file versions in the database
- **Multi-tenant**: Extract customer/tenant IDs from filenames
- **Data provenance**: Record source information
- **Partitioned data**: Extract partition keys

## Automatic Stale Record Cleanup

Automatically delete records that are no longer in the current CSV.

### How it Works

1. **Extract value** from filename (e.g., date)
2. **Add to all rows** being synced
3. **After sync**, delete rows where:
   - The extracted value(s) match
   - But the ID is not in the current CSV

### Configuration

Mark columns with `use_to_delete_old_rows: true`:

```yaml
filename_to_column:
  template: "sales_[date].csv"
  columns:
    date:
      db_column: sync_date
      type: date
      use_to_delete_old_rows: true
```

### Example Workflow

**Day 1**: Sync sales for 2024-01-15

```bash
crump sync sales_2024-01-15.csv --config crump_config.yml --job daily_sales
```

**Database**:
```sql
SELECT * FROM sales WHERE sync_date = '2024-01-15';
-- 100 rows
```

**Day 2**: Re-sync with corrections (only 95 rows now)

```bash
crump sync sales_2024-01-15-corrected.csv --config crump_config.yml --job daily_sales
```

**Result**:
- Updates 95 existing rows
- Deletes 5 stale rows (no longer in CSV)
- Preserves rows for other dates

### Compound Delete Keys

Use multiple columns to identify stale records:

```yaml
filename_to_column:
  template: "[mission]_[sensor]_[date].cdf"
  columns:
    mission:
      db_column: mission_name
      type: varchar(10)
      use_to_delete_old_rows: true
    sensor:
      db_column: sensor_type
      type: varchar(20)
      use_to_delete_old_rows: true
    date:
      db_column: observation_date
      type: date
      use_to_delete_old_rows: true
```

Deletes stale rows only when **all three values** match.

### Benefits

- **Safe incremental syncs**: Replace partitioned data without affecting others
- **Automatic cleanup**: No manual deletion needed
- **Data integrity**: Ensures database matches current source
- **Versioning support**: Update specific partitions while preserving history

## Compound Primary Keys

Support for multi-column primary keys when a single column isn't unique.

### Configuration

```yaml
id_mapping:
  store_id: store_id
  product_id: product_id
```

This creates a compound primary key on `(store_id, product_id)`.

### Use Cases

- **Many-to-many relationships**: Store-product, user-role mappings
- **Time-series with dimensions**: Metric-timestamp-host
- **Multi-tenant data**: Tenant-record combinations
- **Hierarchical data**: Parent-child relationships

### Example

**CSV file**:
```csv
store_id,product_id,quantity,price
1,100,50,9.99
1,101,30,14.99
2,100,25,9.99
```

**Configuration**:
```yaml
id_mapping:
  store_id: store_id
  product_id: product_id
columns:
  quantity: qty
  price: price
```

**Database**:
```sql
-- Compound primary key on (store_id, product_id)
SELECT * FROM store_sales;
```

## Database Indexes

Define indexes to improve query performance.

### Single Column Index

```yaml
indexes:
  - name: idx_created_at
    columns:
      - column: created_at
        order: DESC
```

### Multi-Column Index

```yaml
indexes:
  - name: idx_user_date
    columns:
      - column: user_id
        order: ASC
      - column: created_at
        order: DESC
```

### Index Features

- **Single or multi-column**: Support for composite indexes
- **Sort order**: Ascending (ASC) or descending (DESC)
- **Automatic creation**: Created if they don't exist
- **Idempotent**: Safe to run multiple times
- **Cross-database**: Works with PostgreSQL and SQLite

### Automatic Index Suggestions

The `prepare` command suggests indexes automatically:

```bash
crump prepare activity_log.csv --config crump_config.yml --job user_activity
```

**Rules**:

| Column Type | Index Type | Reason |
|-------------|------------|--------|
| Date/datetime columns | DESC | Recent-first queries |
| Columns ending in `_id` or `_key` | ASC | Foreign key lookups |
| ID column | Skipped | Already a primary key |

### Performance Impact

**Without index**:
```sql
-- Seq Scan on sales (cost=0.00..1234.56 rows=100)
SELECT * FROM sales WHERE created_at > '2024-01-01';
```

**With index**:
```sql
-- Index Scan using idx_created_at on sales (cost=0.42..8.44 rows=100)
SELECT * FROM sales WHERE created_at > '2024-01-01';
```

## Dry-Run Mode

Preview all changes without modifying the database.

### Usage

```bash
export DATABASE_URL="sqlite:///test.db"
crump sync data.csv --config crump_config.yml --job my_job --dry-run
```

### What it Shows

**Schema Changes**:
- Tables to be created
- Columns to be added
- Indexes to be created

**Data Changes**:
- Number of rows to insert/update
- Number of stale rows to delete

**Example Output**:

```
DRY RUN: Simulating sync of sales_2024-01-15.csv using job 'daily_sales'...

Dry-run Summary
────────────────────────────────────────────────────────────
  • Table 'sales' exists
  • 2 column(s) would be ADDED:
      - product_name (TEXT)
      - category (TEXT)
  • 1 index(es) would be CREATED:
      - idx_sync_date

Data Changes:
  • 150 row(s) would be inserted/updated
  • 10 stale row(s) would be deleted

✓ Dry-run complete - no changes made to database
  File: sales_2024-01-15.csv
  Extracted values: {'date': '2024-01-15'}
```

### Use Cases

- **Test configurations**: Verify config before running
- **Preview schema changes**: See what columns/indexes will be added
- **Estimate impact**: Check how many rows will be affected
- **Debug issues**: Identify problems without side effects
- **Documentation**: Show expected behavior

## Multi-Database Support

Works with PostgreSQL and SQLite.

### PostgreSQL

Primary target with full feature support:

```bash
export DATABASE_URL="postgresql://localhost/mydb"
crump sync data.csv --config crump_config.yml --job my_job
```

**Features**:
- Full upsert support
- Compound primary keys
- Advanced indexing
- Row value constructors for compound keys
- Transaction isolation

### SQLite

Alternative for testing and lightweight use:

```bash
export DATABASE_URL="sqlite:///mydb.db"
crump sync data.csv --config crump_config.yml --job my_job
```

**Limitations**:
- Some index features work differently
- Compound key deletion uses AND conditions instead of row value constructors

## Type Detection

Automatically detects column types from CSV data.

### Supported Types

| Type | Example Values | Notes |
|------|---------------|-------|
| INTEGER | `1`, `42`, `-100`, `2147483647` | PostgreSQL INTEGER (-2^31 to 2^31-1) |
| BIGINT | `815230591184000000`, `9223372036854775807` | Large integers exceeding INTEGER range |
| FLOAT | `3.14`, `-0.5`, `1.23e-4` | Floating point numbers |
| DATE | `2024-01-15`, `2024-12-31` | Date values |
| TEXT | `Alice`, `alice@example.com` | Text strings |

### Nullable Detection

Columns with empty values are marked as nullable:

```csv
user_id,name,email,notes
1,Alice,alice@example.com,
2,Bob,bob@example.com,Admin
```

Result:
- `notes`: `TEXT NULL` (has empty value)
- `name`: `TEXT NOT NULL` (always has value)

### Override Types

Specify types explicitly in configuration:

```yaml
filename_to_column:
  template: "data_[version].csv"
  columns:
    version:
      db_column: file_version
      type: varchar(10)  # Override detected type
```

## CDF File Support

Data-sync has built-in support for Common Data Format (CDF) science data files.

### CDF to Database Sync

Automatically extract CDF files to CSV and sync to database:

```bash
crump sync science_data.cdf --config crump_config.yml --job my_job --db-url postgresql://localhost/mydb
```

**How it works**:
1. CDF file is extracted to temporary CSV files
2. CSV data is processed using job configuration
3. Data is synced to database with all transformations applied
4. Temporary files are cleaned up automatically

### CDF Extraction Modes

The `extract` command supports two modes for CDF files:

#### Raw Extraction Mode

Extracts all CDF variables to CSV files without configuration:

```bash
# Extract all variables
crump extract science_data.cdf

# Extract specific variables
crump extract data.cdf -v epoch -v vectors

# Limit records for testing
crump extract data.cdf --max-records 100
```

**Features**:
- Automatic column naming from CDF metadata
- Array variables expanded into multiple columns
- Optionally merge variables with same record count
- Customizable output filenames

#### Config-Based Extraction Mode

Apply the same column mappings and transformations as `sync` command, but output to CSV:

```bash
# Extract with column selection and mapping
crump extract science_data.cdf --config crump_config.yml --job vectors_job

# Multiple files with transformations
crump extract *.cdf --config crump_config.yml --job my_job -o output/
```

**Features**:
- Same column selection as sync command
- Column renaming and type conversion
- Lookup transformations, expressions, and custom functions
- Filename-based value extraction
- Produces CSV that mirrors what would be synced to database

### Use Cases

**Preview data before syncing**:
```bash
# Extract with config to see what will be synced
crump extract data.cdf --config crump_config.yml --job my_job --max-records 10

# Review the output CSV
head output.csv

# If satisfied, sync to database
crump sync data.cdf --config crump_config.yml --job my_job
```

**Generate processed CSV files**:
```bash
# Apply transformations and save as CSV for other tools
crump extract *.cdf --config crump_config.yml --job processed_data -o ./processed/
```

**Test configurations**:
```bash
# Test with limited records
crump extract test_data.cdf --config crump_config.yml --job my_job --max-records 100

# Verify output matches expectations
python validate_output.py output.csv
```

### CDF Variable Handling

**Array Variables**: Automatically expanded into multiple columns
- 1D array `B_field[3]` becomes `B_field_0`, `B_field_1`, `B_field_2`
- Column names use CDF labels when available

**Automerge**: Variables with same record count are merged into single CSV (configurable)

**Metadata**: CDF attributes and labels are used for intelligent column naming

## Sync History Tracking

Track detailed sync operation history in a `_crump_history` table for auditing and monitoring.

### Enabling History

Add the `--history` flag to record sync operations:

```bash
crump sync data.csv --config crump_config.yml --job my_job --history
```

### History Table Schema

The `_crump_history` table is automatically created with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | TIMESTAMP | When the sync started (UTC, primary key) |
| `filename` | TEXT | Name of the file being synced |
| `table_name` | TEXT | Target table name for the sync |
| `rows_upserted` | INTEGER | Number of rows inserted or updated |
| `rows_deleted` | INTEGER | Number of stale rows deleted |
| `data_hash` | TEXT | SHA256 hash of the data file |
| `schema_changed` | BOOLEAN | Whether schema changes were made |
| `duration_seconds` | FLOAT | Duration of the sync operation |
| `success` | BOOLEAN | Whether the sync succeeded |
| `error` | TEXT | Error message if sync failed (NULL if successful) |

### Use Cases

**Audit trail**:
```sql
-- View recent sync operations
SELECT timestamp, filename, table_name, rows_upserted, success
FROM _crump_history
ORDER BY timestamp DESC
LIMIT 10;
```

**Monitor for failures**:
```sql
-- Find failed syncs
SELECT timestamp, filename, error
FROM _crump_history
WHERE success = false
ORDER BY timestamp DESC;
```

**Track data changes**:
```sql
-- Files that caused schema changes
SELECT filename, table_name, timestamp
FROM _crump_history
WHERE schema_changed = true;
```

**Performance monitoring**:
```sql
-- Average sync duration by table
SELECT table_name, AVG(duration_seconds) as avg_duration
FROM _crump_history
WHERE success = true
GROUP BY table_name
ORDER BY avg_duration DESC;
```

**Detect duplicate syncs**:
```sql
-- Find files synced multiple times with same hash
SELECT filename, data_hash, COUNT(*) as sync_count
FROM _crump_history
WHERE success = true
GROUP BY filename, data_hash
HAVING COUNT(*) > 1;
```

### Features

- **Automatic table creation**: `_crump_history` table is created automatically if it doesn't exist
- **Error tracking**: Failed syncs are still recorded with error details
- **Data integrity**: File hashes help detect when same data is re-synced
- **Performance metrics**: Track sync duration for optimization
- **Schema tracking**: Know when schema changes occurred
- **No dry-run recording**: History is never recorded during `--dry-run` operations

### Example Workflow

```bash
# First sync - creates table and records history
crump sync sales_2024-01-15.csv --config crump_config.yml --job daily_sales --history

# Check history
psql -d mydb -c "SELECT * FROM _crump_history ORDER BY timestamp DESC LIMIT 1;"

# Second sync - updates data and records new history entry
crump sync sales_2024-01-16.csv --config crump_config.yml --job daily_sales --history

# View all sync operations
psql -d mydb -c "SELECT timestamp, filename, table_name, rows_upserted, rows_deleted, success FROM _crump_history;"
```

### Best Practices

- **Enable in production**: Use `--history` for production syncs to maintain audit trail
- **Disable in development**: Omit `--history` during development to avoid cluttering history
- **Monitor failures**: Set up alerts for `success = false` entries
- **Clean up old history**: Periodically archive or delete old history records
- **Track performance**: Use duration metrics to optimize large syncs

## Next Steps

- [Configuration Guide](configuration.md) - YAML configuration reference
- [CLI Reference](cli-reference.md) - Command-line options
- [API Reference](api-reference.md) - Python API documentation
