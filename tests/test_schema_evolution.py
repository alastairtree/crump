"""Tests for schema evolution — safe type widening."""

from pathlib import Path

from crump.config import ColumnMapping, CrumpJob
from crump.database import DatabaseConnection, sync_file_to_db
from tests.db_test_utils import execute_query, get_column_types
from tests.test_helpers import create_csv_file


class TestSchemaEvolution:
    """Test that crump detects config type changes and widens the schema.

    When a table already exists with a narrower type (e.g. integer) and the
    config is updated to a wider type (e.g. bigint), crump should issue an
    ALTER statement to widen the column before syncing the new data.
    """

    def test_integer_to_bigint_widening(self, tmp_path: Path, db_url: str) -> None:
        """Sync CSV with integer, then widen config to bigint and sync larger values."""
        table_name = "test_int_to_bigint"

        # --- Step 1: Sync initial CSV with integer column ---
        csv1 = create_csv_file(
            tmp_path / "data1.csv",
            ["id", "value"],
            [
                {"id": "1", "value": "100"},
                {"id": "2", "value": "200"},
            ],
        )
        job1 = CrumpJob(
            name="test",
            target_table=table_name,
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("value", "value", data_type="integer"),
            ],
        )
        rows1 = sync_file_to_db(csv1, job1, db_url)
        assert rows1 == 2

        # Verify initial data
        results1 = execute_query(db_url, f'SELECT id, value FROM "{table_name}" ORDER BY id')
        assert results1[0] == ("1", 100)
        assert results1[1] == ("2", 200)

        # Verify initial column type
        col_types = get_column_types(db_url, table_name)
        if db_url.startswith("postgres"):
            assert col_types["value"] == "integer"

        # --- Step 2: Widen config to bigint and sync larger values ---
        csv2 = create_csv_file(
            tmp_path / "data2.csv",
            ["id", "value"],
            [
                {"id": "3", "value": "3000000000"},  # exceeds 4-byte integer max
                {"id": "4", "value": "-3000000000"},  # below 4-byte integer min
            ],
        )
        job2 = CrumpJob(
            name="test",
            target_table=table_name,
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("value", "value", data_type="bigint"),
            ],
        )
        rows2 = sync_file_to_db(csv2, job2, db_url)
        assert rows2 == 2

        # Verify column type was widened (PostgreSQL only — SQLite uses dynamic typing)
        col_types_after = get_column_types(db_url, table_name)
        if db_url.startswith("postgres"):
            assert col_types_after["value"] == "bigint"

        # Verify ALL data is present (both original small values and new large values)
        results_all = execute_query(db_url, f'SELECT id, value FROM "{table_name}" ORDER BY id')
        assert len(results_all) == 4
        assert results_all[0] == ("1", 100)
        assert results_all[1] == ("2", 200)
        assert results_all[2] == ("3", 3000000000)
        assert results_all[3] == ("4", -3000000000)

    def test_varchar_widening(self, tmp_path: Path, db_url: str) -> None:
        """Sync CSV with varchar(4), then widen config to varchar(10) and sync longer values."""
        table_name = "test_varchar_widen"

        # --- Step 1: Sync initial CSV with varchar(4) column ---
        csv1 = create_csv_file(
            tmp_path / "data1.csv",
            ["id", "code"],
            [
                {"id": "1", "code": "ABCD"},
                {"id": "2", "code": "XY"},
            ],
        )
        job1 = CrumpJob(
            name="test",
            target_table=table_name,
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("code", "code", data_type="varchar(4)"),
            ],
        )
        rows1 = sync_file_to_db(csv1, job1, db_url)
        assert rows1 == 2

        # Verify initial data
        results1 = execute_query(db_url, f'SELECT id, code FROM "{table_name}" ORDER BY id')
        assert results1[0] == ("1", "ABCD")
        assert results1[1] == ("2", "XY")

        # Verify initial column type (PostgreSQL only)
        col_types = get_column_types(db_url, table_name)
        if db_url.startswith("postgres"):
            assert col_types["code"] == "varchar(4)"

        # --- Step 2: Widen config to varchar(10) and sync longer values ---
        csv2 = create_csv_file(
            tmp_path / "data2.csv",
            ["id", "code"],
            [
                {"id": "3", "code": "LONGSTRING"},  # 10 chars, exceeds varchar(4)
                {"id": "4", "code": "MEDIUM"},  # 6 chars, exceeds varchar(4)
            ],
        )
        job2 = CrumpJob(
            name="test",
            target_table=table_name,
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("code", "code", data_type="varchar(10)"),
            ],
        )
        rows2 = sync_file_to_db(csv2, job2, db_url)
        assert rows2 == 2

        # Verify column type was widened (PostgreSQL only)
        col_types_after = get_column_types(db_url, table_name)
        if db_url.startswith("postgres"):
            assert col_types_after["code"] == "varchar(10)"

        # Verify ALL data is present
        results_all = execute_query(db_url, f'SELECT id, code FROM "{table_name}" ORDER BY id')
        assert len(results_all) == 4
        assert results_all[0] == ("1", "ABCD")
        assert results_all[1] == ("2", "XY")
        assert results_all[2] == ("3", "LONGSTRING")
        assert results_all[3] == ("4", "MEDIUM")

    def test_is_safe_type_widening_unit(self) -> None:
        """Unit test for _is_safe_type_widening static method."""
        # Safe widenings
        assert DatabaseConnection._is_safe_type_widening("integer", "BIGINT") is True
        assert DatabaseConnection._is_safe_type_widening("integer", "BIGINT NOT NULL") is True
        assert DatabaseConnection._is_safe_type_widening("varchar(4)", "VARCHAR(10)") is True
        assert DatabaseConnection._is_safe_type_widening("varchar(4)", "VARCHAR(10) NULL") is True
        assert DatabaseConnection._is_safe_type_widening("varchar(5)", "varchar(100)") is True

        # Not widenings (same or narrower)
        assert DatabaseConnection._is_safe_type_widening("integer", "INTEGER") is False
        assert DatabaseConnection._is_safe_type_widening("bigint", "INTEGER") is False
        assert DatabaseConnection._is_safe_type_widening("varchar(10)", "VARCHAR(4)") is False
        assert DatabaseConnection._is_safe_type_widening("varchar(10)", "VARCHAR(10)") is False
        assert DatabaseConnection._is_safe_type_widening("text", "VARCHAR(10)") is False
        assert DatabaseConnection._is_safe_type_widening("integer", "TEXT") is False
