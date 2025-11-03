"""Tests for config module."""

from pathlib import Path

import pytest

from crump.config import CrumpConfig


class TestConfigParsing:
    """Test suite for config file parsing."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Test loading a valid configuration file."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
      email: email
""")

        config = CrumpConfig.from_yaml(config_file)
        assert len(config.jobs) == 1
        assert "test_job" in config.jobs

        job = config.get_job("test_job")
        assert job is not None
        assert job.name == "test_job"
        assert job.target_table == "users"
        assert len(job.id_mapping) == 1
        assert job.id_mapping[0].csv_column == "user_id"
        assert job.id_mapping[0].db_column == "id"
        assert len(job.columns) == 2

    def test_config_with_no_columns(self, tmp_path: Path) -> None:
        """Test config where no specific columns are listed (sync all)."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  sync_all:
    target_table: products
    id_mapping:
      product_id: id
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("sync_all")
        assert job is not None
        assert job.columns == []

    def test_config_file_not_found(self, tmp_path: Path) -> None:
        """Test error when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.yml"

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            CrumpConfig.from_yaml(config_file)

    def test_config_missing_jobs(self, tmp_path: Path) -> None:
        """Test error when config file doesn't have jobs section."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("other_section: value")

        with pytest.raises(ValueError, match="must contain 'jobs' section"):
            CrumpConfig.from_yaml(config_file)

    def test_config_missing_target_table(self, tmp_path: Path) -> None:
        """Test error when job is missing target_table."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  bad_job:
    id_mapping:
      id: id
""")

        with pytest.raises(ValueError, match="missing 'target_table'"):
            CrumpConfig.from_yaml(config_file)

    def test_config_missing_id_mapping(self, tmp_path: Path) -> None:
        """Test error when job is missing id_mapping."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  bad_job:
    target_table: users
""")

        with pytest.raises(ValueError, match="missing 'id_mapping'"):
            CrumpConfig.from_yaml(config_file)

    def test_get_nonexistent_job(self, tmp_path: Path) -> None:
        """Test getting a job that doesn't exist."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  job1:
    target_table: table1
    id_mapping:
      id: id
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("nonexistent")
        assert job is None


class TestColumnDataTypes:
    """Test suite for column data types in config."""

    def test_config_with_data_types(self, tmp_path: Path) -> None:
        """Test config with explicit data types."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  typed_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
      age:
        db_column: user_age
        type: integer
      salary:
        db_column: monthly_salary
        type: float
      birth_date:
        db_column: dob
        type: date
      bio:
        db_column: biography
        type: text
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("typed_job")

        assert job is not None
        assert len(job.id_mapping) == 1
        assert job.id_mapping[0].data_type is None  # ID has no explicit type
        assert len(job.columns) == 5

        # Check that data types are preserved
        name_col = next(c for c in job.columns if c.csv_column == "name")
        assert name_col.db_column == "full_name"
        assert name_col.data_type is None  # Simple format, no type

        age_col = next(c for c in job.columns if c.csv_column == "age")
        assert age_col.db_column == "user_age"
        assert age_col.data_type == "integer"

        salary_col = next(c for c in job.columns if c.csv_column == "salary")
        assert salary_col.db_column == "monthly_salary"
        assert salary_col.data_type == "float"

        date_col = next(c for c in job.columns if c.csv_column == "birth_date")
        assert date_col.db_column == "dob"
        assert date_col.data_type == "date"

        bio_col = next(c for c in job.columns if c.csv_column == "bio")
        assert bio_col.db_column == "biography"
        assert bio_col.data_type == "text"

    def test_extended_format_without_type(self, tmp_path: Path) -> None:
        """Test extended format with db_column but no type."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name:
        db_column: full_name
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")

        assert job is not None
        assert len(job.columns) == 1

        name_col = job.columns[0]
        assert name_col.csv_column == "name"
        assert name_col.db_column == "full_name"
        assert name_col.data_type is None

    def test_invalid_extended_format(self, tmp_path: Path) -> None:
        """Test that extended format without db_column raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name:
        type: text
""")

        with pytest.raises(ValueError, match="must have 'db_column'"):
            CrumpConfig.from_yaml(config_file)


class TestIdColumnMatchers:
    """Test suite for id_column_matchers configuration."""

    def test_config_with_id_column_matchers(self, tmp_path: Path) -> None:
        """Test loading config with id_column_matchers."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
id_column_matchers:
  - customer_id
  - account_id
  - user_id
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
""")

        config = CrumpConfig.from_yaml(config_file)

        assert config.id_column_matchers is not None
        assert config.id_column_matchers == ["customer_id", "account_id", "user_id"]

    def test_config_without_id_column_matchers(self, tmp_path: Path) -> None:
        """Test loading config without id_column_matchers (uses defaults)."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
""")

        config = CrumpConfig.from_yaml(config_file)

        assert config.id_column_matchers is None

    def test_config_invalid_id_column_matchers(self, tmp_path: Path) -> None:
        """Test that non-list id_column_matchers raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
id_column_matchers: "not a list"
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
""")

        with pytest.raises(ValueError, match="id_column_matchers must be a list"):
            CrumpConfig.from_yaml(config_file)

    def test_save_config_with_id_column_matchers(self, tmp_path: Path) -> None:
        """Test saving config with id_column_matchers."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="users",
            id_mapping=[ColumnMapping("user_id", "id")],
            columns=[ColumnMapping("name", "full_name")],
        )

        config = CrumpConfig(jobs={"test_job": job}, id_column_matchers=["custom_id", "record_id"])

        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        assert loaded_config.id_column_matchers == ["custom_id", "record_id"]


class TestCompoundPrimaryKeys:
    """Test suite for compound primary keys."""

    def test_config_with_compound_primary_key(self, tmp_path: Path) -> None:
        """Test loading config with compound primary key."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: user_logins
    id_mapping:
      user_id: user_id
      login_date: login_date
    columns:
      ip_address: ip
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.id_mapping) == 2
        assert job.id_mapping[0].csv_column == "user_id"
        assert job.id_mapping[0].db_column == "user_id"
        assert job.id_mapping[1].csv_column == "login_date"
        assert job.id_mapping[1].db_column == "login_date"

    def test_save_config_with_compound_primary_key(self, tmp_path: Path) -> None:
        """Test saving config with compound primary key."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="sales",
            id_mapping=[
                ColumnMapping("store_id", "store_id"),
                ColumnMapping("product_id", "product_id"),
            ],
            columns=[ColumnMapping("quantity", "qty")],
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        loaded_job = loaded_config.get_job("test_job")
        assert loaded_job is not None
        assert len(loaded_job.id_mapping) == 2
        assert loaded_job.id_mapping[0].db_column == "store_id"
        assert loaded_job.id_mapping[1].db_column == "product_id"


class TestIndexes:
    """Test suite for database indexes."""

    def test_config_with_single_column_index(self, tmp_path: Path) -> None:
        """Test loading config with single-column index."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      email: email
    indexes:
      - name: idx_email
        columns:
          - column: email
            order: ASC
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.indexes) == 1
        assert job.indexes[0].name == "idx_email"
        assert len(job.indexes[0].columns) == 1
        assert job.indexes[0].columns[0].column == "email"
        assert job.indexes[0].columns[0].order == "ASC"

    def test_config_with_multi_column_index(self, tmp_path: Path) -> None:
        """Test loading config with multi-column index."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: orders
    id_mapping:
      order_id: id
    columns:
      customer_id: customer_id
      order_date: order_date
    indexes:
      - name: idx_customer_date
        columns:
          - column: customer_id
            order: ASC
          - column: order_date
            order: DESC
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.indexes) == 1
        index = job.indexes[0]
        assert index.name == "idx_customer_date"
        assert len(index.columns) == 2
        assert index.columns[0].column == "customer_id"
        assert index.columns[0].order == "ASC"
        assert index.columns[1].column == "order_date"
        assert index.columns[1].order == "DESC"

    def test_config_with_multiple_indexes(self, tmp_path: Path) -> None:
        """Test loading config with multiple indexes."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      email: email
      name: name
    indexes:
      - name: idx_email
        columns:
          - column: email
            order: ASC
      - name: idx_name
        columns:
          - column: name
            order: ASC
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.indexes) == 2
        assert job.indexes[0].name == "idx_email"
        assert job.indexes[1].name == "idx_name"

    def test_save_config_with_indexes(self, tmp_path: Path) -> None:
        """Test saving config with indexes."""
        from crump.config import ColumnMapping, CrumpJob, Index, IndexColumn

        job = CrumpJob(
            name="test_job",
            target_table="products",
            id_mapping=[ColumnMapping("product_id", "id")],
            columns=[ColumnMapping("category", "cat"), ColumnMapping("price", "price")],
            indexes=[
                Index(
                    name="idx_category_price",
                    columns=[IndexColumn("cat", "ASC"), IndexColumn("price", "DESC")],
                )
            ],
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        loaded_job = loaded_config.get_job("test_job")
        assert loaded_job is not None
        assert len(loaded_job.indexes) == 1
        index = loaded_job.indexes[0]
        assert index.name == "idx_category_price"
        assert len(index.columns) == 2
        assert index.columns[0].column == "cat"
        assert index.columns[0].order == "ASC"
        assert index.columns[1].column == "price"
        assert index.columns[1].order == "DESC"

    def test_index_invalid_order(self) -> None:
        """Test that invalid index order raises error."""
        from crump.config import IndexColumn

        with pytest.raises(ValueError, match="Index order must be 'ASC' or 'DESC'"):
            IndexColumn("email", "INVALID")

    def test_index_no_columns(self) -> None:
        """Test that index with no columns raises error."""
        from crump.config import Index

        with pytest.raises(ValueError, match="Index must have at least one column"):
            Index("idx_test", [])


class TestFilenameToColumn:
    """Test suite for FilenameToColumn functionality."""

    def test_template_to_regex_conversion(self) -> None:
        """Test converting template string to regex pattern."""
        from crump.config import FilenameColumnMapping, FilenameToColumn

        columns = {
            "mission": FilenameColumnMapping("mission", "mission_name"),
            "date": FilenameColumnMapping("date", "obs_date", "date"),
        }
        ftc = FilenameToColumn(columns=columns, template="[mission]_data_[date].csv")

        # Test extracting values with template
        values = ftc.extract_values_from_filename("imap_data_20240115.csv")
        assert values is not None
        assert values["mission"] == "imap"
        assert values["date"] == "20240115"

    def test_regex_extraction(self) -> None:
        """Test extracting values using regex with named groups."""
        from crump.config import FilenameColumnMapping, FilenameToColumn

        columns = {
            "mission": FilenameColumnMapping("mission", "mission_name", "varchar(10)"),
            "sensor": FilenameColumnMapping("sensor", "sensor_type", "varchar(20)"),
            "date": FilenameColumnMapping("date", "obs_date", "date", use_to_delete_old_rows=True),
        }
        ftc = FilenameToColumn(
            columns=columns,
            regex=r"(?P<mission>[a-z]+)_level2_(?P<sensor>[a-z]+)_(?P<date>\d{8})\.cdf",
        )

        values = ftc.extract_values_from_filename("imap_level2_primary_20240115.cdf")
        assert values is not None
        assert values["mission"] == "imap"
        assert values["sensor"] == "primary"
        assert values["date"] == "20240115"

    def test_get_delete_key_columns(self) -> None:
        """Test getting columns marked for stale row deletion."""
        from crump.config import FilenameColumnMapping, FilenameToColumn

        columns = {
            "mission": FilenameColumnMapping("mission", "mission_name"),
            "date": FilenameColumnMapping("date", "obs_date", "date", use_to_delete_old_rows=True),
            "version": FilenameColumnMapping(
                "version", "file_version", "varchar(10)", use_to_delete_old_rows=True
            ),
        }
        ftc = FilenameToColumn(columns=columns, template="[mission]_[date]_v[version].csv")

        delete_columns = ftc.get_delete_key_columns()
        assert len(delete_columns) == 2
        assert "obs_date" in delete_columns
        assert "file_version" in delete_columns

    def test_both_template_and_regex_error(self) -> None:
        """Test that specifying both template and regex raises error."""
        from crump.config import FilenameColumnMapping, FilenameToColumn

        columns = {"date": FilenameColumnMapping("date", "file_date")}

        with pytest.raises(ValueError, match="exactly one of 'template' or 'regex'"):
            FilenameToColumn(columns=columns, template="[date].csv", regex=r"(?P<date>\d{8})")

    def test_neither_template_nor_regex_error(self) -> None:
        """Test that specifying neither template nor regex raises error."""
        from crump.config import FilenameColumnMapping, FilenameToColumn

        columns = {"date": FilenameColumnMapping("date", "file_date")}

        with pytest.raises(ValueError, match="exactly one of 'template' or 'regex'"):
            FilenameToColumn(columns=columns)

    def test_config_with_filename_to_column_template(self, tmp_path: Path) -> None:
        """Test loading config with filename_to_column using template."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: observations
    id_mapping:
      obs_id: id
    columns:
      value: measurement
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
        job = config.get_job("test_job")
        assert job is not None
        assert job.filename_to_column is not None
        assert job.filename_to_column.template == "[mission]_level2_[sensor]_[date]_v[version].cdf"
        assert job.filename_to_column.regex is None
        assert len(job.filename_to_column.columns) == 4

        # Check date column has use_to_delete_old_rows flag
        date_col = job.filename_to_column.columns["date"]
        assert date_col.use_to_delete_old_rows is True
        assert date_col.db_column == "observation_date"
        assert date_col.data_type == "date"

    def test_config_with_filename_to_column_regex(self, tmp_path: Path) -> None:
        """Test loading config with filename_to_column using regex."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  test_job:
    target_table: data
    id_mapping:
      record_id: id
    filename_to_column:
      regex: "(?P<prefix>[a-z]+)_(?P<date>\\d{8})\\.csv"
      columns:
        prefix:
          db_column: data_prefix
          type: varchar(20)
        date:
          db_column: file_date
          type: date
          use_to_delete_old_rows: true
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.filename_to_column is not None
        assert job.filename_to_column.regex == r"(?P<prefix>[a-z]+)_(?P<date>\d{8})\.csv"
        assert job.filename_to_column.template is None

    def test_config_with_both_template_and_regex_error(self, tmp_path: Path) -> None:
        """Test that config with both template and regex raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text(r"""
jobs:
  test_job:
    target_table: data
    id_mapping:
      id: id
    filename_to_column:
      template: "[date].csv"
      regex: "(?P<date>\\d{8})\\.csv"
      columns:
        date:
          db_column: file_date
""")

        with pytest.raises(ValueError, match="cannot have both 'template' and 'regex'"):
            CrumpConfig.from_yaml(config_file)

    def test_config_with_neither_template_nor_regex_error(self, tmp_path: Path) -> None:
        """Test that config without template or regex raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: data
    id_mapping:
      id: id
    filename_to_column:
      columns:
        date:
          db_column: file_date
""")

        with pytest.raises(
            ValueError, match="filename_to_column must have either 'template' or 'regex'"
        ):
            CrumpConfig.from_yaml(config_file)

    def test_save_config_with_filename_to_column(self, tmp_path: Path) -> None:
        """Test saving config with filename_to_column."""
        from crump.config import (
            ColumnMapping,
            CrumpJob,
            FilenameColumnMapping,
            FilenameToColumn,
        )

        ftc_columns = {
            "mission": FilenameColumnMapping("mission", "mission_name", "varchar(10)"),
            "date": FilenameColumnMapping("date", "obs_date", "date", use_to_delete_old_rows=True),
        }
        ftc = FilenameToColumn(columns=ftc_columns, template="[mission]_[date].csv")

        job = CrumpJob(
            name="test_job",
            target_table="observations",
            id_mapping=[ColumnMapping("obs_id", "id")],
            columns=[ColumnMapping("value", "measurement")],
            filename_to_column=ftc,
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        loaded_job = loaded_config.get_job("test_job")
        assert loaded_job is not None
        assert loaded_job.filename_to_column is not None
        assert loaded_job.filename_to_column.template == "[mission]_[date].csv"
        assert len(loaded_job.filename_to_column.columns) == 2

        date_col = loaded_job.filename_to_column.columns["date"]
        assert date_col.use_to_delete_old_rows is True


class TestSamplePercentage:
    """Test suite for sample_percentage configuration."""

    def test_config_with_sample_percentage(self, tmp_path: Path) -> None:
        """Test loading config with sample_percentage."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
    sample_percentage: 10
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.sample_percentage == 10

    def test_config_without_sample_percentage(self, tmp_path: Path) -> None:
        """Test loading config without sample_percentage (defaults to None)."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      name: full_name
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.sample_percentage is None

    def test_config_with_sample_percentage_100(self, tmp_path: Path) -> None:
        """Test loading config with sample_percentage of 100 (sync all rows)."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    sample_percentage: 100
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.sample_percentage == 100

    def test_config_with_sample_percentage_float(self, tmp_path: Path) -> None:
        """Test loading config with float sample_percentage."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    sample_percentage: 12.5
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert job.sample_percentage == 12.5

    def test_config_sample_percentage_out_of_range_high(self, tmp_path: Path) -> None:
        """Test that sample_percentage > 100 raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    sample_percentage: 150
""")

        with pytest.raises(ValueError, match="sample_percentage must be between 0 and 100"):
            CrumpConfig.from_yaml(config_file)

    def test_config_sample_percentage_out_of_range_low(self, tmp_path: Path) -> None:
        """Test that sample_percentage < 0 raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    sample_percentage: -10
""")

        with pytest.raises(ValueError, match="sample_percentage must be between 0 and 100"):
            CrumpConfig.from_yaml(config_file)

    def test_config_sample_percentage_invalid_type(self, tmp_path: Path) -> None:
        """Test that non-numeric sample_percentage raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    sample_percentage: "invalid"
""")

        with pytest.raises(ValueError, match="sample_percentage must be a number"):
            CrumpConfig.from_yaml(config_file)

    def test_save_config_with_sample_percentage(self, tmp_path: Path) -> None:
        """Test saving config with sample_percentage."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="users",
            id_mapping=[ColumnMapping("user_id", "id")],
            columns=[ColumnMapping("name", "full_name")],
            sample_percentage=25.0,
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        loaded_job = loaded_config.get_job("test_job")
        assert loaded_job is not None
        assert loaded_job.sample_percentage == 25.0

    def test_save_config_without_sample_percentage(self, tmp_path: Path) -> None:
        """Test saving config without sample_percentage (should not appear in YAML)."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="users",
            id_mapping=[ColumnMapping("user_id", "id")],
            columns=[ColumnMapping("name", "full_name")],
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Read file and check sample_percentage is not present
        content = config_file.read_text()
        assert "sample_percentage" not in content

    def test_save_config_with_sample_percentage_100(self, tmp_path: Path) -> None:
        """Test saving config with sample_percentage=100 (should not appear in YAML)."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="users",
            id_mapping=[ColumnMapping("user_id", "id")],
            columns=[ColumnMapping("name", "full_name")],
            sample_percentage=100,
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Read file and check sample_percentage is not present (since 100 is default)
        content = config_file.read_text()
        assert "sample_percentage" not in content


class TestColumnLookup:
    """Test suite for column lookup feature."""

    def test_config_with_lookup(self, tmp_path: Path) -> None:
        """Test loading config with lookup dictionary."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      status:
        db_column: status_code
        type: integer
        lookup:
          active: 1
          inactive: 0
          pending: 2
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.columns) == 1

        status_col = job.columns[0]
        assert status_col.csv_column == "status"
        assert status_col.db_column == "status_code"
        assert status_col.data_type == "integer"
        assert status_col.lookup is not None
        assert status_col.lookup == {"active": 1, "inactive": 0, "pending": 2}

    def test_apply_lookup_with_matching_value(self) -> None:
        """Test applying lookup with a value that exists in the lookup."""
        from crump.config import ColumnMapping

        col = ColumnMapping(
            csv_column="status",
            db_column="status_code",
            lookup={"active": 1, "inactive": 0},
        )

        result = col.apply_lookup("active")
        assert result == 1

        result = col.apply_lookup("inactive")
        assert result == 0

    def test_apply_lookup_with_non_matching_value(self) -> None:
        """Test applying lookup with a value that doesn't exist (passes through unchanged)."""
        from crump.config import ColumnMapping

        col = ColumnMapping(
            csv_column="status",
            db_column="status_code",
            lookup={"active": 1, "inactive": 0},
        )

        result = col.apply_lookup("unknown")
        assert result == "unknown"  # Passes through unchanged

    def test_apply_lookup_without_lookup_configured(self) -> None:
        """Test applying lookup when no lookup is configured (passes through unchanged)."""
        from crump.config import ColumnMapping

        col = ColumnMapping(csv_column="status", db_column="status_code")

        result = col.apply_lookup("active")
        assert result == "active"  # No lookup, so passes through

    def test_config_with_mixed_types_in_lookup(self, tmp_path: Path) -> None:
        """Test lookup with different value types (string to int, string to string, etc.)."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: products
    id_mapping:
      product_id: id
    columns:
      category:
        db_column: category_id
        type: integer
        lookup:
          electronics: 100
          clothing: 200
          food: 300
      size:
        db_column: size_code
        lookup:
          S: SM
          M: MD
          L: LG
          XL: XLG
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.columns) == 2

        category_col = next(c for c in job.columns if c.csv_column == "category")
        assert category_col.lookup == {"electronics": 100, "clothing": 200, "food": 300}

        size_col = next(c for c in job.columns if c.csv_column == "size")
        assert size_col.lookup == {"S": "SM", "M": "MD", "L": "LG", "XL": "XLG"}

    def test_config_lookup_invalid_type(self, tmp_path: Path) -> None:
        """Test that non-dict lookup raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: users
    id_mapping:
      user_id: id
    columns:
      status:
        db_column: status_code
        lookup: "not a dictionary"
""")

        with pytest.raises(ValueError, match="lookup must be a dictionary"):
            CrumpConfig.from_yaml(config_file)

    def test_save_config_with_lookup(self, tmp_path: Path) -> None:
        """Test saving config with lookup."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="users",
            id_mapping=[ColumnMapping("user_id", "id")],
            columns=[
                ColumnMapping(
                    "status",
                    "status_code",
                    data_type="integer",
                    lookup={"active": 1, "inactive": 0},
                )
            ],
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        loaded_job = loaded_config.get_job("test_job")
        assert loaded_job is not None
        assert len(loaded_job.columns) == 1

        status_col = loaded_job.columns[0]
        assert status_col.lookup == {"active": 1, "inactive": 0}

    def test_save_config_without_lookup(self, tmp_path: Path) -> None:
        """Test saving config without lookup (should not appear in YAML)."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="users",
            id_mapping=[ColumnMapping("user_id", "id")],
            columns=[ColumnMapping("status", "status_code", data_type="integer")],
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Read file and check lookup is not present
        content = config_file.read_text()
        assert "lookup" not in content


class TestCustomFunctions:
    """Test suite for custom function and expression column mappings."""

    def test_load_config_with_expression(self, tmp_path: Path) -> None:
        """Test loading config with inline expression."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: metrics
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
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.columns) == 3

        # Find the custom function column
        custom_col = [c for c in job.columns if c.db_column == "percentage_available"][0]
        assert custom_col.csv_column is None
        assert (
            custom_col.expression
            == "((float(total_available) - float(consumed)) / float(total_available)) * 100"
        )
        assert custom_col.input_columns == ["consumed", "total_available"]
        assert custom_col.data_type == "float"

    def test_load_config_with_function(self, tmp_path: Path) -> None:
        """Test loading config with external function reference."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: metrics
    id_mapping:
      id: id
    columns:
      ~:
        db_column: calculated_value
        function: "my_functions.calculate_percentage"
        input_columns: [value1, value2]
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.columns) == 1

        custom_col = job.columns[0]
        assert custom_col.csv_column is None
        assert custom_col.function == "my_functions.calculate_percentage"
        assert custom_col.input_columns == ["value1", "value2"]

    def test_apply_expression(self) -> None:
        """Test applying inline expression to row data."""
        from crump.config import ColumnMapping

        col_mapping = ColumnMapping(
            csv_column=None,
            db_column="percentage",
            expression="((float(total) - float(consumed)) / float(total)) * 100",
            input_columns=["consumed", "total"],
        )

        row_data = {"consumed": "30", "total": "100", "id": "1"}
        result = col_mapping.apply_custom_function(row_data)
        assert result == 70.0

    def test_apply_expression_with_math(self) -> None:
        """Test expression with various math operations."""
        from crump.config import ColumnMapping

        col_mapping = ColumnMapping(
            csv_column=None,
            db_column="result",
            expression="int(a) + float(b) * 2",
            input_columns=["a", "b"],
        )

        row_data = {"a": "10", "b": "5.5"}
        result = col_mapping.apply_custom_function(row_data)
        assert result == 21.0

    def test_expression_missing_input_column(self) -> None:
        """Test error when input column is missing from row data."""
        from crump.config import ColumnMapping

        col_mapping = ColumnMapping(
            csv_column=None,
            db_column="result",
            expression="a + b",
            input_columns=["a", "b"],
        )

        row_data = {"a": "10"}  # Missing 'b'
        with pytest.raises(ValueError, match="Input column 'b' not found"):
            col_mapping.apply_custom_function(row_data)

    def test_both_expression_and_function_raises_error(self) -> None:
        """Test that specifying both expression and function raises error."""
        from crump.config import ColumnMapping

        with pytest.raises(ValueError, match="Cannot specify both 'expression' and 'function'"):
            ColumnMapping(
                csv_column=None,
                db_column="result",
                expression="a + b",
                function="module.func",
                input_columns=["a", "b"],
            )

    def test_custom_function_without_input_columns_raises_error(self) -> None:
        """Test that custom function without input_columns raises error."""
        from crump.config import ColumnMapping

        with pytest.raises(ValueError, match="Must specify 'input_columns'"):
            ColumnMapping(
                csv_column=None,
                db_column="result",
                expression="a + b",
                input_columns=None,
            )

    def test_custom_function_with_csv_column_named_transformation(self) -> None:
        """Test that custom function can use csv_column for named transformations."""
        from crump.config import ColumnMapping

        # This is valid - allows transforming a named CSV column
        col_mapping = ColumnMapping(
            csv_column="temperature",
            db_column="temp_adjusted",
            expression="float(temperature) * 1.1 + 5",
            input_columns=["temperature"],
            data_type="float",
        )

        assert col_mapping.csv_column == "temperature"
        assert col_mapping.db_column == "temp_adjusted"
        assert col_mapping.expression == "float(temperature) * 1.1 + 5"
        assert col_mapping.input_columns == ["temperature"]

        # Test applying the transformation
        row_data = {"temperature": "20"}
        result = col_mapping.apply_custom_function(row_data)
        assert result == 27.0  # 20 * 1.1 + 5

    def test_invalid_expression_type(self, tmp_path: Path) -> None:
        """Test that non-string expression raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: metrics
    id_mapping:
      id: id
    columns:
      ~:
        db_column: result
        expression: 123
        input_columns: [a, b]
""")

        with pytest.raises(ValueError, match="expression must be a string"):
            CrumpConfig.from_yaml(config_file)

    def test_invalid_function_type(self, tmp_path: Path) -> None:
        """Test that non-string function raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: metrics
    id_mapping:
      id: id
    columns:
      ~:
        db_column: result
        function: ["not", "a", "string"]
        input_columns: [a, b]
""")

        with pytest.raises(ValueError, match="function must be a string"):
            CrumpConfig.from_yaml(config_file)

    def test_invalid_input_columns_type(self, tmp_path: Path) -> None:
        """Test that non-list input_columns raises error."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: metrics
    id_mapping:
      id: id
    columns:
      ~:
        db_column: result
        expression: "a + b"
        input_columns: "not a list"
""")

        with pytest.raises(ValueError, match="input_columns must be a list"):
            CrumpConfig.from_yaml(config_file)

    def test_save_config_with_expression(self, tmp_path: Path) -> None:
        """Test saving config with expression."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="metrics",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping(
                    csv_column=None,
                    db_column="percentage",
                    expression="(a / b) * 100",
                    input_columns=["a", "b"],
                    data_type="float",
                )
            ],
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        loaded_job = loaded_config.get_job("test_job")
        assert loaded_job is not None
        assert len(loaded_job.columns) == 1

        custom_col = loaded_job.columns[0]
        assert custom_col.csv_column is None
        assert custom_col.expression == "(a / b) * 100"
        assert custom_col.input_columns == ["a", "b"]

    def test_save_config_with_function(self, tmp_path: Path) -> None:
        """Test saving config with external function."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="metrics",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping(
                    csv_column=None,
                    db_column="result",
                    function="my_module.my_function",
                    input_columns=["x", "y"],
                )
            ],
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        loaded_job = loaded_config.get_job("test_job")
        assert loaded_job is not None
        assert len(loaded_job.columns) == 1

        custom_col = loaded_job.columns[0]
        assert custom_col.csv_column is None
        assert custom_col.function == "my_module.my_function"
        assert custom_col.input_columns == ["x", "y"]

    def test_load_config_with_named_column_transformation(self, tmp_path: Path) -> None:
        """Test loading config with expression on named CSV column."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: sensors
    id_mapping:
      id: id
    columns:
      temperature:
        db_column: temp_adjusted
        expression: "float(temperature) * 1.8 + 32"
        input_columns: [temperature]
        type: float
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.columns) == 1

        temp_col = job.columns[0]
        assert temp_col.csv_column == "temperature"
        assert temp_col.db_column == "temp_adjusted"
        assert temp_col.expression == "float(temperature) * 1.8 + 32"
        assert temp_col.input_columns == ["temperature"]
        assert temp_col.data_type == "float"

    def test_save_config_with_named_column_transformation(self, tmp_path: Path) -> None:
        """Test saving config with expression on named CSV column."""
        from crump.config import ColumnMapping, CrumpJob

        job = CrumpJob(
            name="test_job",
            target_table="sensors",
            id_mapping=[ColumnMapping("id", "id")],
            columns=[
                ColumnMapping(
                    csv_column="temperature",
                    db_column="temp_adjusted",
                    expression="float(temperature) * 1.1 + 5",
                    input_columns=["temperature"],
                    data_type="float",
                )
            ],
        )

        config = CrumpConfig(jobs={"test_job": job})
        config_file = tmp_path / "crump_config.yml"
        config.save_to_yaml(config_file)

        # Reload and verify
        loaded_config = CrumpConfig.from_yaml(config_file)
        loaded_job = loaded_config.get_job("test_job")
        assert loaded_job is not None
        assert len(loaded_job.columns) == 1

        temp_col = loaded_job.columns[0]
        assert temp_col.csv_column == "temperature"
        assert temp_col.db_column == "temp_adjusted"
        assert temp_col.expression == "float(temperature) * 1.1 + 5"
        assert temp_col.input_columns == ["temperature"]

    def test_load_config_with_polynomial_transformation(self, tmp_path: Path) -> None:
        """Test loading config with polynomial transformation."""
        config_file = tmp_path / "crump_config.yml"
        config_file.write_text("""
jobs:
  test_job:
    target_table: data
    id_mapping:
      id: id
    columns:
      value:
        db_column: value_calibrated
        expression: "float(value)**2 * 0.5 + float(value) * 2 + 10"
        input_columns: [value]
        type: float
""")

        config = CrumpConfig.from_yaml(config_file)
        job = config.get_job("test_job")
        assert job is not None
        assert len(job.columns) == 1

        value_col = job.columns[0]
        assert value_col.csv_column == "value"
        assert value_col.db_column == "value_calibrated"
        assert value_col.expression == "float(value)**2 * 0.5 + float(value) * 2 + 10"
        assert value_col.input_columns == ["value"]
