"""Tests for CLI extract command with config and parquet support."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from click.testing import CliRunner

from crump.cli import main
from crump.cli_extract import extract


@pytest.fixture
def solo_cdf_file() -> Path:
    """Path to Solar Orbiter CDF test file."""
    return Path("tests/data/solo_L2_mag-rtn-normal-1-minute-internal_20241225_V00.cdf")


@pytest.fixture
def imap_cdf_file() -> Path:
    """Path to IMAP CDF test file."""
    return Path("tests/data/imap_mag_l1c_norm-magi_20251010_v001.cdf")


class TestExtractCommandHelp:
    """Test suite for extract command help and basic options."""

    def test_extract_help(self, cli_runner: CliRunner) -> None:
        """Test extract command help output."""
        result = cli_runner.invoke(main, ["extract", "--help"])
        assert result.exit_code == 0
        assert "Extract data from CDF files" in result.output
        assert "--config" in result.output
        assert "--job" in result.output
        assert "--parquet" in result.output

    def test_extract_missing_files(self, cli_runner: CliRunner) -> None:
        """Test extract command without required files argument fails."""
        result = cli_runner.invoke(main, ["extract"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output


class TestExtractWithConfig:
    """Tests for _extract_with_config() function via CLI extract command."""

    def test_extract_with_config_basic_csv(
        self, cli_runner: CliRunner, imap_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting CDF with config-based column mapping to CSV."""
        # Create a config file with column mappings
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  imap_mag:
    target_table: mag_data
    id_mapping:
      epoch: timestamp
    columns:
      vectors_x: vector_x
      vectors_y: vector_y
      vector_magnitude: magnitude
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(imap_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "imap_mag",
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"
        assert "Extracting" in result.output
        assert "config-based mapping" in result.output
        assert "Extraction complete" in result.output

        # Check that at least one CSV file was created
        csv_files = list(output_dir.glob("*.csv"))
        assert len(csv_files) > 0, f"No CSV files created. Output: {result.output}"

        # Verify CSV content
        csv_file = csv_files[0]
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []

            # Check that transformed column names are present
            assert "timestamp" in headers, f"timestamp not in headers: {headers}"
            assert "vector_x" in headers, f"vector_x not in headers: {headers}"
            assert "vector_y" in headers, f"vector_y not in headers: {headers}"
            assert "magnitude" in headers, f"magnitude not in headers: {headers}"

            # Original column names should NOT be present
            assert "epoch" not in headers
            assert "vectors_x" not in headers

            rows = list(reader)
            assert len(rows) > 0

    def test_extract_with_config_auto_detect_job(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting with config that has single job (auto-detection)."""
        # Create a config file with a single job
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  solo_mag:
    target_table: solo_data
    id_mapping:
      EPOCH: time_id
    columns:
      EPOCH: epoch_time
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Don't specify --job, should auto-detect
        result = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"
        assert "Auto-detected job: solo_mag" in result.output
        assert "Extraction complete" in result.output

        # Check that at least one output file was created
        csv_files = list(output_dir.glob("*.csv"))
        assert len(csv_files) > 0

    def test_extract_with_config_invalid_job(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting with nonexistent job name fails gracefully."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  real_job:
    target_table: test_table
    id_mapping:
      EPOCH: id
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "nonexistent_job",
            ],
        )

        assert result.exit_code != 0
        assert "Job 'nonexistent_job' not found" in result.output
        assert "Available jobs: real_job" in result.output

    def test_extract_with_config_multiple_jobs_no_job_name(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test that extract with multiple jobs but no --job fails gracefully."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  job_one:
    target_table: table_one
    id_mapping:
      EPOCH: id
  job_two:
    target_table: table_two
    id_mapping:
      EPOCH: id
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code != 0
        assert "Available jobs:" in result.output

    def test_extract_with_config_max_records(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting with config and max_records limit."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      EPOCH: id
    columns:
      B_r: b_radial
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        max_records = 50

        result = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "--max-records",
                str(max_records),
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"
        assert f"Max records: {max_records:,}" in result.output

        # Check created file has limited rows
        csv_files = list(output_dir.glob("*.csv"))
        assert len(csv_files) > 0

        with open(csv_files[0], encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
            # 1 header + max_records data rows
            assert len(rows) <= max_records + 1

    def test_extract_with_config_specific_variables(
        self, cli_runner: CliRunner, imap_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting specific variables with config mapping."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      epoch: timestamp
    columns:
      vector_magnitude: magnitude
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(imap_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "-v",
                "epoch",
                "-v",
                "vector_magnitude",
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"
        assert "epoch, vector_magnitude" in result.output

    def test_extract_with_config_job_without_config_fails(
        self, cli_runner: CliRunner, solo_cdf_file: Path
    ) -> None:
        """Test that specifying --job without --config fails."""
        result = cli_runner.invoke(extract, [str(solo_cdf_file), "--job", "some_job"])

        assert result.exit_code != 0
        assert "--job requires --config" in result.output


class TestExtractWithoutConfig:
    """Tests for raw extraction (without config) via CLI extract command."""

    def test_extract_raw_to_csv(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting CDF without config to CSV files."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"
        assert "Extraction complete" in result.output

        # Check that at least one CSV file was created
        csv_files = list(output_dir.glob("*.csv"))
        assert len(csv_files) > 0

    def test_extract_raw_to_parquet(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting CDF without config to Parquet files."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--parquet",
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"
        assert "Extraction complete" in result.output
        assert "Parquet" in result.output

        # Check that Parquet files were created
        parquet_files = list(output_dir.glob("*.parquet"))
        assert len(parquet_files) > 0

        # Verify Parquet files are readable
        from crump.tabular_file import create_reader

        for pq_file in parquet_files:
            with create_reader(pq_file) as reader:
                assert len(reader.fieldnames) > 0
                rows = list(reader)
                assert len(rows) > 0


class TestExtractWithConfigToParquet:
    """Tests for extracting with config to Parquet format."""

    def test_extract_with_config_to_parquet(
        self, cli_runner: CliRunner, imap_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting CDF with config to Parquet format."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  imap_mag:
    target_table: mag_data
    id_mapping:
      epoch: timestamp
    columns:
      vectors_x: vector_x
      vector_magnitude: magnitude
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(imap_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "imap_mag",
                "--parquet",
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"
        assert "Parquet" in result.output
        assert "Extraction complete" in result.output

        # Check that at least one Parquet file was created
        parquet_files = list(output_dir.glob("*.parquet"))
        assert len(parquet_files) > 0, f"No Parquet files created. Output: {result.output}"

        # Verify Parquet content
        from crump.tabular_file import create_reader

        parquet_file = parquet_files[0]
        with create_reader(parquet_file) as reader:
            headers = reader.fieldnames

            # Check that transformed column names are present
            assert "timestamp" in headers, f"timestamp not in headers: {headers}"
            assert "vector_x" in headers, f"vector_x not in headers: {headers}"
            assert "magnitude" in headers, f"magnitude not in headers: {headers}"

            rows = list(reader)
            assert len(rows) > 0

    def test_extract_with_config_to_parquet_max_records(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting with config to Parquet with max_records limit."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      EPOCH: id
    columns:
      EPOCH: epoch_time
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        max_records = 25

        result = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "--max-records",
                str(max_records),
                "--parquet",
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"

        # Check created file has limited rows
        parquet_files = list(output_dir.glob("*.parquet"))
        assert len(parquet_files) > 0

        from crump.tabular_file import create_reader

        with create_reader(parquet_files[0]) as reader:
            rows = list(reader)
            assert len(rows) <= max_records

    def test_extract_parquet_replaces_csv_extension(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test that --parquet flag replaces .csv extension with .parquet."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--filename",
                "[SOURCE_FILE].csv",
                "--parquet",
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"

        # Should create .parquet files, not .csv
        csv_files = list(output_dir.glob("*.csv"))
        parquet_files = list(output_dir.glob("*.parquet"))

        assert len(csv_files) == 0, f"CSV files were created: {csv_files}"
        assert len(parquet_files) > 0, f"No Parquet files created. Output: {result.output}"


class TestExtractAppendMode:
    """Tests for extract command append mode with config."""

    def test_extract_with_config_append_csv(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting with config and append mode for CSV."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      EPOCH: id
    columns:
      EPOCH: epoch_time
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # First extraction
        result1 = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "--max-records",
                "50",
            ],
        )
        assert result1.exit_code == 0, f"First extract failed: {result1.output}"

        csv_files = list(output_dir.glob("*.csv"))
        assert len(csv_files) > 0
        csv_file = csv_files[0]

        with open(csv_file, encoding="utf-8") as f:
            first_row_count = len(f.readlines()) - 1  # Subtract header

        # Second extraction with append
        result2 = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "--max-records",
                "50",
                "--append",
            ],
        )
        assert result2.exit_code == 0, f"Second extract failed: {result2.output}"

        with open(csv_file, encoding="utf-8") as f:
            second_row_count = len(f.readlines()) - 1

        # Should have double the rows
        assert second_row_count == first_row_count * 2

    def test_extract_with_config_append_parquet(
        self, cli_runner: CliRunner, solo_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting with config and append mode for Parquet."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: test_table
    id_mapping:
      EPOCH: id
    columns:
      EPOCH: epoch_time
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # First extraction
        result1 = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "--max-records",
                "50",
                "--parquet",
            ],
        )
        assert result1.exit_code == 0, f"First extract failed: {result1.output}"

        from crump.tabular_file import create_reader

        parquet_files = list(output_dir.glob("*.parquet"))
        assert len(parquet_files) > 0
        parquet_file = parquet_files[0]

        with create_reader(parquet_file) as reader:
            first_row_count = len(list(reader))

        # Second extraction with append
        result2 = cli_runner.invoke(
            extract,
            [
                str(solo_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "test_job",
                "--max-records",
                "50",
                "--append",
                "--parquet",
            ],
        )
        assert result2.exit_code == 0, f"Second extract failed: {result2.output}"

        with create_reader(parquet_file) as reader:
            second_row_count = len(list(reader))

        # Should have double the rows
        assert second_row_count == first_row_count * 2


class TestExtractFilenameToColumn:
    """Tests for extract with filename_to_column config."""

    def test_extract_with_filename_to_column(
        self, cli_runner: CliRunner, imap_cdf_file: Path, tmp_path: Path
    ) -> None:
        """Test extracting with filename_to_column configuration."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  imap_mag:
    target_table: mag_data
    id_mapping:
      epoch: timestamp
    columns:
      vector_magnitude: magnitude
    filename_to_column:
      template: "imap_mag_l1c_norm-magi_[date]_v[version].cdf"
      columns:
        date:
          db_column: file_date
          type: date
        version:
          db_column: file_version
          type: text
""")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = cli_runner.invoke(
            extract,
            [
                str(imap_cdf_file),
                "--output-path",
                str(output_dir),
                "--config",
                str(config_file),
                "--job",
                "imap_mag",
            ],
        )

        assert result.exit_code == 0, f"Extract failed: {result.output}"

        # Check that at least one CSV file was created
        csv_files = list(output_dir.glob("*.csv"))
        assert len(csv_files) > 0

        # Verify CSV content includes filename-extracted columns
        with open(csv_files[0], encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []

            # filename_to_column should add these columns
            assert "file_date" in headers, f"file_date not in headers: {headers}"
            assert "file_version" in headers, f"file_version not in headers: {headers}"

            # Verify first row has extracted values
            # Note: the date is extracted as raw string from filename template, not converted
            first_row = next(reader)
            assert first_row.get("file_date") == "20251010"
            assert first_row.get("file_version") == "001"
