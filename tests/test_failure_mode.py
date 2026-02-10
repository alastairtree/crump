"""Tests for failure_mode handling of data/config mismatches."""

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

    def test_strict_skips_rows_with_missing_non_nullable(self, csv_file: Path, db_url: str) -> None:
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
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 0  # Both rows skipped

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

    def test_strict_rejects_row_with_any_issue(self, tmp_path: Path, db_url: str) -> None:
        """STRICT skips entire row if any non-nullable field is missing."""
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
        rows = sync_file_to_db(csv_file, job, db_url)
        assert rows == 0

    def test_normal_csv_unaffected_by_failure_mode(self, tmp_path: Path, db_url: str) -> None:
        """When CSV matches config perfectly, failure_mode doesn't change behavior."""
        csv_file = create_csv_file(
            tmp_path / "data.csv",
            ["id", "name", "score"],
            [
                {"id": "1", "name": "Alice", "score": "100"},
                {"id": "2", "name": "Bob", "score": "200"},
            ],
        )
        for mode in (FailureMode.STRICT, FailureMode.PERMISSIVE):
            job = CrumpJob(
                name="test",
                target_table=f"test_normal_{mode.value}",
                id_mapping=[ColumnMapping("id", "id")],
                columns=[
                    ColumnMapping("name", "name"),
                    ColumnMapping("score", "score", data_type="integer"),
                ],
                failure_mode=mode,
            )
            rows = sync_file_to_db(csv_file, job, db_url)
            assert rows == 2


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
        # Should succeed (exit 0) but sync 0 rows in strict mode
        assert result.exit_code == 0

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
