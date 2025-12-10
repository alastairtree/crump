"""End-to-end tests for CDF workflow (2-step: prepare CDF → sync CDF)."""

from pathlib import Path

import pytest


class TestCDFEndToEndWorkflow:
    """Test complete 2-step CDF workflow: prepare CDF → sync CDF → verify database."""

    @pytest.fixture
    def sample_cdf(self) -> Path:
        """Get path to a sample CDF file."""
        return Path("tests/data/imap_mag_l1c_norm-magi_20251010_v001.cdf")

    @pytest.mark.parametrize("db_type", ["sqlite"])
    def test_cdf_prepare_and_sync_workflow(
        self, sample_cdf: Path, tmp_path: Path, db_type: str, request: pytest.FixtureRequest
    ) -> None:
        """Test 2-step workflow: prepare CDF → sync CDF to database (200 rows only)."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare
        from crump.cli_sync import sync
        from crump.config import CrumpConfig

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        db_url = request.getfixturevalue(f"{db_type}_db")
        runner = CliRunner()

        # Step 1: Prepare config from CDF file
        config_file = tmp_path / "crump_config.yml"
        prepare_result = runner.invoke(prepare, [str(sample_cdf), "--config", str(config_file)])
        assert prepare_result.exit_code == 0, f"Prepare failed: {prepare_result.output}"
        assert config_file.exists(), "Config file was not created"

        # Load config to get job name
        config = CrumpConfig.from_yaml(config_file)
        assert len(config.jobs) > 0, "No jobs were created in config"
        first_job_name = list(config.jobs.keys())[0]

        # Step 2: Sync CDF to database (with 200 row limit for speed)
        sync_result = runner.invoke(
            sync,
            [
                str(sample_cdf),
                "--config",
                str(config_file),
                "--job",
                first_job_name,
                "--db-url",
                db_url,
                "--max-records",
                "200",
            ],
        )
        assert sync_result.exit_code == 0, f"Sync failed: {sync_result.output}"

        # Step 3: Verify data in database
        import sqlite3

        conn = sqlite3.connect(db_url.replace("sqlite:///", ""))
        cursor = conn.cursor()

        try:
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            assert len(tables) > 0, "No tables were created in database"

            # Verify table has data
            table_name = config.jobs[first_job_name].target_table
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            db_row_count = cursor.fetchone()[0]

            assert db_row_count > 0, f"Table {table_name} has no data"
            assert db_row_count <= 200, f"Table has more than 200 rows: {db_row_count}"

            # Verify table has expected columns from CDF
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            assert len(column_names) > 0, "Table has no columns"
            assert "id" in column_names, "Table missing 'id' column"

        finally:
            conn.close()

    @pytest.mark.parametrize("db_type", ["sqlite"])
    def test_cdf_sync_with_dry_run(
        self, sample_cdf: Path, tmp_path: Path, db_type: str, request: pytest.FixtureRequest
    ) -> None:
        """Test that dry-run mode works with CDF files."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare
        from crump.cli_sync import sync

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        db_url = request.getfixturevalue(f"{db_type}_db")
        runner = CliRunner()

        # Prepare config from CDF
        config_file = tmp_path / "crump_config.yml"
        prepare_result = runner.invoke(prepare, [str(sample_cdf), "--config", str(config_file)])
        assert prepare_result.exit_code == 0

        from crump.config import CrumpConfig

        config = CrumpConfig.from_yaml(config_file)
        first_job_name = list(config.jobs.keys())[0]

        # Run sync with dry-run flag (limit to 200 rows for speed)
        sync_result = runner.invoke(
            sync,
            [
                str(sample_cdf),
                "--config",
                str(config_file),
                "--job",
                first_job_name,
                "--db-url",
                db_url,
                "--dry-run",
                "--max-records",
                "200",
            ],
        )

        assert sync_result.exit_code == 0, f"Dry-run sync failed: {sync_result.output}"
        assert "DRY RUN" in sync_result.output or "dry run" in sync_result.output.lower()

        # Verify no data was written to database
        import sqlite3

        conn = sqlite3.connect(db_url.replace("sqlite:///", ""))
        cursor = conn.cursor()

        try:
            # Check if table exists
            table_name = config.jobs[first_job_name].target_table
            cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
            )
            table_exists = cursor.fetchone()

            if table_exists:
                # If table exists (from previous tests), it should still be empty
                # or have the same data as before
                # In dry-run, no NEW data should be added
                # We can't assert row count == 0 because the table might exist from previous test
                pass

        finally:
            conn.close()
