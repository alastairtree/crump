# Quick Start

This guide will get you syncing CSV files to PostgreSQL in 5 minutes.

## Step 1: Install crump

```bash
pip install crump
```

## Step 2: Prepare Your Data

Create a sample CSV file (`users.csv`):

```csv
user_id,name,email,notes
1,Alice,alice@example.com,Admin user
2,Bob,bob@example.com,Regular user
3,Charlie,charlie@example.com,Guest user
```

## Step 3: Create Configuration

You can either create a configuration file manually or use the `prepare` command to analyze your CSV and generate one automatically.

=== "Automatic (Recommended)"

    ```bash
    crump prepare users.csv --config crump_config.yml --job users_sync
    ```

    This will:
    - Analyze your CSV file
    - Detect column types
    - Suggest an ID column
    - Suggest indexes
    - Generate a configuration file

=== "Manual"

    Create `crump_config.yml`:

    ```yaml
    jobs:
      users_sync:
        target_table: users
        id_mapping:
          user_id: id
        columns:
          name: full_name
          email: email_address
    ```

## Step 4: Set Database URL

```bash
export DATABASE_URL="sqlite:///test.db"
```

## Step 5: Preview Changes (Optional)

Before syncing, you can preview what changes will be made:

```bash
crump sync users.csv --config crump_config.yml --job users_sync --dry-run
```

This shows:

- Schema changes (tables, columns, indexes to be created)
- Number of rows to be inserted/updated
- Number of stale rows to be deleted
- **Without actually modifying the database**

## Step 6: Sync Your Data

```bash
crump sync users.csv --config crump_config.yml --job users_sync
```

You should see output like:

```
Syncing users.csv using job 'users_sync'...
✓ Successfully synced 3 rows
  Table: users
  File: users.csv
```

## Step 7: Verify in Database

Connect to your database and verify the data:

```sql
SELECT * FROM users;
```

```
 id |   full_name   |   email_address
----+---------------+--------------------
  1 | Alice         | alice@example.com
  2 | Bob           | bob@example.com
  3 | Charlie       | charlie@example.com
```

## What Just Happened?

1. **Table Creation**: crump created the `users` table automatically
2. **Column Mapping**: CSV columns were renamed according to your config
3. **Type Detection**: Column types were inferred from your CSV data
4. **Primary Key**: The `user_id` column was mapped to `id` as the primary key
5. **Upsert**: Data was inserted using PostgreSQL's upsert mechanism

## Running Again

The sync is **idempotent** - you can run it multiple times safely:

```bash
# Update a row in users.csv
# Change Alice's email to alice.new@example.com

# Run sync again
crump sync users.csv --config crump_config.yml --job users_sync
```

The existing rows are updated, no duplicates are created.

## Next Steps

Now that you have the basics working, learn about more advanced features:

- [Configuration Guide](configuration.md) - Advanced YAML configuration
- [Features](features.md) - Learn about all features
  - Filename-based value extraction
  - Automatic stale record cleanup
  - Compound primary keys
  - Database indexes
- [CLI Reference](cli-reference.md) - All command-line options
- [API Reference](api-reference.md) - Use crump in your Python code

## Common Use Cases

### Daily Data Updates

Extract date from filename and automatically cleanup old data:

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
```

### Selective Column Sync

Only sync specific columns, ignore others:

```yaml
jobs:
  users_sync:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
      email: email
      # Other CSV columns are ignored
```

### Compound Primary Keys

Use multiple columns as the primary key:

```yaml
jobs:
  sales_by_store:
    target_table: sales
    id_mapping:
      store_id: store_id
      product_id: product_id
    columns:
      quantity: qty
      price: price
```
