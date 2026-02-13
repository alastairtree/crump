"""Tests for failure_mode handling of data/config mismatches."""

import datetime
from pathlib import Path

import pytest

from crump.config import ColumnMapping, CrumpConfig, CrumpJob, FailureMode
from crump.database import sync_file_to_db
from tests.db_test_utils import execute_query
from tests.test_helpers import create_csv_file

# ---------------------------------------------------------------------------
# Config parsing tests (no database needed)
# ---------------------------------------------------------------------------


class TestFailureModeConfig:
    """Test failure_mode parsing from YAML configuration."""

    def test_default_failure_mode_is_permissive(self, tmp_path: Path) -> None:
        """When failure_mode is omitted, it should default to PERMISSIVE."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: t
    id_mapping:
      id: id
""")
        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.failure_mode == FailureMode.PERMISSIVE

    def test_parse_strict_failure_mode(self, tmp_path: Path) -> None:
        """Test that failure_mode: strict is parsed correctly."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: t
    id_mapping:
      id: id
    failure_mode: strict
""")
        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.failure_mode == FailureMode.STRICT

    def test_parse_permissive_failure_mode(self, tmp_path: Path) -> None:
        """Test that failure_mode: permissive is parsed correctly."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: t
    id_mapping:
      id: id
    failure_mode: permissive
""")
        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.failure_mode == FailureMode.PERMISSIVE

    def test_parse_failure_mode_case_insensitive(self, tmp_path: Path) -> None:
        """Test that failure_mode parsing is case-insensitive."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: t
    id_mapping:
      id: id
    failure_mode: STRICT
""")
        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.failure_mode == FailureMode.STRICT

    def test_invalid_failure_mode_raises(self, tmp_path: Path) -> None:
        """Test that an invalid failure_mode value raises ValueError."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: t
    id_mapping:
      id: id
    failure_mode: invalid
""")
        with pytest.raises(ValueError, match="failure_mode must be 'strict' or 'permissive'"):
            CrumpConfig.from_yaml(config_file)

    def test_failure_mode_serialized_to_yaml(self) -> None:
        """Test that non-default failure_mode is serialized to YAML dict."""
        job = CrumpJob(
            name="test",
            target_table="t",
            id_mapping=[ColumnMapping("id", "id")],
            failure_mode=FailureMode.STRICT,
        )
        config = CrumpConfig(jobs={"test": job})
        yaml_dict = config.to_yaml_dict()
        assert yaml_dict["jobs"]["test"]["failure_mode"] == "strict"

    def test_default_failure_mode_not_serialized(self) -> None:
        """Test that default (PERMISSIVE) failure_mode is not serialized."""
        job = CrumpJob(
            name="test",
            target_table="t",
            id_mapping=[ColumnMapping("id", "id")],
        )
        config = CrumpConfig(jobs={"test": job})
        yaml_dict = config.to_yaml_dict()
        assert "failure_mode" not in yaml_dict["jobs"]["test"]


# ---------------------------------------------------------------------------
# Database sync tests — missing nullable field (runs against both backends)
# ---------------------------------------------------------------------------


class TestMissingNullableField:
    """CSV is missing a nullable field defined in config.

    Both STRICT and PERMISSIVE should insert NULL for the missing field.
    """

    @pytest.fixture()
    def csv_file(self, tmp_path: Path) -> Path:
        """CSV with id and name but missing the 'description' column."""
        return create_csv_file(
            tmp_path / "data.csv",
            ["id", "name"],
            [
                {"id": "1", "name": "Alice"},
                {"id": "2", "name": "Bob"},
            ],
        )

    def test_strict_inserts_null_for_missing_nullable(
        self, csv_file: Path, tmp_path: Path, db_url: str
    ) -> None:
        job = CrumpJob(
            name="test",
            target_table="test_missing_nullable_strict",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("name", "name"),
                ColumnMapping("description", "description", data_type="text", nullable=True),
            ],
            failure_mode=FailureMode.STRICT,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 2
        results = execute_query(
            db_url,
            'SELECT id, name, description FROM "test_missing_nullable_strict" ORDER BY id',
        )
        assert results[0] == ("1", "Alice", None)
        assert results[1] == ("2", "Bob", None)

    def test_permissive_inserts_null_for_missing_nullable(
        self, csv_file: Path, tmp_path: Path, db_url: str
    ) -> None:
        job = CrumpJob(
            name="test",
            target_table="test_missing_nullable_permissive",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("name", "name"),
                ColumnMapping("description", "description", data_type="text", nullable=True),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 2
        results = execute_query(
            db_url,
            'SELECT id, name, description FROM "test_missing_nullable_permissive" ORDER BY id',
        )
        assert results[0] == ("1", "Alice", None)
        assert results[1] == ("2", "Bob", None)


# ---------------------------------------------------------------------------
# Database sync tests — missing non-nullable field (runs against both backends)
# ---------------------------------------------------------------------------


class TestMissingNonNullableField:
    """CSV is missing a non-nullable field defined in config.

    STRICT should skip the row.
    PERMISSIVE should use default values (0 for integers, "" for strings).
    """

    @pytest.fixture()
    def csv_file(self, tmp_path: Path) -> Path:
        """CSV with id and name but missing 'score' and 'label' columns."""
        return create_csv_file(
            tmp_path / "data.csv",
            ["id", "name"],
            [
                {"id": "1", "name": "Alice"},
                {"id": "2", "name": "Bob"},
            ],
        )

    def test_strict_errors_when_all_rows_rejected(self, csv_file: Path, db_url: str) -> None:
        """STRICT raises ValueError when all rows are rejected."""
        job = CrumpJob(
            name="test",
            target_table="test_strict_skip",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("name", "name"),
                ColumnMapping("score", "score", data_type="integer", nullable=False),
            ],
            failure_mode=FailureMode.STRICT,
        )
        with pytest.raises(ValueError, match="All 2 row.*rejected"):
            sync_file_to_db(csv_file, job, db_url)

    def test_permissive_uses_zero_for_missing_integer(self, csv_file: Path, db_url: str) -> None:
        job = CrumpJob(
            name="test",
            target_table="test_permissive_int",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("name", "name"),
                ColumnMapping("score", "score", data_type="integer", nullable=False),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 2
        results = execute_query(
            db_url, 'SELECT id, name, score FROM "test_permissive_int" ORDER BY id'
        )
        assert results[0] == ("1", "Alice", 0)
        assert results[1] == ("2", "Bob", 0)

    def test_permissive_uses_empty_string_for_missing_text(
        self, csv_file: Path, db_url: str
    ) -> None:
        job = CrumpJob(
            name="test",
            target_table="test_permissive_text",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("name", "name"),
                ColumnMapping("label", "label", data_type="text", nullable=False),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 2
        results = execute_query(
            db_url, 'SELECT id, name, label FROM "test_permissive_text" ORDER BY id'
        )
        assert results[0] == ("1", "Alice", "")
        assert results[1] == ("2", "Bob", "")


# ---------------------------------------------------------------------------
# Database sync tests — varchar limit exceeded (runs against both backends)
# ---------------------------------------------------------------------------


class TestVarcharLimitExceeded:
    """CSV contains a string longer than a varchar limit.

    STRICT should reject the row.
    PERMISSIVE should truncate the value.
    """

    @pytest.fixture()
    def csv_file(self, tmp_path: Path) -> Path:
        return create_csv_file(
            tmp_path / "data.csv",
            ["id", "code"],
            [
                {"id": "1", "code": "AB"},  # fits varchar(5)
                {"id": "2", "code": "TOOLONGVALUE"},  # exceeds varchar(5)
                {"id": "3", "code": "XY"},  # fits
            ],
        )

    def test_strict_rejects_row_exceeding_varchar(self, csv_file: Path, db_url: str) -> None:
        job = CrumpJob(
            name="test",
            target_table="test_varchar_strict",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("code", "code", data_type="varchar(5)"),
            ],
            failure_mode=FailureMode.STRICT,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 2  # row 2 skipped
        results = execute_query(db_url, 'SELECT id, code FROM "test_varchar_strict" ORDER BY id')
        assert len(results) == 2
        assert results[0] == ("1", "AB")
        assert results[1] == ("3", "XY")

    def test_permissive_truncates_varchar(self, csv_file: Path, db_url: str) -> None:
        job = CrumpJob(
            name="test",
            target_table="test_varchar_permissive",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("code", "code", data_type="varchar(5)"),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 3  # all rows imported
        results = execute_query(
            db_url, 'SELECT id, code FROM "test_varchar_permissive" ORDER BY id'
        )
        assert len(results) == 3
        assert results[0] == ("1", "AB")
        assert results[1] == ("2", "TOOLO")  # truncated to 5 chars
        assert results[2] == ("3", "XY")


# ---------------------------------------------------------------------------
# Database sync tests — combined scenarios (runs against both backends)
# ---------------------------------------------------------------------------


class TestFailureModeCombinedScenarios:
    """Test combined mismatch scenarios."""

    def test_permissive_handles_multiple_issues_in_one_row(
        self, tmp_path: Path, db_url: str
    ) -> None:
        """PERMISSIVE handles missing nullable, missing non-nullable, and varchar overflow."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "long_name"],
            [
                {"id": "1", "long_name": "A very long name that exceeds limit"},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_combined_permissive",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("long_name", "short_name", data_type="varchar(10)"),
                ColumnMapping("optional", "optional", data_type="text", nullable=True),
                ColumnMapping("required_int", "required_int", data_type="integer", nullable=False),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 1
        results = execute_query(
            db_url,
            'SELECT id, short_name, optional, required_int FROM "test_combined_permissive"',
        )
        assert len(results) == 1
        assert results[0][0] == "1"
        assert results[0][1] == "A very lon"  # truncated to 10
        assert results[0][2] is None  # nullable → NULL
        assert results[0][3] == 0  # non-nullable integer → 0

    def test_strict_errors_when_all_rows_rejected(self, tmp_path: Path, db_url: str) -> None:
        """STRICT raises ValueError if all rows are rejected."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "name"],
            [
                {"id": "1", "name": "Alice"},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_strict_reject",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("name", "name"),
                ColumnMapping("required_col", "required_col", data_type="text", nullable=False),
            ],
            failure_mode=FailureMode.STRICT,
        )
        with pytest.raises(ValueError, match="All 1 row.*rejected"):
            sync_file_to_db(csv_file, job, db_url)

    def test_strict_partial_rejection_does_not_error(self, tmp_path: Path, db_url: str) -> None:
        """STRICT does NOT error when only some rows are rejected (partial success)."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "code"],
            [
                {"id": "1", "code": "OK"},
                {"id": "2", "code": "TOOLONGVALUE"},  # exceeds varchar(5)
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_strict_partial",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("code", "code", data_type="varchar(5)"),
            ],
            failure_mode=FailureMode.STRICT,
        )
        # Should succeed with 1 row synced (not raise)
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 1
        results = execute_query(db_url, 'SELECT id, code FROM "test_strict_partial" ORDER BY id')
        assert len(results) == 1
        assert results[0] == ("1", "OK")


# ---------------------------------------------------------------------------
# CLI integration tests (SQLite only — no need for dual backend)
# ---------------------------------------------------------------------------


class TestFailureModeCLI:
    """Test failure_mode through the CLI interface."""

    def test_sync_with_strict_mode_via_config(self, cli_runner, tmp_path: Path) -> None:
        """Test that strict mode works via config file through CLI."""
        from crump.cli import main

        csv_file = tmp_path / "data.csv"
        create_csv_file(
            csv_file,
            ["id", "name"],
            [
                {"id": "1", "name": "Alice"},
            ],
        )

        config_file = tmp_path / "config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      id: id
    columns:
      name: name
      missing_col:
        db_column: missing_col
        type: text
        nullable: false
    failure_mode: strict
""")

        db_file = tmp_path / "test.db"
        db_url = f"sqlite:///{db_file}"

        result = cli_runner.invoke(
            main,
            [
                "sync",
                str(csv_file),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "--db-url",
                db_url,
            ],
        )
        # All rows rejected in strict mode → non-zero exit code
        assert result.exit_code != 0

    def test_sync_with_permissive_mode_via_config(self, cli_runner, tmp_path: Path) -> None:
        """Test that permissive mode works via config file through CLI."""
        from crump.cli import main

        csv_file = tmp_path / "data.csv"
        create_csv_file(
            csv_file,
            ["id", "name"],
            [
                {"id": "1", "name": "Alice"},
            ],
        )

        config_file = tmp_path / "config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      id: id
    columns:
      name: name
      missing_col:
        db_column: missing_col
        type: integer
        nullable: false
    failure_mode: permissive
""")

        db_file = tmp_path / "test.db"
        db_url = f"sqlite:///{db_file}"

        result = cli_runner.invoke(
            main,
            [
                "sync",
                str(csv_file),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "--db-url",
                db_url,
            ],
        )
        assert result.exit_code == 0

        # Verify the row was inserted with default value
        results = execute_query(db_url, "SELECT id, name, missing_col FROM test_table")
        assert len(results) == 1
        assert results[0] == ("1", "Alice", 0)


# ---------------------------------------------------------------------------
# Integer out-of-range tests (runs against both backends)
# ---------------------------------------------------------------------------


class TestIntegerOutOfRange:
    """CSV contains integer values outside the valid range for the column type.

    STRICT should skip the row.
    PERMISSIVE should use NULL if nullable, or skip if non-nullable.
    """

    @pytest.fixture()
    def csv_file_overflow(self, tmp_path: Path) -> Path:
        """CSV with integer values that overflow a standard 4-byte integer."""
        return create_csv_file(
            tmp_path / "data.csv",
            ["id", "value"],
            [
                {"id": "1", "value": "100"},  # in range
                {"id": "2", "value": "3000000000"},  # exceeds integer max (2147483647)
                {"id": "3", "value": "-3000000000"},  # below integer min (-2147483648)
                {"id": "4", "value": "42"},  # in range
            ],
        )

    def test_strict_skips_out_of_range_integer(self, csv_file_overflow: Path, db_url: str) -> None:
        """STRICT skips rows with out-of-range integers."""
        job = CrumpJob(
            name="test",
            target_table="test_int_strict",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("value", "value", data_type="integer"),
            ],
            failure_mode=FailureMode.STRICT,
        )
        rows = sync_file_to_db(csv_file_overflow, job, db_url)
        assert rows == 2  # rows 2 and 3 skipped
        results = execute_query(db_url, 'SELECT id, value FROM "test_int_strict" ORDER BY id')
        assert len(results) == 2
        assert results[0][0] == "1"
        assert results[1][0] == "4"

    def test_permissive_nulls_out_of_range_integer_nullable(
        self, csv_file_overflow: Path, db_url: str
    ) -> None:
        """PERMISSIVE sets out-of-range integer to NULL when column is nullable."""
        job = CrumpJob(
            name="test",
            target_table="test_int_permissive_nullable",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("value", "value", data_type="integer", nullable=True),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file_overflow, job, db_url)
        assert rows == 4  # all rows imported
        results = execute_query(
            db_url,
            'SELECT id, value FROM "test_int_permissive_nullable" ORDER BY id',
        )
        assert len(results) == 4
        assert results[0] == ("1", 100)
        assert results[1] == ("2", None)  # out of range → NULL
        assert results[2] == ("3", None)  # out of range → NULL
        assert results[3] == ("4", 42)

    def test_permissive_skips_out_of_range_integer_not_nullable(
        self, csv_file_overflow: Path, db_url: str
    ) -> None:
        """PERMISSIVE skips rows with out-of-range integers when column is NOT nullable."""
        job = CrumpJob(
            name="test",
            target_table="test_int_permissive_notnull",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("value", "value", data_type="integer", nullable=False),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file_overflow, job, db_url)
        assert rows == 2  # rows 2 and 3 skipped (can't null, can't fit)
        results = execute_query(
            db_url,
            'SELECT id, value FROM "test_int_permissive_notnull" ORDER BY id',
        )
        assert len(results) == 2
        assert results[0][0] == "1"
        assert results[1][0] == "4"

    def test_bigint_allows_larger_values(self, tmp_path: Path, db_url: str) -> None:
        """Values that overflow integer should fit in bigint."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "big_value"],
            [
                {"id": "1", "big_value": "3000000000"},  # exceeds int, fits bigint
                {"id": "2", "big_value": "-3000000000"},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_bigint",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("big_value", "big_value", data_type="bigint"),
            ],
            failure_mode=FailureMode.STRICT,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 2  # both fit in bigint

    def test_strict_all_out_of_range_raises(self, tmp_path: Path, db_url: str) -> None:
        """STRICT raises ValueError when ALL rows have out-of-range integers."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "value"],
            [
                {"id": "1", "value": "9999999999"},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_int_all_bad",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("value", "value", data_type="integer"),
            ],
            failure_mode=FailureMode.STRICT,
        )
        with pytest.raises(ValueError, match="All 1 row.*rejected"):
            sync_file_to_db(csv_file, job, db_url)


# ---------------------------------------------------------------------------
# Datetime empty/null handling tests (runs against both backends)
# ---------------------------------------------------------------------------


class TestDatetimeEmptyHandling:
    """CSV contains empty or null datetime values.

    Both modes: nullable datetime → NULL.
    STRICT: non-nullable empty datetime → skip row.
    PERMISSIVE: non-nullable empty datetime → minimum datetime.
    """

    def test_nullable_datetime_empty_becomes_null(self, tmp_path: Path, db_url: str) -> None:
        """Empty datetime in a nullable column becomes NULL in both modes."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "event_date"],
            [
                {"id": "1", "event_date": ""},
                {"id": "2", "event_date": "2024-01-15"},
            ],
        )
        for mode in (FailureMode.STRICT, FailureMode.PERMISSIVE):
            job = CrumpJob(
                name="test",
                target_table=f"test_dt_null_{mode.value}",
                id_mapping=[ColumnMapping("id", "id")],
                columns=[
                    ColumnMapping("event_date", "event_date", data_type="date", nullable=True),
                ],
                failure_mode=mode,
            )
            rows = sync_file_to_db(csv_file, job, db_url)
            assert rows == 2
            results = execute_query(
                db_url,
                f'SELECT id, event_date FROM "test_dt_null_{mode.value}" ORDER BY id',
            )
            assert results[0][0] == "1"
            assert results[0][1] is None  # empty → NULL
            assert results[1][0] == "2"

    def test_strict_skips_empty_non_nullable_datetime(self, tmp_path: Path, db_url: str) -> None:
        """STRICT skips rows with empty datetime when column is NOT nullable."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "event_date"],
            [
                {"id": "1", "event_date": ""},
                {"id": "2", "event_date": "2024-01-15"},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_dt_strict_notnull",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("event_date", "event_date", data_type="date", nullable=False),
            ],
            failure_mode=FailureMode.STRICT,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 1  # row 1 skipped
        results = execute_query(
            db_url,
            'SELECT id FROM "test_dt_strict_notnull" ORDER BY id',
        )
        assert len(results) == 1
        assert results[0][0] == "2"

    def test_permissive_uses_min_datetime_for_empty_non_nullable(
        self, tmp_path: Path, db_url: str
    ) -> None:
        """PERMISSIVE uses minimum datetime for empty non-nullable datetime column."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "event_date"],
            [
                {"id": "1", "event_date": ""},
                {"id": "2", "event_date": "2024-01-15"},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_dt_permissive_notnull",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("event_date", "event_date", data_type="date", nullable=False),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 2  # all rows imported
        results = execute_query(
            db_url,
            'SELECT id, event_date FROM "test_dt_permissive_notnull" ORDER BY id',
        )
        assert results[0][0] == "1"
        # Check that the first row got the minimum date
        min_date = results[0][1]
        assert min_date is not None
        # SQLite stores dates as strings, so check for the min date string
        if isinstance(min_date, str):
            assert min_date in ("0001-01-01", "1-01-01", "1-1-1")
        else:
            assert min_date == datetime.date(1, 1, 1)

    def test_datetime_type_empty_becomes_null(self, tmp_path: Path, db_url: str) -> None:
        """Empty datetime type (not just date) in nullable column becomes NULL."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "ts"],
            [
                {"id": "1", "ts": ""},
                {"id": "2", "ts": "   "},  # whitespace-only
                {"id": "3", "ts": "2024-01-15 10:30:00"},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_datetime_empty",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("ts", "ts", data_type="datetime", nullable=True),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 3
        results = execute_query(db_url, 'SELECT id, ts FROM "test_datetime_empty" ORDER BY id')
        assert results[0][1] is None  # empty → NULL
        assert results[1][1] is None  # whitespace → NULL

    def test_timestamp_type_handled_same_as_datetime(self, tmp_path: Path, db_url: str) -> None:
        """Timestamp type is treated the same as datetime."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "created_at"],
            [
                {"id": "1", "created_at": ""},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_timestamp",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("created_at", "created_at", data_type="timestamp", nullable=True),
            ],
            failure_mode=FailureMode.STRICT,
        )
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 1
        results = execute_query(db_url, 'SELECT created_at FROM "test_timestamp"')
        assert results[0][0] is None

    def test_strict_all_empty_datetime_non_nullable_raises(
        self, tmp_path: Path, db_url: str
    ) -> None:
        """STRICT raises ValueError when ALL rows have empty non-nullable datetime."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "event_date"],
            [
                {"id": "1", "event_date": ""},
                {"id": "2", "event_date": ""},
            ],
        )
        job = CrumpJob(
            name="test",
            target_table="test_dt_all_empty",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("event_date", "event_date", data_type="date", nullable=False),
            ],
            failure_mode=FailureMode.STRICT,
        )
        with pytest.raises(ValueError, match="All 2 row.*rejected"):
            sync_file_to_db(csv_file, job, db_url)


# ---------------------------------------------------------------------------
# Grouped warning summary tests
# ---------------------------------------------------------------------------


class TestValidationWarningSummary:
    """Test that validation warnings are grouped into summary messages.

    When many rows trigger the same kind of warning, the log should contain
    one summary message per category rather than one per row.
    """

    def test_log_validation_summary_unit(self) -> None:
        """Unit test for _log_validation_summary emitting grouped messages."""
        import logging
        import logging.handlers

        from crump.database import DatabaseConnection

        db_logger = logging.getLogger("crump.database")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.WARNING)
        db_logger.addHandler(handler)

        try:
            warning_counts = {
                "skip:varchar_exceeded:name:50": 42,
                "fix:varchar_truncated:code:4": 100,
                "skip:int_out_of_range:value:integer": 7,
            }
            DatabaseConnection._log_validation_summary(warning_counts)
            handler.flush()

            messages = [record.getMessage() for record in handler.buffer]
            assert len(messages) == 3

            # Check each summary message contains the count and is grouped
            varchar_skip = [m for m in messages if "varchar(50)" in m and "Skipped" in m]
            assert len(varchar_skip) == 1
            assert "42 rows" in varchar_skip[0]

            varchar_trunc = [m for m in messages if "varchar(4)" in m and "Truncated" in m]
            assert len(varchar_trunc) == 1
            assert "100 rows" in varchar_trunc[0]

            int_skip = [m for m in messages if "integer" in m and "Skipped" in m]
            assert len(int_skip) == 1
            assert "7 rows" in int_skip[0]
        finally:
            db_logger.removeHandler(handler)

    def test_singular_row_word_for_count_one(self) -> None:
        """When count is 1, summary should say 'row' not 'rows'."""
        import logging
        import logging.handlers

        from crump.database import DatabaseConnection

        db_logger = logging.getLogger("crump.database")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.WARNING)
        db_logger.addHandler(handler)

        try:
            DatabaseConnection._log_validation_summary({"skip:varchar_exceeded:name:50": 1})
            handler.flush()
            msg = handler.buffer[0].getMessage()
            assert "1 row" in msg
            assert "1 rows" not in msg
        finally:
            db_logger.removeHandler(handler)

    def test_many_rows_truncated_produces_one_summary(self, tmp_path: Path, db_url: str) -> None:
        """Syncing many rows that exceed varchar limit produces grouped summary."""
        import logging
        import logging.handlers

        # Create CSV with 50 rows that all exceed varchar(4) limit
        rows = [{"id": str(i), "code": "TOOLONGVALUE"} for i in range(50)]
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "code"],
            rows,
        )
        job = CrumpJob(
            name="test",
            target_table="test_grouped_warn",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("code", "code", data_type="varchar(4)"),
            ],
            failure_mode=FailureMode.PERMISSIVE,
        )

        db_logger = logging.getLogger("crump.database")
        handler = logging.handlers.MemoryHandler(capacity=200)
        handler.setLevel(logging.WARNING)
        db_logger.addHandler(handler)

        try:
            rows_synced = sync_file_to_db(csv_file, job, db_url)
            handler.flush()

            assert rows_synced == 50

            messages = [record.getMessage() for record in handler.buffer]

            # Should have exactly 1 truncation summary, NOT 50 per-row messages
            trunc_msgs = [m for m in messages if "Truncated" in m]
            assert len(trunc_msgs) == 1
            assert "50 rows" in trunc_msgs[0]
            assert "varchar(4)" in trunc_msgs[0]
        finally:
            db_logger.removeHandler(handler)

    def test_many_rows_skipped_strict_produces_one_summary(
        self, tmp_path: Path, db_url: str
    ) -> None:
        """STRICT mode skipping many rows produces grouped summary before raising."""
        import logging
        import logging.handlers

        rows = [{"id": str(i), "code": "TOOLONG"} for i in range(20)]
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "code"],
            rows,
        )
        job = CrumpJob(
            name="test",
            target_table="test_grouped_strict",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping("code", "code", data_type="varchar(4)"),
            ],
            failure_mode=FailureMode.STRICT,
        )

        db_logger = logging.getLogger("crump.database")
        handler = logging.handlers.MemoryHandler(capacity=200)
        handler.setLevel(logging.WARNING)
        db_logger.addHandler(handler)

        try:
            with pytest.raises(ValueError, match="All 20 row.*rejected"):
                sync_file_to_db(csv_file, job, db_url)
            handler.flush()

            messages = [record.getMessage() for record in handler.buffer]

            # Should have 1 grouped skip summary + 1 "Skipped N rows" summary
            skip_msgs = [m for m in messages if "Skipped 20 rows" in m]
            assert len(skip_msgs) >= 1
            assert "varchar(4)" in skip_msgs[0]
        finally:
            db_logger.removeHandler(handler)

    def test_empty_warning_counts_produces_no_log(self) -> None:
        """Empty warning_counts dict should not produce any log messages."""
        import logging
        import logging.handlers

        from crump.database import DatabaseConnection

        db_logger = logging.getLogger("crump.database")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.WARNING)
        db_logger.addHandler(handler)

        try:
            DatabaseConnection._log_validation_summary({})
            handler.flush()
            assert len(handler.buffer) == 0
        finally:
            db_logger.removeHandler(handler)
