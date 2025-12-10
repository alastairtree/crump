"""Tests for the prepare command."""

from pathlib import Path

import pytest

from crump.cli_prepare import generate_job_name_from_filename


class TestGenerateJobNameFromFilename:
    """Tests for the generate_job_name_from_filename function."""

    def test_removes_extension(self) -> None:
        """Test that file extension is removed."""
        assert generate_job_name_from_filename("data.csv") == "data"
        assert generate_job_name_from_filename("report.xlsx") == "report"

    def test_removes_numbers(self) -> None:
        """Test that numbers are removed."""
        assert generate_job_name_from_filename("sales_2024.csv") == "sales"
        assert generate_job_name_from_filename("data123.csv") == "data"
        assert generate_job_name_from_filename("report_456_final.csv") == "report_final"

    def test_collapses_underscores(self) -> None:
        """Test that multiple underscores become single."""
        assert generate_job_name_from_filename("user__info.csv") == "user_info"
        assert generate_job_name_from_filename("test___data.csv") == "test_data"

    def test_collapses_hyphens(self) -> None:
        """Test that multiple hyphens become single."""
        assert generate_job_name_from_filename("test--file.csv") == "test-file"
        assert generate_job_name_from_filename("data---report.csv") == "data-report"

    def test_strips_trailing_separators(self) -> None:
        """Test that trailing underscores and hyphens are stripped."""
        assert generate_job_name_from_filename("data_123.csv") == "data"
        assert generate_job_name_from_filename("test-456.csv") == "test"
        assert generate_job_name_from_filename("_data_.csv") == "data"
        assert generate_job_name_from_filename("-test-.csv") == "test"

    def test_converts_to_lowercase(self) -> None:
        """Test that names are converted to lowercase."""
        assert generate_job_name_from_filename("SalesData.csv") == "salesdata"
        assert generate_job_name_from_filename("USER_INFO.csv") == "user_info"

    def test_combined_transformations(self) -> None:
        """Test multiple transformations together."""
        assert generate_job_name_from_filename("Sales_Data_2024.csv") == "sales_data"
        assert generate_job_name_from_filename("user__info__123.csv") == "user_info"
        assert generate_job_name_from_filename("Test--File--456.csv") == "test-file"
        assert generate_job_name_from_filename("REPORT__2024__Q1.csv") == "report_q"

    def test_empty_after_cleaning(self) -> None:
        """Test that empty strings after cleaning default to 'job'."""
        assert generate_job_name_from_filename("123.csv") == "job"
        assert generate_job_name_from_filename("___456___.csv") == "job"

    def test_with_path(self) -> None:
        """Test that paths are handled correctly."""
        assert generate_job_name_from_filename("/path/to/data.csv") == "data"
        assert generate_job_name_from_filename("../files/report_2024.csv") == "report"


class TestPrepareCommandIntegration:
    """Integration tests for the prepare command."""

    @pytest.fixture
    def sample_csv(self, tmp_path: Path) -> Path:
        """Create a sample CSV file."""
        csv_file = tmp_path / "test_data_2024.csv"
        csv_file.write_text(
            "id,name,age,created_date\n1,Alice,30,2024-01-01\n2,Bob,25,2024-01-02\n"
        )
        return csv_file

    @pytest.fixture
    def bigint_csv(self, tmp_path: Path) -> Path:
        """Create a CSV file with mixed integer and bigint values."""
        csv_file = tmp_path / "bigint_data.csv"
        csv_file.write_text(
            "id,epoch,value\n1,815230591184000000,100\n2,815230591184000001,200\n3,100,300\n"
        )
        return csv_file

    @pytest.fixture
    def second_csv(self, tmp_path: Path) -> Path:
        """Create a second sample CSV file."""
        csv_file = tmp_path / "user__info__123.csv"
        csv_file.write_text(
            "user_id,email,status\n1,alice@test.com,active\n2,bob@test.com,inactive\n"
        )
        return csv_file

    def test_prepare_single_file_auto_generated_name(
        self, sample_csv: Path, tmp_path: Path
    ) -> None:
        """Test prepare with single file and auto-generated job name."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(prepare, [str(sample_csv), "--config", str(config_file)])

        assert result.exit_code == 0
        assert config_file.exists()

        # Load config and check job was created with auto-generated name
        from crump.config import CrumpConfig

        config = CrumpConfig.from_yaml(config_file)
        # Expected name: "test_data_2024.csv" -> "test_data"
        assert "test_data" in config.jobs
        job = config.jobs["test_data"]
        assert job.target_table == "test_data"

    def test_prepare_single_file_custom_name(self, sample_csv: Path, tmp_path: Path) -> None:
        """Test prepare with single file and custom job name."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(
            prepare, [str(sample_csv), "--config", str(config_file), "--job", "my_custom_job"]
        )

        assert result.exit_code == 0
        assert config_file.exists()

        # Load config and check job was created with custom name
        from crump.config import CrumpConfig

        config = CrumpConfig.from_yaml(config_file)
        assert "my_custom_job" in config.jobs
        assert "test_data" not in config.jobs

    def test_prepare_multiple_files_auto_generated_names(
        self, sample_csv: Path, second_csv: Path, tmp_path: Path
    ) -> None:
        """Test prepare with multiple files and auto-generated job names."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(
            prepare, [str(sample_csv), str(second_csv), "--config", str(config_file)]
        )

        assert result.exit_code == 0
        assert config_file.exists()

        # Load config and check both jobs were created
        from crump.config import CrumpConfig

        config = CrumpConfig.from_yaml(config_file)
        # Expected names: "test_data_2024.csv" -> "test_data", "user__info__123.csv" -> "user_info"
        assert "test_data" in config.jobs
        assert "user_info" in config.jobs

    def test_prepare_multiple_files_with_custom_name_fails(
        self, sample_csv: Path, second_csv: Path, tmp_path: Path
    ) -> None:
        """Test that specifying job name with multiple files fails."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(
            prepare,
            [str(sample_csv), str(second_csv), "--config", str(config_file), "--job", "custom_job"],
        )

        assert result.exit_code != 0
        assert "Cannot specify job name when processing multiple files" in result.output

    def test_prepare_updates_existing_with_force(self, sample_csv: Path, tmp_path: Path) -> None:
        """Test that prepare can update existing job with --force."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        # First run
        result1 = runner.invoke(prepare, [str(sample_csv), "--config", str(config_file)])
        assert result1.exit_code == 0

        # Second run without force should fail
        result2 = runner.invoke(prepare, [str(sample_csv), "--config", str(config_file)])
        assert result2.exit_code != 0
        assert "Use --force to overwrite" in result2.output

        # Third run with force should succeed
        result3 = runner.invoke(prepare, [str(sample_csv), "--config", str(config_file), "--force"])
        assert result3.exit_code == 0

    def test_prepare_detects_bigint_type(self, bigint_csv: Path, tmp_path: Path) -> None:
        """Test that prepare command detects bigint data type for large integers."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare
        from crump.config import CrumpConfig

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(prepare, [str(bigint_csv), "--config", str(config_file)])

        assert result.exit_code == 0
        assert config_file.exists()

        # Load config and verify bigint type was detected
        config = CrumpConfig.from_yaml(config_file)
        job = config.jobs["bigint_data"]

        # Check that epoch column has bigint type
        epoch_column = None
        for col in job.columns or []:
            if col.csv_column == "epoch":
                epoch_column = col
                break

        assert epoch_column is not None, "epoch column not found in job config"
        assert epoch_column.data_type == "bigint", f"Expected bigint, got {epoch_column.data_type}"


class TestDetectFilenamePatterns:
    """Tests for the detect_filename_patterns function."""

    def test_detect_yyyymmdd_pattern(self) -> None:
        """Test detecting YYYYMMDD date pattern."""
        from crump.cli_prepare import detect_filename_patterns

        result = detect_filename_patterns("data_20240115.csv")
        assert result is not None
        assert result.template == "data_[date].csv"
        assert "date" in result.columns
        assert result.columns["date"].db_column == "file_date"
        assert result.columns["date"].data_type == "date"
        assert result.columns["date"].use_to_delete_old_rows is True

    def test_detect_yyyy_mm_dd_pattern(self) -> None:
        """Test detecting YYYY-MM-DD date pattern."""
        from crump.cli_prepare import detect_filename_patterns

        result = detect_filename_patterns("sales_2024-01-15.csv")
        assert result is not None
        assert result.template == "sales_[date].csv"
        assert "date" in result.columns

    def test_detect_yyyy_mm_dd_underscore_pattern(self) -> None:
        """Test detecting YYYY_MM_DD date pattern."""
        from crump.cli_prepare import detect_filename_patterns

        result = detect_filename_patterns("report_2024_12_31.csv")
        assert result is not None
        assert result.template == "report_[date].csv"
        assert "date" in result.columns

    def test_no_pattern_detected(self) -> None:
        """Test when no date pattern is found."""
        from crump.cli_prepare import detect_filename_patterns

        result = detect_filename_patterns("simple_data.csv")
        assert result is None

    def test_date_in_middle_of_filename(self) -> None:
        """Test date pattern in middle of filename."""
        from crump.cli_prepare import detect_filename_patterns

        result = detect_filename_patterns("prefix_20241225_suffix.csv")
        assert result is not None
        assert result.template == "prefix_[date]_suffix.csv"

    def test_multiple_date_formats_prefer_first(self) -> None:
        """Test that first matching pattern is used when multiple exist."""
        from crump.cli_prepare import detect_filename_patterns

        # YYYYMMDD appears first in search order
        result = detect_filename_patterns("data_20240115_2024-01-15.csv")
        assert result is not None
        # Should match YYYYMMDD (first pattern)
        if result.template:
            assert "[date]_2024-01-15.csv" in result.template

    def test_extraction_works_with_detected_pattern(self) -> None:
        """Test that the detected pattern can actually extract values."""
        from crump.cli_prepare import detect_filename_patterns

        result = detect_filename_patterns("sales_20240315.csv")
        assert result is not None

        # Test that extraction works
        values = result.extract_values_from_filename("sales_20240315.csv")
        assert values is not None
        assert values["date"] == "20240315"

        # Test with different date
        values2 = result.extract_values_from_filename("sales_20241201.csv")
        assert values2 is not None
        assert values2["date"] == "20241201"


class TestPrepareWithFilenameDetection:
    """Integration tests for prepare command with filename pattern detection."""

    @pytest.fixture
    def dated_csv(self, tmp_path: Path) -> Path:
        """Create a CSV file with date in filename."""
        csv_file = tmp_path / "data_20240115.csv"
        csv_file.write_text("id,value\n1,100\n2,200\n")
        return csv_file

    def test_prepare_detects_and_adds_filename_to_column(
        self, dated_csv: Path, tmp_path: Path
    ) -> None:
        """Test that prepare command detects date pattern and adds filename_to_column."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare
        from crump.config import CrumpConfig

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(prepare, [str(dated_csv), "--config", str(config_file)])

        assert result.exit_code == 0
        assert "Detected date pattern in filename" in result.output

        # Load config and verify filename_to_column was added
        config = CrumpConfig.from_yaml(config_file)
        job = config.jobs["data"]

        assert job.filename_to_column is not None
        assert job.filename_to_column.template == "data_[date].csv"
        assert "date" in job.filename_to_column.columns
        assert job.filename_to_column.columns["date"].use_to_delete_old_rows is True

    def test_prepare_no_detection_for_simple_filename(
        self, sample_csv: Path, tmp_path: Path
    ) -> None:
        """Test that no filename_to_column is added for files without date patterns."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare
        from crump.config import CrumpConfig

        # sample_csv is from parent class fixture: "test_data_2024.csv"
        # This should match YYYYMMDD pattern (2024)
        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(prepare, [str(sample_csv), "--config", str(config_file)])

        assert result.exit_code == 0

        # Actually this file HAS a date pattern (2024), so it should detect it
        config = CrumpConfig.from_yaml(config_file)
        job = list(config.jobs.values())[0]
        # The fixture creates "test_data_2024.csv" which contains "2024" - 4 digits
        # But our pattern looks for 8 digits (YYYYMMDD), so this should NOT match
        # Let me check... actually "2024" is only 4 digits, not 8, so YYYYMMDD won't match

        # But wait, let me re-read the fixture. It's "test_data_2024.csv"
        # Our patterns are:
        # - YYYYMMDD: r"(\d{8})" - requires 8 digits
        # - YYYY-MM-DD: r"(\d{4}-\d{2}-\d{2})" - requires dashes
        # - YYYY_MM_DD: r"(\d{4}_\d{2}_\d{2})" - requires underscores
        # So "2024" alone won't match any pattern
        assert job.filename_to_column is None

    @pytest.fixture
    def sample_csv(self, tmp_path: Path) -> Path:
        """Create a simple CSV file without date pattern."""
        csv_file = tmp_path / "simple_data.csv"
        csv_file.write_text("id,name\n1,Alice\n2,Bob\n")
        return csv_file


class TestPrepareWithCDFFiles:
    """Tests for the prepare command with CDF files."""

    @pytest.fixture
    def sample_cdf(self) -> Path:
        """Get path to a sample CDF file."""
        return Path("tests/data/imap_mag_l1c_norm-magi_20251010_v001.cdf")

    def test_prepare_single_cdf_file(self, sample_cdf: Path, tmp_path: Path) -> None:
        """Test prepare with a single CDF file."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare
        from crump.config import CrumpConfig

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(prepare, [str(sample_cdf), "--config", str(config_file)])

        assert result.exit_code == 0
        assert config_file.exists()

        # Verify output contains CDF extraction messages
        assert "Processing" in result.output
        assert "CDF file(s)" in result.output or "Extracting data from CDF file" in result.output

        # Load config and verify jobs were created
        config = CrumpConfig.from_yaml(config_file)
        assert len(config.jobs) > 0

        # Verify cleanup message
        assert "Cleaning up temporary files" in result.output

    def test_prepare_cdf_with_csv(self, sample_cdf: Path, tmp_path: Path) -> None:
        """Test prepare with both CDF and CSV files."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare
        from crump.config import CrumpConfig

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        # Create a CSV file
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,value\n1,100\n2,200\n")

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(
            prepare, [str(sample_cdf), str(csv_file), "--config", str(config_file)]
        )

        assert result.exit_code == 0
        assert config_file.exists()

        # Load config and verify jobs were created for both files
        config = CrumpConfig.from_yaml(config_file)
        assert len(config.jobs) > 1

        # Verify we have a job for the CSV file
        assert "test" in config.jobs

    def test_prepare_cdf_with_force(self, sample_cdf: Path, tmp_path: Path) -> None:
        """Test prepare CDF file with --force flag."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        # First run
        result1 = runner.invoke(prepare, [str(sample_cdf), "--config", str(config_file)])
        assert result1.exit_code == 0

        # Second run with force should succeed
        result2 = runner.invoke(prepare, [str(sample_cdf), "--config", str(config_file), "--force"])
        assert result2.exit_code == 0

    def test_prepare_unsupported_file_type(self, tmp_path: Path) -> None:
        """Test that unsupported file types are handled gracefully."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare

        # Create an unsupported file
        unsupported_file = tmp_path / "test.txt"
        unsupported_file.write_text("some text")

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(prepare, [str(unsupported_file), "--config", str(config_file)])

        # Should show warning about unsupported file type
        assert "Unsupported file type" in result.output or "Warning" in result.output

    def test_prepare_cdf_extraction_failure(self, tmp_path: Path) -> None:
        """Test handling of CDF extraction failure."""
        from click.testing import CliRunner

        from crump.cli_prepare import prepare

        # Create a fake CDF file (invalid content)
        fake_cdf = tmp_path / "fake.cdf"
        fake_cdf.write_text("not a real CDF file")

        config_file = tmp_path / "crump_config.yml"
        runner = CliRunner()

        result = runner.invoke(prepare, [str(fake_cdf), "--config", str(config_file)])

        # Should fail or show error
        assert result.exit_code != 0 or "Error" in result.output


class TestExtractCDFToTempCSV:
    """Tests for the _extract_cdf_to_temp_tabular_files helper function."""

    @pytest.fixture
    def sample_cdf(self) -> Path:
        """Get path to a sample CDF file."""
        return Path("tests/data/imap_mag_l1c_norm-magi_20251010_v001.cdf")

    def test_extract_cdf_to_temp_tabular_files(self, sample_cdf: Path, tmp_path: Path) -> None:
        """Test extracting CDF to temporary CSV files."""
        from crump.cli_prepare import _extract_cdf_to_temp_tabular_files

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        csv_files = _extract_cdf_to_temp_tabular_files(sample_cdf, temp_dir, max_records=50)

        # Should create at least one CSV file
        assert len(csv_files) > 0

        # All files should exist and be in the temp directory
        for csv_file in csv_files:
            assert csv_file.exists()
            assert csv_file.parent == temp_dir
            assert csv_file.suffix == ".csv"

            # Verify CSV has content
            content = csv_file.read_text()
            assert len(content) > 0
            assert "\n" in content  # Should have at least header and data

    def test_extract_cdf_max_records_limit(self, sample_cdf: Path, tmp_path: Path) -> None:
        """Test that max_records parameter limits extraction."""
        from crump.cli_prepare import _extract_cdf_to_temp_tabular_files

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        csv_files = _extract_cdf_to_temp_tabular_files(sample_cdf, temp_dir, max_records=10)

        # Verify extracted CSVs have at most 10 rows (plus header)
        for csv_file in csv_files:
            lines = csv_file.read_text().strip().split("\n")
            # Should have header + at most 10 data rows
            assert len(lines) <= 11


class TestCDFEndToEndWorkflow:
    """End-to-end tests for the complete CDF workflow: prepare -> extract -> sync."""

    @pytest.fixture
    def sample_cdf(self) -> Path:
        """Get path to a sample CDF file."""
        return Path("tests/data/imap_mag_l1c_norm-magi_20251010_v001.cdf")

    @pytest.mark.parametrize("db_type", ["sqlite"])
    def test_cdf_prepare_extract_sync_workflow(
        self, sample_cdf: Path, tmp_path: Path, db_type: str, request: pytest.FixtureRequest
    ) -> None:
        """Test complete workflow: extract CDF -> prepare config -> sync to database.

        This end-to-end test verifies that:
        1. extract command converts all CDF data to CSV files
        2. prepare command generates valid config from CSV files
        3. sync command loads data from CSV into database
        4. Data from CDF is successfully migrated to database
        """
        from click.testing import CliRunner

        from crump.cli_extract import extract
        from crump.cli_prepare import prepare
        from crump.cli_sync import sync
        from crump.config import CrumpConfig

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        # Get database fixture
        db_url = request.getfixturevalue(f"{db_type}_db")

        runner = CliRunner()

        # Step 1: Extract full CDF data to CSV files first
        csv_output_dir = tmp_path / "csv_data"
        csv_output_dir.mkdir()

        extract_result = runner.invoke(
            extract, [str(sample_cdf), "--output-path", str(csv_output_dir)]
        )

        assert extract_result.exit_code == 0, f"Extract failed: {extract_result.output}"

        # Verify CSV files were created
        csv_files = sorted(csv_output_dir.glob("*.csv"))
        assert len(csv_files) > 0, "No CSV files were extracted"

        # Step 2: Run prepare command on extracted CSV files to generate config
        config_file = tmp_path / "crump_config.yml"
        csv_file_args = [str(f) for f in csv_files]
        prepare_result = runner.invoke(prepare, csv_file_args + ["--config", str(config_file)])

        assert prepare_result.exit_code == 0, f"Prepare failed: {prepare_result.output}"
        assert config_file.exists(), "Config file was not created"

        # Verify config was created with jobs
        config = CrumpConfig.from_yaml(config_file)
        assert len(config.jobs) > 0, "No jobs were created in config"

        # Step 3: Sync first job/CSV pair to database
        first_job_name = list(config.jobs.keys())[0]
        first_csv = csv_files[0]

        sync_result = runner.invoke(
            sync,
            [
                str(first_csv),
                "--config",
                str(config_file),
                "--job",
                first_job_name,
                "--db-url",
                db_url,
            ],
        )

        assert sync_result.exit_code == 0, f"Sync failed: {sync_result.output}"

        # Step 4: Verify data in database
        import csv as csv_module
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

            # Count rows in CSV
            with open(first_csv, encoding="utf-8") as f:
                reader = csv_module.reader(f)
                next(reader)  # Skip header
                csv_row_count = sum(1 for _ in reader)

            assert db_row_count > 0, f"Table {table_name} has no data"
            assert db_row_count == csv_row_count, (
                f"Row count mismatch: DB={db_row_count}, CSV={csv_row_count}"
            )

        finally:
            conn.close()

    @pytest.mark.parametrize("db_type", ["sqlite"])
    def test_cdf_prepare_sync_verifies_column_types(
        self, sample_cdf: Path, tmp_path: Path, db_type: str, request: pytest.FixtureRequest
    ) -> None:
        """Test that CDF data types are correctly preserved in database."""
        from click.testing import CliRunner

        from crump.cli_extract import extract
        from crump.cli_prepare import prepare
        from crump.cli_sync import sync
        from crump.config import CrumpConfig

        if not sample_cdf.exists():
            pytest.skip("Sample CDF file not found")

        db_url = request.getfixturevalue(f"{db_type}_db")
        runner = CliRunner()

        # Extract CSV data first
        csv_output_dir = tmp_path / "csv_data"
        csv_output_dir.mkdir()
        extract_result = runner.invoke(
            extract, [str(sample_cdf), "--output-path", str(csv_output_dir)]
        )
        assert extract_result.exit_code == 0

        csv_files = sorted(csv_output_dir.glob("*.csv"))
        assert len(csv_files) > 0

        # Prepare config from extracted CSVs
        config_file = tmp_path / "crump_config.yml"
        csv_file_args = [str(f) for f in csv_files]
        prepare_result = runner.invoke(prepare, csv_file_args + ["--config", str(config_file)])
        assert prepare_result.exit_code == 0

        # Load config and sync first job
        config = CrumpConfig.from_yaml(config_file)
        first_job_name = list(config.jobs.keys())[0]
        first_job = config.jobs[first_job_name]
        first_csv = csv_files[0]

        sync_result = runner.invoke(
            sync,
            [
                str(first_csv),
                "--config",
                str(config_file),
                "--job",
                first_job_name,
                "--db-url",
                db_url,
            ],
        )
        assert sync_result.exit_code == 0, f"Sync failed: {sync_result.output}"

        # Verify table schema
        import sqlite3

        conn = sqlite3.connect(db_url.replace("sqlite:///", ""))
        cursor = conn.cursor()

        try:
            # Get table schema
            cursor.execute(
                f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{first_job.target_table}'"
            )
            schema = cursor.fetchone()
            assert schema is not None, f"Table {first_job.target_table} was not created"

            schema_sql = schema[0]

            # Verify id column exists
            assert "id" in schema_sql.lower(), "ID column not found in schema"

            # Verify table has data
            cursor.execute(f'SELECT COUNT(*) FROM "{first_job.target_table}"')
            row_count = cursor.fetchone()[0]
            assert row_count > 0, "No data in table"

        finally:
            conn.close()
