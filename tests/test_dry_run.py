"""Tests for dry-run functionality."""

import csv
from pathlib import Path

from crump.config import (
    ColumnMapping,
    CrumpJob,
    FilenameColumnMapping,
    FilenameToColumn,
    Index,
    IndexColumn,
)
from crump.database import DatabaseConnection, sync_file_to_db_dry_run

from .db_test_utils import table_exists


def test_dry_run_summary_new_table(db_url: str, tmp_path: Path) -> None:
    """Test dry-run summary when table doesn't exist."""
    from tests.test_helpers import create_csv_file

    # Create a CSV file
    csv_file = tmp_path / "test.csv"
    create_csv_file(
        csv_file,
        ["user_id", "name", "email"],
        [
            {"user_id": "1", "name": "Alice", "email": "alice@example.com"},
            {"user_id": "2", "name": "Bob", "email": "bob@example.com"},
            {"user_id": "3", "name": "Charlie", "email": "charlie@example.com"},
        ],
    )

    # Create a sync job configuration
    job = CrumpJob(
        name="test_job",
        target_table="users",
        id_mapping=[ColumnMapping("user_id", "id")],
        columns=[
            ColumnMapping("name", "full_name"),
            ColumnMapping("email", "email_address"),
        ],
    )

    # Run dry-run
    summary = sync_file_to_db_dry_run(csv_file, job, db_url)

    # Verify summary
    assert summary.table_name == "users"
    assert not summary.table_exists
    assert summary.rows_to_sync == 3
    assert summary.rows_to_delete == 0
    assert len(summary.new_columns) == 0  # No columns to add since table doesn't exist
    assert len(summary.new_indexes) == 0

    # Verify no tables were created during dry-run
    assert not table_exists(db_url, "users"), "No tables should have been created during dry-run"


def test_dry_run_summary_existing_table_no_changes(db_url: str, tmp_path: Path) -> None:
    """Test dry-run when table exists and no schema changes needed."""
    from tests.test_helpers import create_csv_file

    # Create a CSV file
    csv_file = tmp_path / "test.csv"
    create_csv_file(
        csv_file,
        ["product_id", "name", "price"],
        [
            {"product_id": "1", "name": "Widget", "price": "19.99"},
            {"product_id": "2", "name": "Gadget", "price": "29.99"},
        ],
    )

    # First, create the table with actual data
    job = CrumpJob(
        name="test_job",
        target_table="products",
        id_mapping=[ColumnMapping("product_id", "id")],
        columns=[
            ColumnMapping("name", "name"),
            ColumnMapping("price", "price"),
        ],
    )

    with DatabaseConnection(db_url) as db:
        db.sync_tabular_file(csv_file, job)

    # Now run dry-run with same schema
    summary = sync_file_to_db_dry_run(csv_file, job, db_url)

    # Verify summary
    assert summary.table_name == "products"
    assert summary.table_exists
    # NOTE: Current implementation reports all rows as "to sync" since it doesn't
    # compare CSV data with existing database data. This is the upper bound -
    # actual upserts may not change data if values match.
    # A more sophisticated implementation would query and compare data.
    assert summary.rows_to_sync == 2
    assert summary.rows_to_delete == 0
    assert len(summary.new_columns) == 0
    assert len(summary.new_indexes) == 0


def test_dry_run_summary_new_columns(db_url: str, tmp_path: Path) -> None:
    """Test dry-run when new columns need to be added."""
    # Create initial CSV file with fewer columns
    csv_file1 = tmp_path / "test1.csv"
    with open(csv_file1, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "customer_name"])
        writer.writeheader()
        writer.writerow({"order_id": "1", "customer_name": "Alice"})

    job1 = CrumpJob(
        name="test_job",
        target_table="orders",
        id_mapping=[ColumnMapping("order_id", "id")],
        columns=[ColumnMapping("customer_name", "customer_name")],
    )

    with DatabaseConnection(db_url) as db:
        db.sync_tabular_file(csv_file1, job1)

    # Create new CSV with additional columns
    csv_file2 = tmp_path / "test2.csv"
    with open(csv_file2, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "customer_name", "total", "status"])
        writer.writeheader()
        writer.writerow(
            {"order_id": "2", "customer_name": "Bob", "total": "100", "status": "shipped"}
        )

    # New job with additional columns
    job2 = CrumpJob(
        name="test_job",
        target_table="orders",
        id_mapping=[ColumnMapping("order_id", "id")],
        columns=[
            ColumnMapping("customer_name", "customer_name"),
            ColumnMapping("total", "total_amount", "float"),
            ColumnMapping("status", "order_status"),
        ],
    )

    # Run dry-run
    summary = sync_file_to_db_dry_run(csv_file2, job2, db_url)

    # Verify summary
    assert summary.table_name == "orders"
    assert summary.table_exists
    assert summary.rows_to_sync == 1
    assert len(summary.new_columns) == 2

    # Check that new columns are identified
    new_column_names = [col[0] for col in summary.new_columns]
    assert "total_amount" in new_column_names
    assert "order_status" in new_column_names


def test_new_column_updates_all_rows(db_url: str, tmp_path: Path) -> None:
    """Test that when new columns are added, all existing rows are updated.

    This test verifies that schema evolution (adding new columns) causes
    all existing rows to be re-synced, not just new rows.
    """
    # Create initial CSV and sync it
    csv_file1 = tmp_path / "data_v1.csv"
    with open(csv_file1, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "name"])
        writer.writeheader()
        writer.writerow({"user_id": "1", "name": "Alice"})
        writer.writerow({"user_id": "2", "name": "Bob"})
        writer.writerow({"user_id": "3", "name": "Charlie"})

    job_v1 = CrumpJob(
        name="test_job",
        target_table="users",
        id_mapping=[ColumnMapping("user_id", "id")],
        columns=[ColumnMapping("name", "name")],
    )

    with DatabaseConnection(db_url) as db:
        rows_v1 = db.sync_tabular_file(csv_file1, job_v1)
    assert rows_v1 == 3

    # Create new CSV with additional column and same data plus one new row
    csv_file2 = tmp_path / "data_v2.csv"
    with open(csv_file2, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "name", "email"])
        writer.writeheader()
        writer.writerow({"user_id": "1", "name": "Alice", "email": "alice@example.com"})
        writer.writerow({"user_id": "2", "name": "Bob", "email": "bob@example.com"})
        writer.writerow({"user_id": "3", "name": "Charlie", "email": "charlie@example.com"})
        writer.writerow({"user_id": "4", "name": "Diana", "email": "diana@example.com"})

    job_v2 = CrumpJob(
        name="test_job",
        target_table="users",
        id_mapping=[ColumnMapping("user_id", "id")],
        columns=[
            ColumnMapping("name", "name"),
            ColumnMapping("email", "email"),  # New column
        ],
    )

    # Run dry-run first
    summary = sync_file_to_db_dry_run(csv_file2, job_v2, db_url)

    # Verify dry-run detected the new column
    assert summary.table_exists
    assert len(summary.new_columns) == 1
    assert summary.new_columns[0][0] == "email"
    # All 4 rows will be synced (3 existing + 1 new)
    assert summary.rows_to_sync == 4

    # Now perform actual sync
    with DatabaseConnection(db_url) as db:
        rows_v2 = db.sync_tabular_file(csv_file2, job_v2)

    # All 4 rows are synced (UPSERT operates on all rows)
    assert rows_v2 == 4

    # Verify dry-run prediction matched actual sync
    assert summary.rows_to_sync == rows_v2

    # Verify the email column was added and all rows have email values
    from .db_test_utils import execute_query

    rows = execute_query(db_url, "SELECT id, name, email FROM users ORDER BY id")
    assert len(rows) == 4
    assert rows[0] == ("1", "Alice", "alice@example.com")
    assert rows[1] == ("2", "Bob", "bob@example.com")
    assert rows[2] == ("3", "Charlie", "charlie@example.com")
    assert rows[3] == ("4", "Diana", "diana@example.com")


def test_dry_run_summary_new_indexes(db_url: str, tmp_path: Path) -> None:
    """Test dry-run when new indexes need to be created."""
    # Create a CSV file
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "email"])
        writer.writeheader()
        writer.writerow({"user_id": "1", "email": "alice@example.com"})

    job_no_indexes = CrumpJob(
        name="test_job",
        target_table="users",
        id_mapping=[ColumnMapping("user_id", "id")],
        columns=[ColumnMapping("email", "email")],
    )

    with DatabaseConnection(db_url) as db:
        db.sync_tabular_file(csv_file, job_no_indexes)

    # Create job with indexes
    job_with_indexes = CrumpJob(
        name="test_job",
        target_table="users",
        id_mapping=[ColumnMapping("user_id", "id")],
        columns=[ColumnMapping("email", "email")],
        indexes=[
            Index("idx_email", [IndexColumn("email", "ASC")]),
        ],
    )

    # Run dry-run
    summary = sync_file_to_db_dry_run(csv_file, job_with_indexes, db_url)

    # Verify summary
    assert summary.table_name == "users"
    assert summary.table_exists
    assert len(summary.new_indexes) == 1
    assert "idx_email" in summary.new_indexes


def test_dry_run_with_date_mapping_and_stale_records(db_url: str, tmp_path: Path) -> None:
    """Test dry-run with date mapping and stale record detection."""
    # Create initial CSV with date in filename
    csv_file1 = tmp_path / "sales_2024-01-15.csv"
    with open(csv_file1, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sale_id", "amount"])
        writer.writeheader()
        writer.writerow({"sale_id": "1", "amount": "100"})
        writer.writerow({"sale_id": "2", "amount": "200"})
        writer.writerow({"sale_id": "3", "amount": "300"})

    job = CrumpJob(
        name="sales_job",
        target_table="sales",
        id_mapping=[ColumnMapping("sale_id", "id")],
        columns=[ColumnMapping("amount", "amount")],
        filename_to_column=FilenameToColumn(
            regex=r"sales_(?P<date>[0-9-]+).*\.csv",
            columns={
                "date": FilenameColumnMapping(
                    name="date",
                    db_column="sync_date",
                    data_type="date",
                    use_to_delete_old_rows=True,
                )
            },
        ),
    )

    with DatabaseConnection(db_url) as db:
        filename_values = job.filename_to_column.extract_values_from_filename(csv_file1)
        db.sync_tabular_file(csv_file1, job, filename_values)

    # Create new CSV with fewer records (simulating deletions)
    csv_file2 = tmp_path / "sales_2024-01-15_v2.csv"
    with open(csv_file2, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sale_id", "amount"])
        writer.writeheader()
        writer.writerow({"sale_id": "1", "amount": "150"})  # Updated
        writer.writerow({"sale_id": "2", "amount": "200"})  # Same
        # sale_id 3 is missing - should be detected as stale

    # Run dry-run
    filename_values2 = job.filename_to_column.extract_values_from_filename(csv_file2)
    summary = sync_file_to_db_dry_run(csv_file2, job, db_url, filename_values2)

    # Verify summary
    assert summary.table_name == "sales"
    assert summary.table_exists
    assert summary.rows_to_sync == 2
    assert summary.rows_to_delete == 1  # sale_id 3 would be deleted


def test_dry_run_with_compound_primary_key(db_url: str, tmp_path: Path) -> None:
    """Test dry-run with compound primary key."""
    # Create a CSV file
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["store_id", "product_id", "quantity"])
        writer.writeheader()
        writer.writerow({"store_id": "1", "product_id": "A", "quantity": "10"})
        writer.writerow({"store_id": "1", "product_id": "B", "quantity": "20"})
        writer.writerow({"store_id": "2", "product_id": "A", "quantity": "15"})

    # Create a sync job with compound primary key
    job = CrumpJob(
        name="inventory_job",
        target_table="inventory",
        id_mapping=[
            ColumnMapping("store_id", "store_id"),
            ColumnMapping("product_id", "product_id"),
        ],
        columns=[ColumnMapping("quantity", "qty")],
    )

    # Run dry-run
    summary = sync_file_to_db_dry_run(csv_file, job, db_url)

    # Verify summary
    assert summary.table_name == "inventory"
    assert not summary.table_exists
    assert summary.rows_to_sync == 3
    assert summary.rows_to_delete == 0


def test_dry_run_compound_key_with_date_mapping_matches_sync(db_url: str, tmp_path: Path) -> None:
    """Test that dry-run with compound keys and date mapping returns same counts as actual sync.

    This test verifies that the dry-run accurately predicts the number of rows that will be
    added and deleted when using compound primary keys with date-based sync.
    """
    # Create initial CSV with varied data using compound keys and date in filename
    csv_file1 = tmp_path / "inventory_2024-01-15.csv"
    with open(csv_file1, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["store_id", "product_id", "category", "quantity", "price"]
        )
        writer.writeheader()
        # Multiple stores with multiple products
        writer.writerow(
            {
                "store_id": "1",
                "product_id": "A001",
                "category": "Electronics",
                "quantity": "50",
                "price": "299.99",
            }
        )
        writer.writerow(
            {
                "store_id": "1",
                "product_id": "B002",
                "category": "Furniture",
                "quantity": "25",
                "price": "149.99",
            }
        )
        writer.writerow(
            {
                "store_id": "1",
                "product_id": "C003",
                "category": "Books",
                "quantity": "100",
                "price": "19.99",
            }
        )
        writer.writerow(
            {
                "store_id": "2",
                "product_id": "A001",
                "category": "Electronics",
                "quantity": "30",
                "price": "299.99",
            }
        )
        writer.writerow(
            {
                "store_id": "2",
                "product_id": "D004",
                "category": "Clothing",
                "quantity": "75",
                "price": "49.99",
            }
        )
        writer.writerow(
            {
                "store_id": "3",
                "product_id": "B002",
                "category": "Furniture",
                "quantity": "15",
                "price": "149.99",
            }
        )
        writer.writerow(
            {
                "store_id": "3",
                "product_id": "E005",
                "category": "Sports",
                "quantity": "40",
                "price": "89.99",
            }
        )

    # Create a sync job with compound primary key and filename to column mapping
    job = CrumpJob(
        name="inventory_job",
        target_table="inventory",
        id_mapping=[
            ColumnMapping("store_id", "store_id"),
            ColumnMapping("product_id", "product_id"),
        ],
        columns=[
            ColumnMapping("category", "category"),
            ColumnMapping("quantity", "quantity", "int"),
            ColumnMapping("price", "price", "float"),
        ],
        filename_to_column=FilenameToColumn(
            columns={
                "date": FilenameColumnMapping(
                    name="date",
                    db_column="sync_date",
                    data_type="date",
                    use_to_delete_old_rows=True,
                )
            },
            regex=r"inventory_(?P<date>[0-9-]+).*\.csv",
        ),
    )

    # Extract date from filename
    filename_values = job.filename_to_column.extract_values_from_filename(csv_file1)

    # Run dry-run BEFORE actual sync
    dry_run_summary_initial = sync_file_to_db_dry_run(csv_file1, job, db_url, filename_values)

    # Perform actual sync and capture results
    with DatabaseConnection(db_url) as db:
        rows_synced_initial = db.sync_tabular_file(csv_file1, job, filename_values)

    # Verify dry-run predicted the correct number of rows for initial sync
    assert dry_run_summary_initial.rows_to_sync == rows_synced_initial
    assert dry_run_summary_initial.rows_to_sync == 7
    assert dry_run_summary_initial.rows_to_delete == 0  # No deletions on first sync

    # Create second CSV with updates and deletions (same date but different filename)
    # We need a different filename to avoid overwriting, but with same date pattern
    csv_file2 = tmp_path / "inventory_2024-01-15_v2.csv"
    with open(csv_file2, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["store_id", "product_id", "category", "quantity", "price"]
        )
        writer.writeheader()
        # Keep some, update some, remove some (store 3 products removed, store 1 C003 removed)
        writer.writerow(
            {
                "store_id": "1",
                "product_id": "A001",
                "category": "Electronics",
                "quantity": "45",
                "price": "299.99",
            }  # Updated quantity
        )
        writer.writerow(
            {
                "store_id": "1",
                "product_id": "B002",
                "category": "Furniture",
                "quantity": "30",
                "price": "139.99",
            }  # Updated quantity and price
        )
        # Store 1, product C003 removed
        writer.writerow(
            {
                "store_id": "2",
                "product_id": "A001",
                "category": "Electronics",
                "quantity": "30",
                "price": "299.99",
            }  # Unchanged
        )
        writer.writerow(
            {
                "store_id": "2",
                "product_id": "D004",
                "category": "Clothing",
                "quantity": "80",
                "price": "44.99",
            }  # Updated
        )
        # Store 3 products removed
        writer.writerow(
            {
                "store_id": "4",
                "product_id": "F006",
                "category": "Garden",
                "quantity": "20",
                "price": "59.99",
            }  # New store/product
        )

    # Extract date from second filename
    filename_values2 = job.filename_to_column.extract_values_from_filename(csv_file2)

    # Run dry-run BEFORE actual sync
    dry_run_summary_update = sync_file_to_db_dry_run(csv_file2, job, db_url, filename_values2)

    # Perform actual sync
    with DatabaseConnection(db_url) as db:
        rows_synced_update = db.sync_tabular_file(csv_file2, job, filename_values2)

    # Verify dry-run predicted correct counts for update
    assert dry_run_summary_update.rows_to_sync == rows_synced_update
    assert dry_run_summary_update.rows_to_sync == 5  # 4 updates + 1 new

    # With compound key fix, all stale records should be detected:
    # - Store 1, product C003 (removed)
    # - Store 3, product B002 (removed)
    # - Store 3, product E005 (removed)
    # Total: 3 deletions
    assert dry_run_summary_update.rows_to_delete == 3
