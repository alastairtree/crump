# Configuration Guide

The configuration file is a YAML file that defines sync jobs. Each job specifies how to sync a CSV file to a database table.

## Basic Configuration

A minimal configuration looks like this:

```yaml
jobs:
  my_job:
    target_table: users
    id_mapping:
      user_id: id
```

## Configuration Reference

### Job Structure

Each job has the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target_table` | string | Yes | Name of the database table |
| `id_mapping` | dict | Yes | Mapping for primary key column(s) |
| `columns` | dict | No | Column mappings (CSV → DB). If omitted, syncs all columns |
| `filename_to_column` | object | No | Extract values from filename to database columns |
| `indexes` | list | No | Database indexes to create |
| `sample_percentage` | float | No | Percentage of rows to sync (0-100). If omitted or 100, syncs all rows |

### ID Mapping

The `id_mapping` defines which column(s) form the primary key:

#### Single Primary Key

```yaml
id_mapping:
  user_id: id  # CSV column: DB column
```

#### Compound Primary Key

```yaml
id_mapping:
  store_id: store_id
  product_id: product_id
```

### Column Mapping

The `columns` field maps CSV columns to database columns:

```yaml
columns:
  name: full_name          # Rename: name → full_name
  email: email_address     # Rename: email → email_address
  status: status           # Keep same name
```

!!! tip
    If you omit the `columns` field entirely, all CSV columns are synced with their original names.

### Column Lookups

Transform CSV values to different values in the database using lookup dictionaries. This is useful for:

- Converting human-readable strings to numeric codes (e.g., "active" → 1)
- Mapping abbreviations to full values (e.g., "S" → "Small")
- Standardizing inconsistent values
- Converting between different code systems

#### Basic Lookup

```yaml
columns:
  status:
    db_column: status_code
    type: integer
    lookup:
      active: 1
      inactive: 0
      pending: 2
```

This converts:
- `"active"` → `1`
- `"inactive"` → `0`
- `"pending"` → `2`
- Any other value passes through unchanged

#### Lookup Behavior

- **Matching values**: Transformed according to the lookup dictionary
- **Non-matching values**: Passed through unchanged (no error)
- **Type conversion**: The `type` field defines the database type, allowing string-to-int conversions
- **Works with all column types**: Can be used with regular columns and id_mapping

#### Examples

**String to Integer (Status Codes):**
```yaml
columns:
  status:
    db_column: status_code
    type: integer
    lookup:
      active: 1
      inactive: 0
      suspended: -1
```

**String to String (Size Expansion):**
```yaml
columns:
  size:
    db_column: size_full
    lookup:
      S: Small
      M: Medium
      L: Large
      XL: Extra Large
```

**Multiple Lookup Columns:**
```yaml
columns:
  status:
    db_column: status_code
    type: integer
    lookup:
      pending: 1
      shipped: 2
      delivered: 3
  priority:
    db_column: priority_level
    type: integer
    lookup:
      low: 1
      medium: 2
      high: 3
```

**With Data Type and Nullable:**
```yaml
columns:
  category:
    db_column: category_id
    type: integer
    nullable: false
    lookup:
      electronics: 100
      clothing: 200
      food: 300
```

!!! note
    Lookups are applied **before** type conversion. For example, if you lookup `"active"` → `1` with `type: integer`, the value `1` is already an integer and will be stored correctly in an integer column.

### Custom Functions

Create calculated columns using Python expressions or external functions. This provides ultimate flexibility for complex data transformations that go beyond simple lookups or mappings.

#### Use Cases

- Calculate derived values (percentages, totals, ratios)
- Combine multiple columns into one (concatenation, formatting)
- Apply complex business logic
- Perform mathematical operations
- Format or transform data in custom ways

#### Inline Expressions

Use the `expression` field to define Python expressions that calculate values from other columns.

**Creating New Calculated Columns:**

Use `~` (null) as the column key when creating a new column:

```yaml
columns:
  consumed: consumed
  total_available: total_available
  ~:  # null key indicates this is a calculated column, not from CSV
    db_column: percentage_available
    expression: "((float(total_available) - float(consumed)) / float(total_available)) * 100"
    input_columns: [consumed, total_available]
    type: float
```

**Transforming Existing CSV Columns:**

Use the CSV column name as the key when transforming an existing column:

```yaml
columns:
  temperature:
    db_column: temp_fahrenheit
    expression: "float(temperature) * 1.8 + 32"
    input_columns: [temperature]
    type: float
```

This is useful for:
- Unit conversions (Celsius to Fahrenheit, meters to feet)
- Applying calibration formulas or polynomials
- Scaling or adjusting values
- Simple transformations on a single column

**Key points:**
- The `expression` is a Python expression evaluated for each row
- `input_columns` lists the CSV columns needed for the calculation
- CSV values are strings by default - use `float()`, `int()`, etc. for type conversion
- Available functions: `abs`, `min`, `max`, `round`, `int`, `float`, `str`, `bool`, `len`

#### External Functions

For complex logic, reference functions defined in separate Python modules:

```yaml
columns:
  first_name: first_name
  last_name: last_name
  ~:
    db_column: full_name
    function: "my_functions.concatenate_names"
    input_columns: [first_name, last_name]
    type: text
```

Create a Python module (e.g., `my_functions.py`):

```python
def concatenate_names(first: str, last: str) -> str:
    """Concatenate first and last name with proper formatting."""
    return f"{first} {last}".title()
```

**Key points:**
- Use `function` field with format `"module.function_name"`
- The module must be importable (in your Python path)
- Function parameters receive values in the order specified in `input_columns`
- All parameters are passed as strings (convert as needed in your function)
- Return value can be any type compatible with the specified `type`

#### Examples

**Example 1: Calculate Order Total**

```yaml
columns:
  price: unit_price
  quantity: quantity
  ~:
    db_column: total_price
    expression: "float(price) * float(quantity)"
    input_columns: [price, quantity]
    type: float
```

**Example 2: Combine Multiple Columns**

```yaml
columns:
  street: street
  city: city
  state: state
  zip: zip_code
  ~:
    db_column: full_address
    expression: "f'{street}, {city}, {state} {zip}'"
    input_columns: [street, city, state, zip]
    type: text
```

**Example 3: Multiple Calculated Columns**

```yaml
columns:
  price: price
  quantity: quantity
  tax_rate: tax_rate
  ~:
    db_column: subtotal
    expression: "float(price) * float(quantity)"
    input_columns: [price, quantity]
    type: float
  ~:
    db_column: tax_amount
    expression: "float(price) * float(quantity) * float(tax_rate)"
    input_columns: [price, quantity, tax_rate]
    type: float
```

**Example 4: Transform Named Column (Unit Conversion)**

```yaml
columns:
  temperature:
    db_column: temp_fahrenheit
    expression: "float(temperature) * 1.8 + 32"
    input_columns: [temperature]
    type: float
```

This transforms the `temperature` column from Celsius to Fahrenheit.

**Example 5: Polynomial Calibration**

```yaml
columns:
  raw_sensor_value:
    db_column: calibrated_value
    expression: "0.01 * float(raw_sensor_value)**2 + 1.5 * float(raw_sensor_value) + 2"
    input_columns: [raw_sensor_value]
    type: float
```

Applies a quadratic calibration formula to sensor readings.

**Example 6: External Function for Complex Logic**

```yaml
columns:
  temperature: temp_celsius
  ~:
    db_column: temp_fahrenheit
    function: "converters.celsius_to_fahrenheit"
    input_columns: [temperature]
    type: float
```

```python
# converters.py
def celsius_to_fahrenheit(celsius: str) -> float:
    """Convert Celsius to Fahrenheit."""
    c = float(celsius)
    return (c * 9/5) + 32
```

#### Constraints and Validation

- **Cannot specify both**: You cannot use `expression` and `function` together
- **Requires input_columns**: You must specify `input_columns` when using expressions or functions
- **Column naming**:
  - Use `~` (null key) for new calculated columns that don't exist in CSV
  - Use the CSV column name as key when transforming an existing column
- **Input column validation**: All columns in `input_columns` must exist in the CSV file
- **Error handling**: If an expression or function fails, the sync operation will fail with a detailed error message

#### Security Considerations

**Expression Safety:**
- Expressions are evaluated using Python's `eval()` with a restricted namespace
- Only safe built-in functions are available
- Cannot access file system, network, or other dangerous operations
- Still, only use expressions from trusted sources

**Function Safety:**
- External functions have full Python access
- Only use functions from trusted modules
- Validate and sanitize function logic before deployment

### Filename to Column

Extract values from filenames and store them in database columns:

#### Template Syntax

Use `[column_name]` placeholders in the template:

```yaml
filename_to_column:
  template: "sales_[date].csv"
  columns:
    date:
      db_column: sync_date
      type: date
      use_to_delete_old_rows: true
```

This matches files like `sales_2024-01-15.csv` and extracts `2024-01-15` into the `sync_date` column.

#### Regex Syntax

For more complex patterns, use regex with named groups:

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

This matches files like `imap_level2_primary_20240115_v002.cdf`.

#### Column Options

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `db_column` | string | No | Database column name (defaults to column name) |
| `type` | string | No | SQL data type (e.g., `date`, `varchar(10)`, `integer`) |
| `use_to_delete_old_rows` | boolean | No | Use this column to identify stale records for deletion |

#### Automatic Cleanup

When `use_to_delete_old_rows: true` is set, crump will:

1. Extract the value from the filename
2. Add it to all synced rows
3. Delete rows with matching values but IDs not in the current CSV
4. Preserve rows with different values

**Example Workflow:**

```bash
# Day 1: Sync sales for 2024-01-15
crump sync sales_2024-01-15.csv --config crump_config.yml --job daily_sales
# Result: Inserts 100 rows with sync_date = '2024-01-15'

# Day 2: Re-sync same date with corrections (only 95 rows)
crump sync sales_2024-01-15-corrected.csv --config crump_config.yml --job daily_sales
# Result: Updates 95 rows, deletes 5 stale rows for 2024-01-15
#         Rows for other dates are untouched
```

#### Compound Delete Keys

You can use multiple columns for identifying stale records:

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

This deletes stale rows only when ALL three values match.

### Indexes

Define database indexes to improve query performance:

```yaml
indexes:
  - name: idx_user_id
    columns:
      - column: user_id
        order: ASC
  - name: idx_created_at
    columns:
      - column: created_at
        order: DESC
  - name: idx_user_date
    columns:
      - column: user_id
        order: ASC
      - column: created_at
        order: DESC
```

#### Index Features

- Single or multi-column indexes
- Ascending (ASC) or descending (DESC) sort order
- Automatically created if they don't exist
- Works with both PostgreSQL and SQLite

#### Automatic Index Suggestions

The `prepare` command automatically suggests indexes:

```bash
crump prepare activity_log.csv --config crump_config.yml --job user_activity
```

Suggestion rules:

- **Date/datetime columns**: Get descending indexes (for recent-first queries)
- **Columns ending in `_id` or `_key`**: Get ascending indexes (for foreign key lookups)
- **ID column**: Excluded (already a primary key)

### Row Sampling

For large datasets, you can sync only a percentage of rows using the `sample_percentage` option. This is useful for:

- Testing sync jobs with large datasets
- Creating representative samples for development/staging environments
- Reducing sync time and database load

```yaml
jobs:
  large_dataset:
    target_table: events
    id_mapping:
      event_id: id
    sample_percentage: 10  # Sync 10% of rows (1 in every 10)
```

#### Sampling Behavior

- **Value range**: 0-100 (float values allowed, e.g., 12.5 for 12.5%)
- **Default**: `null` or `100` syncs all rows
- **First row**: Always included (regardless of percentage)
- **Last row**: Always included (regardless of percentage)
- **Interval**: Calculated as `100 / sample_percentage`

**Examples:**

- `sample_percentage: 10` → Syncs rows at indices 0, 10, 20, 30, ... and last row
- `sample_percentage: 50` → Syncs rows at indices 0, 2, 4, 6, 8, ... and last row
- `sample_percentage: 25` → Syncs rows at indices 0, 4, 8, 12, ... and last row

#### Example Use Cases

**Testing Configuration:**
```yaml
# Development environment - 1% sample for quick testing
dev_events:
  target_table: events
  id_mapping:
    event_id: id
  sample_percentage: 1
```

**Staging Environment:**
```yaml
# Staging - 10% sample for representative testing
staging_events:
  target_table: events
  id_mapping:
    event_id: id
  sample_percentage: 10
```

**Production:**
```yaml
# Production - full sync (omit sample_percentage)
prod_events:
  target_table: events
  id_mapping:
    event_id: id
```

!!! note
    Sampling is deterministic based on row position, not random. The same file will always produce the same sample. First and last rows are always included to ensure edge cases are tested.

## Complete Example

Here's a comprehensive configuration demonstrating all features:

```yaml
jobs:
  # Simple job - sync all columns
  users_sync:
    target_table: users
    id_mapping:
      user_id: id

  # Selective sync with renaming
  customers_sync:
    target_table: customers
    id_mapping:
      customer_id: id
    columns:
      first_name: fname
      last_name: lname
      email: email_address

  # Daily sales with date extraction and cleanup
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
      quantity: qty
    indexes:
      - name: idx_sync_date
        columns:
          - column: sync_date
            order: DESC
      - name: idx_product
        columns:
          - column: product_id
            order: ASC

  # Compound key with indexes
  sales_by_store:
    target_table: store_sales
    id_mapping:
      store_id: store_id
      product_id: product_id
    columns:
      quantity: qty
      price: price
    indexes:
      - name: idx_store_product
        columns:
          - column: store_id
            order: ASC
          - column: product_id
            order: ASC

  # Science data with complex filename pattern
  observation_data:
    target_table: observations
    id_mapping:
      obs_id: id
    filename_to_column:
      template: "[mission]_level2_[sensor]_[date]_v[version].cdf"
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
    indexes:
      - name: idx_obs_date
        columns:
          - column: observation_date
            order: DESC
      - name: idx_mission_sensor
        columns:
          - column: mission_name
            order: ASC
          - column: sensor_type
            order: ASC
```

## Best Practices

1. **Use the prepare command**: Let crump analyze your CSV and generate configuration automatically
2. **Start simple**: Begin with basic config, add features as needed
3. **Use dry-run mode**: Test configuration before running actual syncs
4. **Add indexes**: Define indexes for columns you'll query frequently
5. **Use filename extraction**: For time-series or versioned data, extract metadata from filenames
6. **Use lookups for standardization**: Transform inconsistent CSV values to standardized database values
7. **Compound keys carefully**: Only use when a single column isn't unique
8. **Document your jobs**: Use descriptive job names that explain what they do

## Next Steps

- [CLI Reference](cli-reference.md) - Learn about command-line options
- [Features](features.md) - Detailed feature documentation
- [API Reference](api-reference.md) - Use crump programmatically
