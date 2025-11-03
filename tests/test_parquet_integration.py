"""Integration tests for Parquet file support."""

from pathlib import Path

from crump.config import CrumpConfig
from crump.database import sync_file_to_db
from crump.tabular_file import create_writer
from tests.db_test_utils import execute_query, get_table_columns


class TestParquetDatabaseIntegration:
    """Integration tests for syncing Parquet files to database."""

    def test_sync_parquet_basic(self, tmp_path: Path, db_url: str) -> None:
        """Test basic Parquet file sync to database."""
        # Create Parquet file
        parquet_file = tmp_path / "users.parquet"
        with create_writer(parquet_file) as writer:
            writer.writerow(["user_id", "name", "email"])
            writer.writerow(["1", "Alice", "alice@example.com"])
            writer.writerow(["2", "Bob", "bob@example.com"])
            writer.writerow(["3", "Charlie", "charlie@example.com"])

        # Create config file
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  sync_users:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
""")

        # Load config and get job
        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("sync_users")
        assert job is not None

        # Sync Parquet file
        rows_synced = sync_file_to_db(parquet_file, job, db_url)
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

    def test_sync_parquet_with_types(self, tmp_path: Path, db_url: str) -> None:
        """Test Parquet sync with different data types."""
        # Create Parquet file with mixed types
        parquet_file = tmp_path / "products.parquet"
        with create_writer(parquet_file) as writer:
            writer.writerow(["product_id", "name", "price", "in_stock"])
            writer.writerow(["P1", "Widget", 9.99, True])
            writer.writerow(["P2", "Gadget", 19.99, False])
            writer.writerow(["P3", "Tool", 14.50, True])

        # Create config file
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  sync_products:
    target_table: products
    id_mapping:
      product_id: id
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("sync_products")
        assert job is not None

        # Sync
        rows_synced = sync_file_to_db(parquet_file, job, db_url)
        assert rows_synced == 3

        # Verify data
        rows = execute_query(db_url, "SELECT id, name, price, in_stock FROM products ORDER BY id")
        assert len(rows) == 3
        assert rows[0][0] == "P1"
        assert rows[0][1] == "Widget"
        # Price might be float or string depending on database
        assert float(rows[0][2]) == 9.99

    def test_sync_parquet_idempotency(self, tmp_path: Path, db_url: str) -> None:
        """Test that syncing the same Parquet file twice is idempotent."""
        # Create Parquet file
        parquet_file = tmp_path / "data.parquet"
        with create_writer(parquet_file) as writer:
            writer.writerow(["id", "value"])
            writer.writerow(["A", "100"])
            writer.writerow(["B", "200"])

        # Create config file
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  sync_data:
    target_table: test_data
    id_mapping:
      id: id
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("sync_data")
        assert job is not None

        # First sync
        rows_synced_1 = sync_file_to_db(parquet_file, job, db_url)
        assert rows_synced_1 == 2

        # Second sync (idempotency test)
        rows_synced_2 = sync_file_to_db(parquet_file, job, db_url)
        assert rows_synced_2 == 2

        # Verify no duplicates
        rows = execute_query(db_url, "SELECT id, value FROM test_data ORDER BY id")
        assert len(rows) == 2
        assert rows[0] == ("A", "100")
        assert rows[1] == ("B", "200")

    def test_sync_parquet_update_existing(self, tmp_path: Path, db_url: str) -> None:
        """Test that syncing updated Parquet file updates existing records."""
        # Create initial Parquet file
        parquet_file = tmp_path / "inventory.parquet"
        with create_writer(parquet_file) as writer:
            writer.writerow(["sku", "quantity"])
            writer.writerow(["SKU001", 50])
            writer.writerow(["SKU002", 30])

        # Create config
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  sync_inventory:
    target_table: inventory
    id_mapping:
      sku: sku
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("sync_inventory")
        assert job is not None

        # First sync
        rows_synced = sync_file_to_db(parquet_file, job, db_url)
        assert rows_synced == 2

        # Verify initial data
        rows = execute_query(db_url, "SELECT sku, quantity FROM inventory ORDER BY sku")
        assert len(rows) == 2
        assert rows[0] == ("SKU001", "50")
        assert rows[1] == ("SKU002", "30")

        # Create updated Parquet file
        parquet_file_2 = tmp_path / "inventory_updated.parquet"
        with create_writer(parquet_file_2) as writer:
            writer.writerow(["sku", "quantity"])
            writer.writerow(["SKU001", 75])  # Updated
            writer.writerow(["SKU002", 30])  # Unchanged
            writer.writerow(["SKU003", 100])  # New

        # Sync updated file
        rows_synced_2 = sync_file_to_db(parquet_file_2, job, db_url)
        assert rows_synced_2 == 3

        # Verify updated data
        rows = execute_query(db_url, "SELECT sku, quantity FROM inventory ORDER BY sku")
        assert len(rows) == 3
        assert rows[0] == ("SKU001", "75")  # Updated
        assert rows[1] == ("SKU002", "30")  # Unchanged
        assert rows[2] == ("SKU003", "100")  # New
