"""Integration tests for database synchronization with SQLite and PostgreSQL."""

import csv
from pathlib import Path

import pytest

from crump.config import CrumpConfig
from crump.database import DatabaseConnection, sync_file_to_db
from tests.db_test_utils import execute_query, get_table_columns, get_table_indexes


class TestDatabaseIntegration:
    """Integration tests with SQLite and PostgreSQL databases."""

    def test_sync_csv_with_column_mapping_and_exclusion(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing CSV with renamed column and excluded column.

        This test verifies:
        1. CSV with 3 columns: id, name (renamed to full_name), email (not synced)
        2. Idempotency: running twice doesn't duplicate or change data
        """
        from tests.test_helpers import create_config_file, create_csv_file

        # Create CSV file with 3 columns
        csv_file = tmp_path / "users.csv"
        create_csv_file(
            csv_file,
            ["user_id", "name", "email"],
            [
                {"user_id": "1", "name": "Alice", "email": "alice@example.com"},
                {"user_id": "2", "name": "Bob", "email": "bob@example.com"},
                {"user_id": "3", "name": "Charlie", "email": "charlie@example.com"},
            ],
        )

        # Create config file
        config_file = tmp_path / "crump_config.yml"
        create_config_file(
            config_file, "sync_users", "users", {"user_id": "id"}, {"name": "full_name"}
        )

        # Load config and get job
        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("sync_users")
        assert job is not None

        # First sync
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 3

        # Verify data in database
        columns = get_table_columns(db_url, "users")
        assert "id" in columns
        assert "full_name" in columns
        assert "email" not in columns  # This column should NOT be synced

        # Check data
        rows = execute_query(db_url, "SELECT id, full_name FROM users ORDER BY id")
        assert len(rows) == 3
        assert rows[0] == ("1", "Alice")
        assert rows[1] == ("2", "Bob")
        assert rows[2] == ("3", "Charlie")

        # Second sync (idempotency test)
        rows_synced_2 = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced_2 == 3

        # Verify data hasn't changed
        rows = execute_query(db_url, "SELECT id, full_name FROM users ORDER BY id")
        assert len(rows) == 3  # Still 3 rows, no duplicates
        assert rows[0] == ("1", "Alice")
        assert rows[1] == ("2", "Bob")
        assert rows[2] == ("3", "Charlie")

    def test_sync_all_columns(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing all columns when no specific columns are listed."""
        from tests.test_helpers import create_config_file, create_csv_file

        csv_file = tmp_path / "products.csv"
        create_csv_file(
            csv_file,
            ["product_id", "name", "price", "category"],
            [
                {"product_id": "P1", "name": "Widget", "price": "9.99", "category": "Tools"},
                {"product_id": "P2", "name": "Gadget", "price": "19.99", "category": "Electronics"},
            ],
        )

        config_file = tmp_path / "crump_config.yml"
        create_config_file(config_file, "sync_products", "products", {"product_id": "id"})

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("sync_products")
        assert job is not None

        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 2

        # Verify all columns were synced
        columns = get_table_columns(db_url, "products")
        assert "id" in columns
        assert "name" in columns
        assert "price" in columns
        assert "category" in columns

        rows = execute_query(db_url, "SELECT id, name, price, category FROM products ORDER BY id")
        assert len(rows) == 2
        assert rows[0] == ("P1", "Widget", "9.99", "Tools")
        assert rows[1] == ("P2", "Gadget", "19.99", "Electronics")

    def test_upsert_updates_existing_rows(self, tmp_path: Path, db_url: str) -> None:
        """Test that upserting updates existing rows instead of creating duplicates."""
        from tests.test_helpers import create_config_file, create_csv_file

        csv_file = tmp_path / "data.csv"

        # First version of data
        create_csv_file(csv_file, ["id", "value"], [{"id": "1", "value": "original"}])

        config_file = tmp_path / "crump_config.yml"
        create_config_file(config_file, "test_upsert", "test_data", {"id": "id"})

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_upsert")

        # First sync
        sync_file_to_db(csv_file, job, db_url)

        # Update the CSV with new value for same ID
        create_csv_file(csv_file, ["id", "value"], [{"id": "1", "value": "updated"}])

        # Second sync should update the row
        sync_file_to_db(csv_file, job, db_url)

        # Verify only one row exists with updated value
        count_result = execute_query(db_url, "SELECT COUNT(*) FROM test_data")
        assert count_result[0][0] == 1  # Still only one row

        row_result = execute_query(db_url, "SELECT id, value FROM test_data")
        assert row_result[0] == ("1", "updated")  # Value was updated

    def test_missing_csv_column_error(self, tmp_path: Path, db_url: str) -> None:
        """Test error when CSV is missing a required column."""
        csv_file = tmp_path / "incomplete.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id"])
            writer.writeheader()
            writer.writerow({"id": "1"})

        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  bad_job:
    target_table: test
    id_mapping:
      id: id
    columns:
      missing_column: value
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("bad_job")

        with DatabaseConnection(db_url) as db, pytest.raises(ValueError, match="not found in CSV"):
            db.sync_tabular_file(csv_file, job)

    def test_sync_with_filename_to_column(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with filename_to_column extracts and stores values."""
        # Create CSV file
        csv_file = tmp_path / "sales_2024-01-15.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["sale_id", "amount"])
            writer.writeheader()
            writer.writerow({"sale_id": "1", "amount": "100"})
            writer.writerow({"sale_id": "2", "amount": "200"})

        # Create config with filename_to_column
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
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
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("daily_sales")
        assert job is not None
        assert job.filename_to_column is not None

        # Extract values and sync
        filename_values = job.filename_to_column.extract_values_from_filename(csv_file)
        assert filename_values == {"date": "2024-01-15"}

        rows_synced = sync_file_to_db(csv_file, job, db_url, filename_values)
        assert rows_synced == 2

        # Verify date column was created and populated
        columns = get_table_columns(db_url, "sales")
        assert "sync_date" in columns

        rows = execute_query(db_url, "SELECT id, amount, sync_date FROM sales ORDER BY id")
        assert len(rows) == 2
        # For PostgreSQL: date becomes date object, for SQLite: stays as string
        if db_url.startswith("sqlite"):
            assert rows[0] == ("1", "100", "2024-01-15")
            assert rows[1] == ("2", "200", "2024-01-15")
        else:
            from datetime import date

            assert rows[0] == ("1", "100", date(2024, 1, 15))
            assert rows[1] == ("2", "200", date(2024, 1, 15))

    def test_delete_stale_records(self, tmp_path: Path, db_url: str) -> None:
        """Test that stale records are deleted after sync with filename_to_column."""
        # First sync with 3 records for date 2024-01-15
        csv_file = tmp_path / "data_2024-01-15.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "value": "A"})
            writer.writerow({"id": "2", "value": "B"})
            writer.writerow({"id": "3", "value": "C"})

        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  daily_data:
    target_table: data
    id_mapping:
      id: id
    filename_to_column:
      template: "data_[date].csv"
      columns:
        date:
          db_column: sync_date
          type: date
          use_to_delete_old_rows: true
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("daily_data")

        filename_values = job.filename_to_column.extract_values_from_filename(csv_file)
        rows_synced = sync_file_to_db(csv_file, job, db_url, filename_values)
        assert rows_synced == 3

        # Verify 3 records exist
        count_result = execute_query(
            db_url, "SELECT COUNT(*) FROM data WHERE sync_date = %s", ("2024-01-15",)
        )
        assert count_result[0][0] == 3

        # Second sync with only 2 records (ID 3 removed)
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "value": "A_updated"})
            writer.writerow({"id": "2", "value": "B_updated"})

        rows_synced_2 = sync_file_to_db(csv_file, job, db_url, filename_values)
        assert rows_synced_2 == 2

        # Verify only 2 records remain for this date
        rows = execute_query(
            db_url, "SELECT id, value FROM data WHERE sync_date = %s ORDER BY id", ("2024-01-15",)
        )
        assert len(rows) == 2
        assert rows[0] == ("1", "A_updated")
        assert rows[1] == ("2", "B_updated")

    def test_delete_stale_records_preserves_other_dates(self, tmp_path: Path, db_url: str) -> None:
        """Test that deleting stale records only affects matching date with filename_to_column."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  daily_data:
    target_table: multi_date_data
    id_mapping:
      id: id
    filename_to_column:
      template: "data_[date].csv"
      columns:
        date:
          db_column: sync_date
          type: date
          use_to_delete_old_rows: true
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("daily_data")

        # Sync data for 2024-01-15
        csv_file_1 = tmp_path / "data_2024-01-15.csv"
        with open(csv_file_1, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "value": "Day1"})
            writer.writerow({"id": "2", "value": "Day1"})

        filename_values_1 = job.filename_to_column.extract_values_from_filename(csv_file_1)
        sync_file_to_db(csv_file_1, job, db_url, filename_values_1)

        # Sync data for 2024-01-16
        csv_file_2 = tmp_path / "data_2024-01-16.csv"
        with open(csv_file_2, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "value": "Day2"})
            writer.writerow({"id": "2", "value": "Day2"})
            writer.writerow({"id": "3", "value": "Day2"})

        filename_values_2 = job.filename_to_column.extract_values_from_filename(csv_file_2)
        sync_file_to_db(csv_file_2, job, db_url, filename_values_2)

        # Verify total records (IDs 1,2 were updated to day 2, ID 3 was inserted)
        total_count_result = execute_query(db_url, "SELECT COUNT(*) FROM multi_date_data")
        assert total_count_result[0][0] == 3

        # Re-sync day 1 with only ID 1 (updating it back to day 1)
        with open(csv_file_1, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "value": "Day1_updated"})

        sync_file_to_db(csv_file_1, job, db_url, filename_values_1)

        # Verify: ID 1 updated back to day 1, IDs 2 and 3 still on day 2
        day1_count_result = execute_query(
            db_url,
            "SELECT COUNT(*) FROM multi_date_data WHERE sync_date = %s",
            ("2024-01-15",),
        )
        assert day1_count_result[0][0] == 1  # Only ID 1

        day2_count_result = execute_query(
            db_url,
            "SELECT COUNT(*) FROM multi_date_data WHERE sync_date = %s",
            ("2024-01-16",),
        )
        assert day2_count_result[0][0] == 2  # IDs 2 and 3

    def test_sync_with_typed_columns(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with explicit data types for columns."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  typed_data:
    target_table: products
    id_mapping:
      product_id: id
    columns:
      name: product_name
      price:
        db_column: unit_price
        type: float
      stock:
        db_column: quantity
        type: integer
      description:
        db_column: desc
        type: text
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("typed_data")

        # Create CSV with sample data
        csv_file = tmp_path / "products.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["product_id", "name", "price", "stock", "description"]
            )
            writer.writeheader()
            writer.writerow(
                {
                    "product_id": "1",
                    "name": "Widget",
                    "price": "19.99",
                    "stock": "100",
                    "description": "A useful widget",
                }
            )

        sync_file_to_db(csv_file, job, db_url)

        # Verify data was synced
        rows = execute_query(
            db_url, "SELECT id, product_name, unit_price, quantity FROM products ORDER BY id"
        )
        assert len(rows) == 1
        assert rows[0][0] == "1"
        assert rows[0][1] == "Widget"
        # Note: Values are stored as strings in CSV, databases may convert them

    def test_schema_evolution_add_columns(self, tmp_path: Path, db_url: str) -> None:
        """Test that new columns are automatically added to existing tables."""
        config_file = tmp_path / "crump_config.yml"

        # Initial sync with 2 columns
        config_file.write_text(r"""
jobs:
  evolving_data:
    target_table: customers
    id_mapping:
      customer_id: id
    columns:
      name: customer_name
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("evolving_data")

        csv_file = tmp_path / "customers.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["customer_id", "name"])
            writer.writeheader()
            writer.writerow({"customer_id": "1", "name": "Alice"})

        sync_file_to_db(csv_file, job, db_url)

        # Verify initial schema
        columns = get_table_columns(db_url, "customers")
        assert "id" in columns
        assert "customer_name" in columns
        assert "email" not in columns  # Not yet added

        # Update config to add new columns
        config_file.write_text(r"""
jobs:
  evolving_data:
    target_table: customers
    id_mapping:
      customer_id: id
    columns:
      name: customer_name
      email:
        db_column: email_address
        type: text
      age:
        db_column: customer_age
        type: integer
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("evolving_data")

        # Sync with new columns
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["customer_id", "name", "email", "age"])
            writer.writeheader()
            writer.writerow(
                {"customer_id": "2", "name": "Bob", "email": "bob@example.com", "age": "30"}
            )

        sync_file_to_db(csv_file, job, db_url)

        # Verify schema now includes new columns
        columns = get_table_columns(db_url, "customers")
        assert "id" in columns
        assert "customer_name" in columns
        assert "email_address" in columns  # New column added
        assert "customer_age" in columns  # New column added

        # Verify both rows exist (old one has NULL for new columns)
        rows = execute_query(db_url, "SELECT id, customer_name FROM customers ORDER BY id")
        assert len(rows) == 2
        assert rows[0] == ("1", "Alice")
        assert rows[1] == ("2", "Bob")

    @pytest.mark.parametrize("db_url", ["sqlite", "postgres"], indirect=True)
    def test_compound_primary_key(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with compound primary key."""
        from crump.config import ColumnMapping, CrumpJob
        from tests.test_helpers import create_csv_file

        # Create CSV with data
        csv_file = tmp_path / "sales.csv"
        create_csv_file(
            csv_file,
            ["store_id", "product_id", "quantity", "price"],
            [
                {"store_id": "1", "product_id": "A", "quantity": "10", "price": "9.99"},
                {"store_id": "1", "product_id": "B", "quantity": "5", "price": "19.99"},
                {"store_id": "2", "product_id": "A", "quantity": "8", "price": "9.99"},
            ],
        )

        # Create job with compound primary key
        job = CrumpJob(
            name="sales",
            target_table="sales",
            id_mapping=[
                ColumnMapping("store_id", "store_id"),
                ColumnMapping("product_id", "product_id"),
            ],
            columns=[
                ColumnMapping("quantity", "qty"),
                ColumnMapping("price", "price"),
            ],
        )

        # Sync data
        sync_file_to_db(csv_file, job, db_url)

        # Verify data
        rows = execute_query(
            db_url, "SELECT store_id, product_id, qty FROM sales ORDER BY store_id, product_id"
        )
        assert len(rows) == 3
        assert rows[0] == ("1", "A", "10")
        assert rows[1] == ("1", "B", "5")
        assert rows[2] == ("2", "A", "8")

        # Update existing row and add new row
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["store_id", "product_id", "quantity", "price"])
            writer.writeheader()
            writer.writerow(
                {"store_id": "1", "product_id": "A", "quantity": "15", "price": "9.99"}
            )  # Updated
            writer.writerow({"store_id": "1", "product_id": "B", "quantity": "5", "price": "19.99"})
            writer.writerow({"store_id": "2", "product_id": "A", "quantity": "8", "price": "9.99"})
            writer.writerow(
                {"store_id": "2", "product_id": "B", "quantity": "3", "price": "19.99"}
            )  # New

        sync_file_to_db(csv_file, job, db_url)

        # Verify update and insert
        rows = execute_query(
            db_url, "SELECT store_id, product_id, qty FROM sales ORDER BY store_id, product_id"
        )
        assert len(rows) == 4
        assert rows[0] == ("1", "A", "15")  # Updated quantity
        assert rows[3] == ("2", "B", "3")  # New row

    @pytest.mark.parametrize("db_url", ["sqlite", "postgres"], indirect=True)
    def test_single_column_index(self, tmp_path: Path, db_url: str) -> None:
        """Test creating single-column index."""
        from crump.config import ColumnMapping, CrumpJob, Index, IndexColumn
        from tests.test_helpers import create_csv_file

        # Create CSV
        csv_file = tmp_path / "users.csv"
        create_csv_file(
            csv_file,
            ["user_id", "email", "name"],
            [{"user_id": "1", "email": "alice@example.com", "name": "Alice"}],
        )

        # Create job with index
        job = CrumpJob(
            name="users",
            target_table="users",
            id_mapping=[ColumnMapping("user_id", "id")],
            columns=[
                ColumnMapping("email", "email"),
                ColumnMapping("name", "name"),
            ],
            indexes=[Index(name="idx_email", columns=[IndexColumn("email", "ASC")])],
        )

        # Sync data
        sync_file_to_db(csv_file, job, db_url)

        # Verify index exists
        indexes = get_table_indexes(db_url, "users")
        assert "idx_email" in indexes

        # Sync again - index should not be recreated (no error)
        sync_file_to_db(csv_file, job, db_url)

    @pytest.mark.parametrize("db_url", ["sqlite", "postgres"], indirect=True)
    def test_multi_column_index(self, tmp_path: Path, db_url: str) -> None:
        """Test creating multi-column index with different sort orders."""
        from crump.config import ColumnMapping, CrumpJob, Index, IndexColumn

        # Create CSV
        csv_file = tmp_path / "orders.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["order_id", "customer_id", "order_date", "total"]
            )
            writer.writeheader()
            writer.writerow(
                {
                    "order_id": "1",
                    "customer_id": "100",
                    "order_date": "2024-01-01",
                    "total": "50.00",
                }
            )

        # Create job with multi-column index
        job = CrumpJob(
            name="orders",
            target_table="orders",
            id_mapping=[ColumnMapping("order_id", "id")],
            columns=[
                ColumnMapping("customer_id", "customer_id"),
                ColumnMapping("order_date", "order_date"),
                ColumnMapping("total", "total"),
            ],
            indexes=[
                Index(
                    name="idx_customer_date",
                    columns=[
                        IndexColumn("customer_id", "ASC"),
                        IndexColumn("order_date", "DESC"),
                    ],
                )
            ],
        )

        # Sync data
        sync_file_to_db(csv_file, job, db_url)

        # Verify index exists
        indexes = get_table_indexes(db_url, "orders")
        assert "idx_customer_date" in indexes

    @pytest.mark.parametrize("db_url", ["sqlite", "postgres"], indirect=True)
    def test_multiple_indexes(self, tmp_path: Path, db_url: str) -> None:
        """Test creating multiple indexes on a table."""
        from crump.config import ColumnMapping, CrumpJob, Index, IndexColumn

        # Create CSV
        csv_file = tmp_path / "products.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["product_id", "name", "category", "price"])
            writer.writeheader()
            writer.writerow(
                {"product_id": "1", "name": "Widget", "category": "Tools", "price": "9.99"}
            )

        # Create job with multiple indexes
        job = CrumpJob(
            name="products",
            target_table="products",
            id_mapping=[ColumnMapping("product_id", "id")],
            columns=[
                ColumnMapping("name", "name"),
                ColumnMapping("category", "category"),
                ColumnMapping("price", "price"),
            ],
            indexes=[
                Index(name="idx_name", columns=[IndexColumn("name", "ASC")]),
                Index(name="idx_category", columns=[IndexColumn("category", "ASC")]),
                Index(
                    name="idx_category_price",
                    columns=[IndexColumn("category", "ASC"), IndexColumn("price", "DESC")],
                ),
            ],
        )

        # Sync data
        sync_file_to_db(csv_file, job, db_url)

        # Verify all indexes exist
        indexes = get_table_indexes(db_url, "products")
        assert "idx_name" in indexes
        assert "idx_category" in indexes
        assert "idx_category_price" in indexes

    def test_filename_to_column_multiple_values(self, tmp_path: Path, db_url: str) -> None:
        """Test extracting multiple values from filename with template syntax."""
        # Create CSV file with filename containing multiple values
        csv_file = tmp_path / "imap_level2_primary_20240115_v002.cdf"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["obs_id", "measurement"])
            writer.writeheader()
            writer.writerow({"obs_id": "1", "measurement": "42.5"})
            writer.writerow({"obs_id": "2", "measurement": "38.2"})

        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  obs_data:
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
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("obs_data")
        assert job is not None
        assert job.filename_to_column is not None

        # Extract values
        filename_values = job.filename_to_column.extract_values_from_filename(csv_file)
        assert filename_values == {
            "mission": "imap",
            "sensor": "primary",
            "date": "20240115",
            "version": "002",
        }

        # Sync data
        rows_synced = sync_file_to_db(csv_file, job, db_url, filename_values)
        assert rows_synced == 2

        # Verify all columns were created
        columns = get_table_columns(db_url, "observations")
        assert "mission_name" in columns
        assert "sensor_type" in columns
        assert "observation_date" in columns
        assert "file_version" in columns

        # Verify data was inserted with extracted values
        rows = execute_query(
            db_url,
            "SELECT id, measurement, mission_name, sensor_type, observation_date, file_version FROM observations ORDER BY id",
        )
        assert len(rows) == 2
        # For PostgreSQL: date becomes date object, for SQLite: stays as string
        if db_url.startswith("sqlite"):
            assert rows[0] == ("1", "42.5", "imap", "primary", "20240115", "002")
            assert rows[1] == ("2", "38.2", "imap", "primary", "20240115", "002")
        else:
            from datetime import date

            assert rows[0] == ("1", "42.5", "imap", "primary", date(2024, 1, 15), "002")
            assert rows[1] == ("2", "38.2", "imap", "primary", date(2024, 1, 15), "002")

    def test_filename_to_column_regex_syntax(self, tmp_path: Path, db_url: str) -> None:
        """Test extracting values from filename with regex syntax."""
        csv_file = tmp_path / "data_20240315_v1.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["record_id", "value"])
            writer.writeheader()
            writer.writerow({"record_id": "1", "value": "test"})

        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  versioned_data:
    target_table: versioned_records
    id_mapping:
      record_id: id
    filename_to_column:
      regex: "data_(?P<date>\\d{8})_v(?P<version>\\d+)\\.csv"
      columns:
        date:
          db_column: record_date
          type: date
          use_to_delete_old_rows: true
        version:
          db_column: data_version
          type: integer
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("versioned_data")

        # Extract values using regex
        filename_values = job.filename_to_column.extract_values_from_filename(csv_file)
        assert filename_values == {"date": "20240315", "version": "1"}

        # Sync data
        rows_synced = sync_file_to_db(csv_file, job, db_url, filename_values)
        assert rows_synced == 1

        # Verify data
        rows = execute_query(
            db_url, "SELECT id, value, record_date, data_version FROM versioned_records"
        )
        assert len(rows) == 1
        # For SQLite: date stays as string, version becomes integer
        # For PostgreSQL: date becomes date object, version becomes integer
        if db_url.startswith("sqlite"):
            assert rows[0] == ("1", "test", "20240315", 1)
        else:
            from datetime import date

            assert rows[0] == ("1", "test", date(2024, 3, 15), 1)

    def test_filename_to_column_compound_key_can_update_filename_columns_in_a_later_file_meaning_stale_detection_does_not_locate_them(
        self, tmp_path: Path, db_url: str
    ) -> None:
        """Test stale record deletion using compound key from filename values."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  mission_data:
    target_table: mission_records
    id_mapping:
      obs_id: id
    filename_to_column:
      template: "[mission]_[date]_v[version].csv"
      columns:
        mission:
          db_column: mission_name
          type: varchar(20)
          use_to_delete_old_rows: true
        date:
          db_column: observation_date
          type: date
          use_to_delete_old_rows: true
        version:
          db_column: file_version
          type: varchar(10)
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("mission_data")

        # First sync: mission A, date 2024-01-15, version v1
        csv_file_1 = tmp_path / "missionA_2024-01-15_v1.csv"
        with open(csv_file_1, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["obs_id", "value"])
            writer.writeheader()
            writer.writerow({"obs_id": "1", "value": "A1"})
            writer.writerow({"obs_id": "2", "value": "A2"})
            writer.writerow({"obs_id": "3", "value": "A3"})

        filename_values_1 = job.filename_to_column.extract_values_from_filename(csv_file_1)
        sync_file_to_db(csv_file_1, job, db_url, filename_values_1)

        # Second sync: mission A, different date, version v1
        csv_file_2 = tmp_path / "missionA_2024-01-16_v1.csv"
        with open(csv_file_2, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["obs_id", "value"])
            writer.writeheader()
            writer.writerow({"obs_id": "1", "value": "A1_day2"})
            writer.writerow({"obs_id": "4", "value": "A2_day2"})

        filename_values_2 = job.filename_to_column.extract_values_from_filename(csv_file_2)
        sync_file_to_db(csv_file_2, job, db_url, filename_values_2)

        # Verify we have 4 records total:
        # - 2 for missionA + 2024-01-15 (IDs 2,3 plus the now updated ID 1)
        # - 2 for missionA + 2024-01-16 (IDs 4 and ID 1 again but with updated value)
        total_count = execute_query(db_url, "SELECT COUNT(*) FROM mission_records")
        assert total_count[0][0] == 4

        # Re-sync first file with only 2 records (ID 3 removed)
        with open(csv_file_1, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["obs_id", "value"])
            writer.writeheader()
            writer.writerow({"obs_id": "1", "value": "A1_updated"})
            writer.writerow({"obs_id": "2", "value": "A2_updated"})

        sync_file_to_db(csv_file_1, job, db_url, filename_values_1)

        # Verify: Records for mission A + date 2024-01-15 only have IDs 1,2
        # Mission A + date 2024-01-16 should only have ID 4
        day1_count = execute_query(
            db_url,
            "SELECT COUNT(*) FROM mission_records WHERE mission_name = %s AND observation_date = %s",
            ("missionA", "2024-01-15"),
        )
        assert (
            day1_count[0][0] == 2
        )  # ID 3 removed, id 1 updated to the second file and then back to the first

        day2_count = execute_query(
            db_url,
            "SELECT COUNT(*) FROM mission_records WHERE mission_name = %s AND observation_date = %s",
            ("missionA", "2024-01-16"),
        )
        assert day2_count[0][0] == 1  # just id 4, id 1 was updated back to day 1

        total_after = execute_query(db_url, "SELECT COUNT(*) FROM mission_records")
        assert total_after[0][0] == 3  # 2 from day 1, 1 from day 2

    def test_filename_to_column_compound_key_will_remove_updated_stale_records(
        self, tmp_path: Path, db_url: str
    ) -> None:
        """Test stale record deletion using compound key from filename values."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  mission_data:
    target_table: mission_records
    id_mapping:
      obs_id: id
    filename_to_column:
      template: "[mission]_[date]_v[version].csv"
      columns:
        mission:
          db_column: mission_name
          type: varchar(20)
          use_to_delete_old_rows: true
        date:
          db_column: observation_date
          type: date
          use_to_delete_old_rows: true
        version:
          db_column: file_version
          type: varchar(10)
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("mission_data")

        # First sync: mission A, date 2024-01-15, version v1
        csv_file_1 = tmp_path / "missionA_2024-01-15_v1.csv"
        with open(csv_file_1, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["obs_id", "value"])
            writer.writeheader()
            writer.writerow({"obs_id": "1", "value": "A1"})
            writer.writerow({"obs_id": "2", "value": "A2"})
            writer.writerow({"obs_id": "3", "value": "A3"})

        filename_values_1 = job.filename_to_column.extract_values_from_filename(csv_file_1)
        sync_file_to_db(csv_file_1, job, db_url, filename_values_1)

        # Second sync: mission A, different date, version v1
        csv_file_2 = tmp_path / "missionA_2024-01-16_v1.csv"
        with open(csv_file_2, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["obs_id", "value"])
            writer.writeheader()
            writer.writerow({"obs_id": "1", "value": "A1"})
            writer.writerow({"obs_id": "2", "value": "A2"})
            writer.writerow({"obs_id": "3", "value": "A3_day3"})
            writer.writerow({"obs_id": "4", "value": "A2_day2"})

        filename_values_2 = job.filename_to_column.extract_values_from_filename(csv_file_2)
        sync_file_to_db(csv_file_2, job, db_url, filename_values_2)

        # Verify we have 4 records total:
        total_count = execute_query(db_url, "SELECT COUNT(*) FROM mission_records")
        assert total_count[0][0] == 4

        # 3rd sync - Re-sync second file with only 3 records (ID 2 removed) and an update to ID 4
        with open(csv_file_2, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["obs_id", "value"])
            writer.writeheader()
            writer.writerow({"obs_id": "1", "value": "A1"})
            writer.writerow({"obs_id": "3", "value": "A3_day3"})
            writer.writerow({"obs_id": "4", "value": "A2_day2_updated"})
        sync_file_to_db(csv_file_2, job, db_url, filename_values_2)

        # Verify: Records for mission A + date 2024-01-15 not there any more as were updated to date 2024-01-16
        day1_count = execute_query(
            db_url,
            "SELECT COUNT(*) FROM mission_records WHERE mission_name = %s AND observation_date = %s",
            ("missionA", "2024-01-15"),
        )
        assert day1_count[0][0] == 0  # all updated in day2

        day2_count = execute_query(
            db_url,
            "SELECT COUNT(*) FROM mission_records WHERE mission_name = %s AND observation_date = %s",
            ("missionA", "2024-01-16"),
        )
        assert day2_count[0][0] == 3  # IDs 1,3,4

        total_after = execute_query(db_url, "SELECT COUNT(*) FROM mission_records")
        assert total_after[0][0] == 3  # IDs 1,3,4


class TestBigintSupport:
    """Integration tests for bigint data type support."""

    @pytest.mark.parametrize("db_url", ["sqlite", "postgres"], indirect=True)
    def test_sync_csv_with_bigint_values(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing CSV with bigint values (large integers)."""
        from crump.config import ColumnMapping, CrumpJob

        # Create CSV with bigint values
        csv_file = tmp_path / "bigint_data.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "epoch", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "epoch": "815230591184000000", "value": "100"})
            writer.writerow({"id": "2", "epoch": "815230591184000001", "value": "200"})
            writer.writerow({"id": "3", "epoch": "999999999999999999", "value": "300"})

        # Create job with explicit bigint type for epoch column
        job = CrumpJob(
            name="bigint_test",
            target_table="bigint_table",
            id_mapping=[ColumnMapping("id", "id", data_type="integer")],
            columns=[
                ColumnMapping("epoch", "epoch", data_type="bigint"),
                ColumnMapping("value", "value", data_type="integer"),
            ],
        )

        # Sync data
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 3

        # Verify data was inserted correctly
        rows = execute_query(db_url, "SELECT id, epoch, value FROM bigint_table ORDER BY id")
        assert len(rows) == 3
        # Database returns integer types, not strings
        assert rows[0] == (1, 815230591184000000, 100)
        assert rows[1] == (2, 815230591184000001, 200)
        assert rows[2] == (3, 999999999999999999, 300)

        # Verify column types in database schema
        columns = get_table_columns(db_url, "bigint_table")
        assert "epoch" in columns

    @pytest.mark.parametrize("db_url", ["sqlite", "postgres"], indirect=True)
    def test_sync_csv_with_mixed_integer_and_bigint_values(
        self, tmp_path: Path, db_url: str
    ) -> None:
        """Test syncing CSV with mixed regular integers and bigint values."""
        from crump.config import ColumnMapping, CrumpJob

        # Create CSV with mixed small and large integer values
        csv_file = tmp_path / "mixed_bigint_data.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "epoch", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "epoch": "100", "value": "10"})  # Small integer
            writer.writerow({"id": "2", "epoch": "815230591184000000", "value": "200"})  # Bigint
            writer.writerow({"id": "3", "epoch": "500", "value": "30"})  # Small integer
            writer.writerow({"id": "4", "epoch": "999999999999999999", "value": "400"})  # Bigint

        # Create job with explicit bigint type for epoch column
        job = CrumpJob(
            name="mixed_bigint_test",
            target_table="mixed_bigint_table",
            id_mapping=[ColumnMapping("id", "id", data_type="integer")],
            columns=[
                ColumnMapping("epoch", "epoch", data_type="bigint"),
                ColumnMapping("value", "value", data_type="integer"),
            ],
        )

        # Sync data
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 4

        # Verify data was inserted correctly - mix of small and large values
        rows = execute_query(db_url, "SELECT id, epoch, value FROM mixed_bigint_table ORDER BY id")
        assert len(rows) == 4
        assert rows[0] == (1, 100, 10)  # Small value
        assert rows[1] == (2, 815230591184000000, 200)  # Large value
        assert rows[2] == (3, 500, 30)  # Small value
        assert rows[3] == (4, 999999999999999999, 400)  # Large value


class TestSamplePercentage:
    """Integration tests for sample_percentage feature."""

    def test_sync_with_sample_percentage_10(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with 10% sample (1 in 10 rows, plus first and last)."""
        from tests.test_helpers import create_csv_file

        # Create CSV with 25 rows
        csv_file = tmp_path / "data.csv"
        rows = [{"id": str(i), "value": f"row_{i}"} for i in range(25)]
        create_csv_file(csv_file, ["id", "value"], rows)

        # Create config with 10% sampling
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_sample:
    target_table: sample_test
    id_mapping:
      id: id
    sample_percentage: 10
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_sample")
        assert job is not None

        # Sync with sampling
        rows_synced = sync_file_to_db(csv_file, job, db_url)

        # Verify correct rows were synced
        # With 10%, we expect rows at indices: 0, 10, 20, 24 (last)
        # That's 4 rows total
        assert rows_synced == 4

        # Verify data in database
        rows_db = execute_query(
            db_url, "SELECT id, value FROM sample_test ORDER BY CAST(id AS INTEGER)"
        )
        assert len(rows_db) == 4
        assert rows_db[0] == ("0", "row_0")  # First row always included
        assert rows_db[1] == ("10", "row_10")  # 10% interval
        assert rows_db[2] == ("20", "row_20")  # 10% interval
        assert rows_db[3] == ("24", "row_24")  # Last row always included

    def test_sync_with_sample_percentage_50(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with 50% sample (1 in 2 rows, plus first and last)."""
        from tests.test_helpers import create_csv_file

        # Create CSV with 10 rows
        csv_file = tmp_path / "data.csv"
        rows = [{"id": str(i), "value": f"row_{i}"} for i in range(10)]
        create_csv_file(csv_file, ["id", "value"], rows)

        # Create config with 50% sampling
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_sample:
    target_table: sample_test_50
    id_mapping:
      id: id
    sample_percentage: 50
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_sample")
        assert job is not None

        # Sync with sampling
        rows_synced = sync_file_to_db(csv_file, job, db_url)

        # With 50%, we expect rows at indices: 0, 2, 4, 6, 8, 9 (last)
        # That's 6 rows total
        assert rows_synced == 6

        # Verify data in database
        rows_db = execute_query(
            db_url, "SELECT id FROM sample_test_50 ORDER BY CAST(id AS INTEGER)"
        )
        synced_ids = [row[0] for row in rows_db]
        assert synced_ids == ["0", "2", "4", "6", "8", "9"]

    def test_sync_with_sample_percentage_100(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with 100% sample (all rows)."""
        from tests.test_helpers import create_csv_file

        # Create CSV with 5 rows
        csv_file = tmp_path / "data.csv"
        rows = [{"id": str(i), "value": f"row_{i}"} for i in range(5)]
        create_csv_file(csv_file, ["id", "value"], rows)

        # Create config with 100% sampling
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_sample:
    target_table: sample_test_100
    id_mapping:
      id: id
    sample_percentage: 100
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_sample")
        assert job is not None

        # Sync with 100% sampling (should sync all rows)
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 5

        # Verify all rows in database
        count = execute_query(db_url, "SELECT COUNT(*) FROM sample_test_100")
        assert count[0][0] == 5

    def test_sync_without_sample_percentage(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing without sample_percentage (all rows)."""
        from tests.test_helpers import create_csv_file

        # Create CSV with 5 rows
        csv_file = tmp_path / "data.csv"
        rows = [{"id": str(i), "value": f"row_{i}"} for i in range(5)]
        create_csv_file(csv_file, ["id", "value"], rows)

        # Create config without sample_percentage
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_sample:
    target_table: sample_test_none
    id_mapping:
      id: id
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_sample")
        assert job is not None

        # Sync without sampling (should sync all rows)
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 5

        # Verify all rows in database
        count = execute_query(db_url, "SELECT COUNT(*) FROM sample_test_none")
        assert count[0][0] == 5

    def test_dry_run_with_sample_percentage(self, tmp_path: Path, db_url: str) -> None:
        """Test dry run with sample_percentage."""
        from crump.database import sync_file_to_db_dry_run
        from tests.test_helpers import create_csv_file

        # Create CSV with 25 rows
        csv_file = tmp_path / "data.csv"
        rows = [{"id": str(i), "value": f"row_{i}"} for i in range(25)]
        create_csv_file(csv_file, ["id", "value"], rows)

        # Create config with 10% sampling
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_sample:
    target_table: sample_test_dry
    id_mapping:
      id: id
    sample_percentage: 10
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_sample")
        assert job is not None

        # Dry run
        summary = sync_file_to_db_dry_run(csv_file, job, db_url)

        # Verify dry run summary
        assert summary.table_name == "sample_test_dry"
        assert summary.table_exists is False
        # With 10% sampling, we expect 4 rows (0, 10, 20, 24)
        assert summary.rows_to_sync == 4
        assert summary.rows_to_delete == 0


class TestColumnLookup:
    """Integration tests for column lookup feature."""

    def test_sync_with_lookup_string_to_int(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with lookup mapping strings to integers."""
        from tests.test_helpers import create_csv_file

        # Create CSV with string status values
        csv_file = tmp_path / "users.csv"
        rows = [
            {"user_id": "1", "name": "Alice", "status": "active"},
            {"user_id": "2", "name": "Bob", "status": "inactive"},
            {"user_id": "3", "name": "Charlie", "status": "pending"},
        ]
        create_csv_file(csv_file, ["user_id", "name", "status"], rows)

        # Create config with lookup
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_lookup:
    target_table: users_with_lookup
    id_mapping:
      user_id: id
    columns:
      name: full_name
      status:
        db_column: status_code
        type: integer
        lookup:
          active: 1
          inactive: 0
          pending: 2
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_lookup")
        assert job is not None

        # Sync with lookup
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 3

        # Verify data was transformed
        rows_db = execute_query(
            db_url, "SELECT id, full_name, status_code FROM users_with_lookup ORDER BY id"
        )
        assert len(rows_db) == 3
        assert rows_db[0] == ("1", "Alice", 1)  # "active" -> 1
        assert rows_db[1] == ("2", "Bob", 0)  # "inactive" -> 0
        assert rows_db[2] == ("3", "Charlie", 2)  # "pending" -> 2

    def test_sync_with_lookup_passthrough_unknown_values(self, tmp_path: Path, db_url: str) -> None:
        """Test that values not in lookup are passed through unchanged."""
        from tests.test_helpers import create_csv_file

        # Create CSV with some unknown status values
        csv_file = tmp_path / "users.csv"
        rows = [
            {"user_id": "1", "status": "active"},
            {"user_id": "2", "status": "inactive"},
            {"user_id": "3", "status": "unknown_status"},
        ]
        create_csv_file(csv_file, ["user_id", "status"], rows)

        # Create config with lookup
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_lookup:
    target_table: users_lookup_passthrough
    id_mapping:
      user_id: id
    columns:
      status:
        db_column: status_code
        lookup:
          active: 1
          inactive: 0
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_lookup")
        assert job is not None

        # Sync with lookup
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 3

        # Verify data - unknown values passed through
        rows_db = execute_query(
            db_url, "SELECT id, status_code FROM users_lookup_passthrough ORDER BY id"
        )
        assert len(rows_db) == 3
        assert rows_db[0] == ("1", "1")  # "active" -> 1 (but stored as string)
        assert rows_db[1] == ("2", "0")  # "inactive" -> 0 (but stored as string)
        assert rows_db[2] == ("3", "unknown_status")  # Passed through unchanged

    def test_sync_with_lookup_string_to_string(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with lookup mapping strings to different strings."""
        from tests.test_helpers import create_csv_file

        # Create CSV with abbreviated size codes
        csv_file = tmp_path / "products.csv"
        rows = [
            {"product_id": "1", "name": "T-Shirt", "size": "S"},
            {"product_id": "2", "name": "Pants", "size": "M"},
            {"product_id": "3", "name": "Jacket", "size": "L"},
            {"product_id": "4", "name": "Coat", "size": "XL"},
        ]
        create_csv_file(csv_file, ["product_id", "name", "size"], rows)

        # Create config with lookup for size expansion
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_lookup:
    target_table: products_lookup
    id_mapping:
      product_id: id
    columns:
      name: product_name
      size:
        db_column: size_full
        lookup:
          S: Small
          M: Medium
          L: Large
          XL: Extra Large
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_lookup")
        assert job is not None

        # Sync with lookup
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 4

        # Verify data was transformed
        rows_db = execute_query(
            db_url, "SELECT id, product_name, size_full FROM products_lookup ORDER BY id"
        )
        assert len(rows_db) == 4
        assert rows_db[0] == ("1", "T-Shirt", "Small")
        assert rows_db[1] == ("2", "Pants", "Medium")
        assert rows_db[2] == ("3", "Jacket", "Large")
        assert rows_db[3] == ("4", "Coat", "Extra Large")

    def test_sync_with_multiple_lookup_columns(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with multiple columns having lookups."""
        from tests.test_helpers import create_csv_file

        # Create CSV with multiple lookup columns
        csv_file = tmp_path / "orders.csv"
        rows = [
            {"order_id": "1", "status": "pending", "priority": "high"},
            {"order_id": "2", "status": "shipped", "priority": "low"},
            {"order_id": "3", "status": "delivered", "priority": "medium"},
        ]
        create_csv_file(csv_file, ["order_id", "status", "priority"], rows)

        # Create config with lookups for both columns
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_lookup:
    target_table: orders_lookup
    id_mapping:
      order_id: id
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
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_lookup")
        assert job is not None

        # Sync with lookups
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 3

        # Verify both columns were transformed
        rows_db = execute_query(
            db_url, "SELECT id, status_code, priority_level FROM orders_lookup ORDER BY id"
        )
        assert len(rows_db) == 3
        assert rows_db[0] == ("1", 1, 3)  # pending -> 1, high -> 3
        assert rows_db[1] == ("2", 2, 1)  # shipped -> 2, low -> 1
        assert rows_db[2] == ("3", 3, 2)  # delivered -> 3, medium -> 2


class TestCustomFunctions:
    """Integration tests for custom function column mappings."""

    def test_sync_with_expression(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with inline expression for calculated column."""
        from tests.test_helpers import create_csv_file

        # Create CSV with resource usage data
        csv_file = tmp_path / "resources.csv"
        rows = [
            {"id": "1", "consumed": "30", "total_available": "100"},
            {"id": "2", "consumed": "75", "total_available": "150"},
            {"id": "3", "consumed": "10", "total_available": "50"},
        ]
        create_csv_file(csv_file, ["id", "consumed", "total_available"], rows)

        # Create config with expression for percentage calculation
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_expression:
    target_table: resources_expr
    id_mapping:
      id: id
    columns:
      consumed: consumed
      total_available: total_available
      ~:
        db_column: percentage_available
        expression: "((float(total_available) - float(consumed)) / float(total_available)) * 100"
        input_columns: [consumed, total_available]
        type: float
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_expression")
        assert job is not None

        # Sync with expression
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 3

        # Verify calculated column
        rows_db = execute_query(
            db_url,
            "SELECT id, consumed, total_available, percentage_available FROM resources_expr ORDER BY id",
        )
        assert len(rows_db) == 3
        assert rows_db[0] == ("1", "30", "100", 70.0)
        assert rows_db[1] == ("2", "75", "150", 50.0)
        assert rows_db[2] == ("3", "10", "50", 80.0)

    def test_sync_with_external_function(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with external function for calculated column."""
        from tests.test_helpers import create_csv_file

        # Create CSV with resource usage data
        csv_file = tmp_path / "resources.csv"
        rows = [
            {"id": "1", "consumed": "30", "total_available": "100"},
            {"id": "2", "consumed": "50", "total_available": "200"},
        ]
        create_csv_file(csv_file, ["id", "consumed", "total_available"], rows)

        # Create config with external function
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_function:
    target_table: resources_func
    id_mapping:
      id: id
    columns:
      consumed: consumed
      total_available: total_available
      ~:
        db_column: percentage_available
        function: "tests.custom_functions.calculate_percentage"
        input_columns: [consumed, total_available]
        type: float
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_function")
        assert job is not None

        # Sync with function
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 2

        # Verify calculated column
        rows_db = execute_query(
            db_url,
            "SELECT id, consumed, total_available, percentage_available FROM resources_func ORDER BY id",
        )
        assert len(rows_db) == 2
        assert rows_db[0] == ("1", "30", "100", 70.0)
        assert rows_db[1] == ("2", "50", "200", 75.0)

    def test_sync_with_string_concatenation(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with custom function for string concatenation."""
        from tests.test_helpers import create_csv_file

        # Create CSV with name parts
        csv_file = tmp_path / "names.csv"
        rows = [
            {"id": "1", "first_name": "John", "last_name": "Doe"},
            {"id": "2", "first_name": "Jane", "last_name": "Smith"},
        ]
        create_csv_file(csv_file, ["id", "first_name", "last_name"], rows)

        # Create config with external function for concatenation
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_concat:
    target_table: names_concat
    id_mapping:
      id: id
    columns:
      first_name: first_name
      last_name: last_name
      ~:
        db_column: full_name
        function: "tests.custom_functions.concatenate_strings"
        input_columns: [first_name, last_name]
        type: text
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_concat")
        assert job is not None

        # Sync with function
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 2

        # Verify concatenated column
        rows_db = execute_query(
            db_url,
            "SELECT id, first_name, last_name, full_name FROM names_concat ORDER BY id",
        )
        assert len(rows_db) == 2
        assert rows_db[0] == ("1", "John", "Doe", "John Doe")
        assert rows_db[1] == ("2", "Jane", "Smith", "Jane Smith")

    def test_sync_with_multiple_custom_functions(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with multiple custom function columns."""
        from tests.test_helpers import create_csv_file

        # Create CSV with order data
        csv_file = tmp_path / "orders.csv"
        rows = [
            {
                "order_id": "1",
                "price": "10.5",
                "quantity": "3",
                "first_name": "John",
                "last_name": "Doe",
            },
            {
                "order_id": "2",
                "price": "25.0",
                "quantity": "2",
                "first_name": "Jane",
                "last_name": "Smith",
            },
        ]
        create_csv_file(
            csv_file, ["order_id", "price", "quantity", "first_name", "last_name"], rows
        )

        # Create config with multiple custom functions
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_multi:
    target_table: orders_multi
    id_mapping:
      order_id: id
    columns:
      price: price
      quantity: quantity
      ~:
        db_column: total_price
        function: "tests.custom_functions.calculate_total"
        input_columns: [price, quantity]
        type: float
      ~:
        db_column: customer_name
        function: "tests.custom_functions.concatenate_strings"
        input_columns: [first_name, last_name]
        type: text
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_multi")
        assert job is not None

        # Sync with multiple functions
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 2

        # Verify both calculated columns
        rows_db = execute_query(
            db_url,
            "SELECT id, price, quantity, total_price, customer_name FROM orders_multi ORDER BY id",
        )
        assert len(rows_db) == 2
        assert rows_db[0] == ("1", "10.5", "3", 31.5, "John Doe")
        assert rows_db[1] == ("2", "25.0", "2", 50.0, "Jane Smith")

    def test_dry_run_with_custom_function(self, tmp_path: Path, db_url: str) -> None:
        """Test dry-run mode with custom function."""
        from crump.database import sync_file_to_db_dry_run
        from tests.test_helpers import create_csv_file

        # Create CSV
        csv_file = tmp_path / "data.csv"
        rows = [
            {"id": "1", "consumed": "40", "total_available": "100"},
            {"id": "2", "consumed": "20", "total_available": "80"},
        ]
        create_csv_file(csv_file, ["id", "consumed", "total_available"], rows)

        # Create config with expression
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_dryrun:
    target_table: dryrun_func
    id_mapping:
      id: id
    columns:
      ~:
        db_column: percentage
        expression: "((float(total_available) - float(consumed)) / float(total_available)) * 100"
        input_columns: [consumed, total_available]
        type: float
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_dryrun")
        assert job is not None

        # Run dry-run
        summary = sync_file_to_db_dry_run(csv_file, job, db_url)

        assert summary.table_name == "dryrun_func"
        assert not summary.table_exists
        assert summary.rows_to_sync == 2
        # When table doesn't exist, new_columns should be empty (whole table is new)
        assert len(summary.new_columns) == 0

    def test_sync_with_named_column_expression(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with expression on a named CSV column."""
        from tests.test_helpers import create_csv_file

        # Create CSV with temperature data in Celsius
        csv_file = tmp_path / "temperatures.csv"
        rows = [
            {"id": "1", "temperature": "0"},
            {"id": "2", "temperature": "100"},
            {"id": "3", "temperature": "37"},
        ]
        create_csv_file(csv_file, ["id", "temperature"], rows)

        # Create config with expression to convert Celsius to Fahrenheit
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_named:
    target_table: temps_named
    id_mapping:
      id: id
    columns:
      temperature:
        db_column: temp_fahrenheit
        expression: "float(temperature) * 1.8 + 32"
        input_columns: [temperature]
        type: float
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_named")
        assert job is not None

        # Sync with expression
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 3

        # Verify transformed values
        rows_db = execute_query(db_url, "SELECT id, temp_fahrenheit FROM temps_named ORDER BY id")
        assert len(rows_db) == 3
        assert rows_db[0][0] == "1" and rows_db[0][1] == pytest.approx(32.0)  # 0°C = 32°F
        assert rows_db[1][0] == "2" and rows_db[1][1] == pytest.approx(212.0)  # 100°C = 212°F
        assert rows_db[2][0] == "3" and rows_db[2][1] == pytest.approx(98.6)  # 37°C = 98.6°F

    def test_sync_with_named_column_external_function(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with external function on a named CSV column."""
        from tests.test_helpers import create_csv_file

        # Create CSV with temperature data in Celsius
        csv_file = tmp_path / "temperatures.csv"
        rows = [
            {"id": "1", "temperature": "0"},
            {"id": "2", "temperature": "25"},
        ]
        create_csv_file(csv_file, ["id", "temperature"], rows)

        # Create config with external function
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_named_func:
    target_table: temps_func
    id_mapping:
      id: id
    columns:
      temperature:
        db_column: temp_fahrenheit
        function: "tests.custom_functions.celsius_to_fahrenheit"
        input_columns: [temperature]
        type: float
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_named_func")
        assert job is not None

        # Sync with function
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 2

        # Verify transformed values
        rows_db = execute_query(db_url, "SELECT id, temp_fahrenheit FROM temps_func ORDER BY id")
        assert len(rows_db) == 2
        assert rows_db[0] == ("1", 32.0)  # 0°C = 32°F
        assert rows_db[1] == ("2", 77.0)  # 25°C = 77°F

    def test_sync_with_polynomial_transformation(self, tmp_path: Path, db_url: str) -> None:
        """Test syncing with polynomial calibration on a named column."""
        from tests.test_helpers import create_csv_file

        # Create CSV with raw sensor values
        csv_file = tmp_path / "sensors.csv"
        rows = [
            {"id": "1", "raw_value": "10"},
            {"id": "2", "raw_value": "20"},
            {"id": "3", "raw_value": "50"},
        ]
        create_csv_file(csv_file, ["id", "raw_value"], rows)

        # Create config with polynomial calibration
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_poly:
    target_table: sensors_calibrated
    id_mapping:
      id: id
    columns:
      raw_value:
        db_column: calibrated_value
        expression: "0.01 * float(raw_value)**2 + 1.5 * float(raw_value) + 2"
        input_columns: [raw_value]
        type: float
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_poly")
        assert job is not None

        # Sync with polynomial
        rows_synced = sync_file_to_db(csv_file, job, db_url)
        assert rows_synced == 3

        # Verify calibrated values: y = 0.01*x^2 + 1.5*x + 2
        rows_db = execute_query(
            db_url, "SELECT id, calibrated_value FROM sensors_calibrated ORDER BY id"
        )
        assert len(rows_db) == 3
        assert rows_db[0] == ("1", 18.0)  # 0.01*100 + 1.5*10 + 2 = 18
        assert rows_db[1] == ("2", 36.0)  # 0.01*400 + 1.5*20 + 2 = 36
        assert rows_db[2] == ("3", 102.0)  # 0.01*2500 + 1.5*50 + 2 = 102
