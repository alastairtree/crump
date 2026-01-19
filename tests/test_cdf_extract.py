"""Tests for CDF extraction functionality."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from crump.cdf_extractor import extract_cdf_to_tabular_file, extract_cdf_with_config
from crump.cdf_reader import read_cdf_variables
from crump.config import ColumnMapping, CrumpJob


@pytest.fixture
def solo_cdf_file() -> Path:
    """Path to Solar Orbiter CDF test file."""
    return Path("tests/data/solo_L2_mag-rtn-normal-1-minute-internal_20241225_V00.cdf")


@pytest.fixture
def imap_cdf_file() -> Path:
    """Path to IMAP CDF test file."""
    return Path("tests/data/imap_mag_l1c_norm-magi_20251010_v001.cdf")


def test_read_cdf_variables_solo(solo_cdf_file: Path) -> None:
    """Test reading variables from Solar Orbiter CDF file."""
    variables = read_cdf_variables(solo_cdf_file)

    assert len(variables) > 0

    # Variables should be sorted by record count (descending)
    for i in range(len(variables) - 1):
        assert variables[i].num_records >= variables[i + 1].num_records

    # Check that we have the expected main variables
    var_names = {var.name for var in variables}
    assert "EPOCH" in var_names
    assert "B_RTN" in var_names


def test_read_cdf_variables_imap(imap_cdf_file: Path) -> None:
    """Test reading variables from IMAP CDF file."""
    variables = read_cdf_variables(imap_cdf_file)

    assert len(variables) > 0

    # Check for expected variables
    var_names = {var.name for var in variables}
    assert "vectors" in var_names
    assert "epoch" in var_names
    assert "vector_magnitude" in var_names


def test_epoch_conversion_imap(imap_cdf_file: Path) -> None:
    """Test that EPOCH values are converted to datetime64."""
    import numpy as np

    variables = read_cdf_variables(imap_cdf_file)

    # Find the epoch variable
    epoch_var = next((v for v in variables if v.name == "epoch"), None)
    assert epoch_var is not None, "epoch variable not found"

    # Check that epoch data is datetime64
    assert isinstance(epoch_var.data, np.ndarray)
    assert np.issubdtype(epoch_var.data.dtype, np.datetime64), (
        f"Expected datetime64, got {epoch_var.data.dtype}"
    )

    # Check that values are valid datetimes
    # The filename says 20251010, so dates should be around October 10, 2025
    first_value = epoch_var.data[0]
    first_str = str(first_value)
    assert "2025-10" in first_str, f"Expected date in October 2025, got {first_str}"


def test_epoch_conversion_solo(solo_cdf_file: Path) -> None:
    """Test that EPOCH values are converted to datetime64 in Solar Orbiter file."""
    import numpy as np

    variables = read_cdf_variables(solo_cdf_file)

    # Find the EPOCH variable
    epoch_var = next((v for v in variables if v.name == "EPOCH"), None)
    assert epoch_var is not None, "EPOCH variable not found"

    # Check that EPOCH data is datetime64
    assert isinstance(epoch_var.data, np.ndarray)
    assert np.issubdtype(epoch_var.data.dtype, np.datetime64), (
        f"Expected datetime64, got {epoch_var.data.dtype}"
    )

    # Check that values are valid datetimes
    # The filename says 20241225, so dates should be around December 25, 2024
    first_value = epoch_var.data[0]
    first_str = str(first_value)
    assert "2024-12" in first_str, f"Expected date in December 2024, got {first_str}"


def test_epoch_csv_extraction(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test that EPOCH values are written as datetime strings in CSV."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=True,
        append=False,
        variable_names=None,
        max_records=10,
    )

    # Find a result that has the epoch column
    epoch_result = None
    for result in results:
        if "epoch" in result.column_names:
            epoch_result = result
            break

    assert epoch_result is not None, "No CSV file contains epoch column"

    # Read the CSV and check epoch values
    with open(epoch_result.output_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        assert len(rows) > 0, "CSV has no data rows"

        # Check that epoch values are datetime strings, not integers
        first_epoch = rows[0]["epoch"]
        assert "2025-10" in first_epoch, f"Expected datetime string with 2025-10, got {first_epoch}"
        assert "T" in first_epoch, f"Expected ISO format datetime with 'T', got {first_epoch}"
        assert ":" in first_epoch, f"Expected time component with ':', got {first_epoch}"


def test_extract_with_automerge(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting CDF with automerge enabled."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=True,
        append=False,
        variable_names=None,
    )

    # Should create merged CSV files
    assert len(results) > 0

    # Check that files were created
    for result in results:
        assert result.output_file.exists()
        assert result.num_rows > 0
        assert result.num_columns > 0

        # Verify CSV is readable
        with open(result.output_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == result.num_rows
            assert len(reader.fieldnames or []) == result.num_columns


def test_extract_without_automerge(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting CDF with automerge disabled."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=None,
    )

    # Should create separate CSV for each variable
    assert len(results) > 0

    # Each result should correspond to a single variable
    for result in results:
        assert len(result.variable_names) == 1


def test_extract_specific_variables(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting specific variables only."""
    requested_vars = ["vectors", "epoch"]

    results = extract_cdf_to_tabular_file(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=requested_vars,
    )

    # Should only extract the requested variables
    extracted_vars = set()
    for result in results:
        extracted_vars.update(result.variable_names)

    assert extracted_vars == set(requested_vars)


def test_extract_nonexistent_variable(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting a variable that doesn't exist."""
    with pytest.raises(ValueError, match="Variables not found"):
        extract_cdf_to_tabular_file(
            cdf_file_path=solo_cdf_file,
            output_dir=tmp_path,
            filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
            automerge=False,
            append=False,
            variable_names=["nonexistent_variable"],
        )


def test_extract_with_custom_filename_template(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extraction with custom filename template."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="data_[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=["EPOCH"],
    )

    assert len(results) == 1
    assert results[0].output_file.name == "data_EPOCH.csv"


def test_extract_with_append_mode(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extraction with append mode."""
    # First extraction
    results1 = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=["EPOCH"],
    )

    assert len(results1) == 1
    original_rows = results1[0].num_rows
    output_file = results1[0].output_file

    # Second extraction with append
    extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=True,
        variable_names=["EPOCH"],
    )

    # File should now have double the rows (header is not duplicated)
    with open(output_file, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        # First row is header, rest are data
        assert len(rows) == original_rows * 2 + 1  # 1 header + 2x data


def test_extract_file_exists_error(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test that extraction fails if file exists and append is False."""
    # First extraction
    extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=["EPOCH"],
    )

    # Second extraction without append should fail
    with pytest.raises(FileExistsError, match="Output file already exists"):
        extract_cdf_to_tabular_file(
            cdf_file_path=solo_cdf_file,
            output_dir=tmp_path,
            filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
            automerge=False,
            append=False,
            variable_names=["EPOCH"],
        )


def test_extract_append_header_mismatch(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test that appending with different headers fails."""
    # Create a CSV with different headers
    csv_file = tmp_path / "solo_L2_mag-rtn-normal-1-minute-internal_20241225_V00-EPOCH.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["wrong_column", "another_wrong_column"])
        writer.writerow([1, 2])

    # Try to append with different headers
    with pytest.raises(ValueError, match="existing file has different columns"):
        extract_cdf_to_tabular_file(
            cdf_file_path=solo_cdf_file,
            output_dir=tmp_path,
            filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
            automerge=False,
            append=True,
            variable_names=["EPOCH"],
        )


def test_extract_filename_uses_first_variable(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test that merged CSV files use the first variable name in filename."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=True,
        append=False,
        variable_names=["vectors", "epoch", "vector_magnitude"],
    )

    # All three variables have the same record count, should be merged
    assert len(results) == 1
    result = results[0]

    # Filename should use the first variable name (vectors)
    assert "vectors" in result.output_file.name
    # Should NOT contain record count
    assert "records" not in result.output_file.name


def test_extract_filename_collision_adds_suffix(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test that filename collisions within one extraction get numerical suffixes."""
    # Create two CSV files manually that would cause collision
    # We'll extract variables with the same name pattern

    # Extract with automerge disabled to get separate files
    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="test.csv",  # Same name for all
        automerge=False,
        append=False,
        variable_names=None,
    )

    # All variables should have unique filenames
    filenames = [r.output_file.name for r in results]
    assert len(filenames) == len(set(filenames))  # All unique

    # First should be "test.csv", rest should have suffixes
    assert "test.csv" in filenames
    if len(filenames) > 1:
        assert any("test_" in f for f in filenames)


def test_extract_array_variables_column_expansion(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test that array variables are expanded into multiple columns."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=["vectors"],
    )

    assert len(results) == 1
    result = results[0]

    # vectors has shape (N, 4), so should create 4 columns
    assert result.num_columns == 4

    # Check column names contain the variable name
    for col_name in result.column_names:
        assert "vectors" in col_name


def test_extract_creates_output_directory(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test that extraction creates the output directory if it doesn't exist."""
    output_dir = tmp_path / "new_directory" / "nested"

    assert not output_dir.exists()

    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=output_dir,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=True,
        append=False,
        variable_names=None,
    )

    assert output_dir.exists()
    assert len(results) > 0


def test_extract_merges_same_record_count_variables(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test that variables with the same record count are merged when automerge is True."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=True,
        append=False,
        variable_names=["vectors", "epoch", "vector_magnitude"],
    )

    # All three variables should have the same record count and be merged
    assert len(results) == 1
    result = results[0]

    # Should include all three variables
    assert set(result.variable_names) == {"vectors", "epoch", "vector_magnitude"}

    # Should have columns from all variables (vectors has 4, epoch has 1, vector_magnitude has 1)
    assert result.num_columns == 6


def test_cdf_variable_column_names_with_labels(solo_cdf_file: Path) -> None:
    """Test that CDF variables use label metadata for column names when available."""
    variables = read_cdf_variables(solo_cdf_file)

    # Find B_RTN variable which has labels
    b_rtn_var = next((v for v in variables if v.name == "B_RTN"), None)
    assert b_rtn_var is not None

    # Get column names (needs access to CDF file for metadata)
    from crump.cdf_reader import get_column_names_for_variable

    col_names = get_column_names_for_variable(b_rtn_var, solo_cdf_file)

    # Should use labels from LBL1_B_RTN: B_r, B_t, B_n
    assert len(col_names) == 3
    assert "B_r" in col_names[0] or "B_t" in col_names[1] or "B_n" in col_names[2]


def test_unique_column_names(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test that all column names in extracted CSV are unique."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=True,
        append=False,
        variable_names=None,
    )

    for result in results:
        # Check that all column names are unique
        assert len(result.column_names) == len(set(result.column_names))


def test_extract_with_max_records(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extraction with max_records limits the number of rows."""
    max_records = 100

    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=["EPOCH"],
        max_records=max_records,
    )

    assert len(results) == 1
    result = results[0]

    # Should have exactly max_records rows
    assert result.num_rows == max_records

    # Verify actual file has correct number of rows
    with open(result.output_file, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        # 1 header + max_records data rows
        assert len(rows) == max_records + 1


def test_extract_max_records_larger_than_available(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test that max_records larger than available data extracts all data."""
    max_records = 999999  # Larger than available data

    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=["EPOCH"],
        max_records=max_records,
    )

    assert len(results) == 1
    result = results[0]

    # Should have all available rows (1440 in the solo file)
    assert result.num_rows == 1440


def test_extract_max_records_with_automerge(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test max_records with automerge enabled."""
    max_records = 50

    results = extract_cdf_to_tabular_file(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=True,
        append=False,
        variable_names=["vectors", "epoch"],
        max_records=max_records,
    )

    # Both variables have the same record count and should be merged
    assert len(results) == 1
    result = results[0]

    # Should have max_records rows
    assert result.num_rows == max_records

    # Verify the CSV file
    with open(result.output_file, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        assert len(rows) == max_records + 1  # 1 header + max_records data


def test_extract_max_records_none_extracts_all(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test that max_records=None extracts all data."""
    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].csv",
        automerge=False,
        append=False,
        variable_names=["EPOCH"],
        max_records=None,
    )

    assert len(results) == 1
    result = results[0]

    # Should have all 1440 rows
    assert result.num_rows == 1440


def test_extract_cdf_with_config_basic(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting CDF with config-based column mapping."""
    # Create a simple job config
    job = CrumpJob(
        name="test_job",
        target_table="test_table",
        id_mapping=[ColumnMapping(csv_column="epoch", db_column="id")],
        columns=[
            ColumnMapping(csv_column="vectors_x", db_column="vector_x"),
            ColumnMapping(csv_column="vectors_y", db_column="vector_y"),
            ColumnMapping(csv_column="vector_magnitude", db_column="magnitude"),
        ],
    )

    results = extract_cdf_with_config(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        job=job,
        max_records=None,
    )

    # Should have at least one result
    assert len(results) > 0
    result = results[0]

    # Verify extraction result
    assert result.output_file.exists()
    assert result.num_rows > 0
    assert result.num_columns == 4  # id + vector_x + vector_y + magnitude

    # Verify CSV content
    with open(result.output_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        assert headers == ["id", "vector_x", "vector_y", "magnitude"]

        rows = list(reader)
        assert len(rows) == result.num_rows


def test_extract_cdf_with_config_column_renaming(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test that config-based extraction renames columns correctly."""
    # Create a job with column renaming
    job = CrumpJob(
        name="test_job",
        target_table="test_table",
        id_mapping=[ColumnMapping(csv_column="epoch", db_column="timestamp")],
        columns=[
            ColumnMapping(csv_column="vector_magnitude", db_column="mag"),
        ],
    )

    results = extract_cdf_with_config(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        job=job,
        max_records=None,
    )

    assert len(results) > 0
    result = results[0]

    # Verify CSV has renamed columns
    with open(result.output_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        assert "timestamp" in headers
        assert "mag" in headers
        assert "epoch" not in headers  # Original name should not be present
        assert "vector_magnitude" not in headers


def test_extract_cdf_with_config_max_records(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test that max_records works with config-based extraction."""
    max_records = 50

    job = CrumpJob(
        name="test_job",
        target_table="test_table",
        id_mapping=[ColumnMapping(csv_column="EPOCH", db_column="id")],
        columns=[
            ColumnMapping(csv_column="B_r", db_column="b_radial"),
        ],
    )

    results = extract_cdf_with_config(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        job=job,
        max_records=max_records,
    )

    assert len(results) > 0
    result = results[0]

    # Should have exactly max_records rows
    assert result.num_rows == max_records

    # Verify file
    with open(result.output_file, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        assert len(rows) == max_records + 1  # 1 header + max_records data


def test_extract_cdf_with_config_missing_column(imap_cdf_file: Path, tmp_path: Path) -> None:
    """Test that extraction returns empty list when column mappings don't match."""
    # Create a job that references a non-existent column
    job = CrumpJob(
        name="test_job",
        target_table="test_table",
        id_mapping=[ColumnMapping(csv_column="nonexistent_column", db_column="id")],
        columns=[],
    )

    # Should return empty list when columns don't match
    results = extract_cdf_with_config(
        cdf_file_path=imap_cdf_file,
        output_dir=tmp_path,
        job=job,
        max_records=None,
    )

    # No matching CSV should be produced
    assert len(results) == 0


def test_extract_cdf_to_parquet(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting CDF file to Parquet format."""
    from crump.tabular_file import create_reader

    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].parquet",
        automerge=True,
        append=False,
        variable_names=None,
        max_records=None,
        use_parquet=True,
    )

    assert len(results) > 0

    # Verify at least one file is Parquet
    parquet_files = [r for r in results if r.output_file.suffix == ".parquet"]
    assert len(parquet_files) > 0

    # Verify we can read the Parquet file
    parquet_file = parquet_files[0].output_file
    assert parquet_file.exists()

    with create_reader(parquet_file) as reader:
        assert len(reader.fieldnames) > 0
        rows = list(reader)
        assert len(rows) > 0


def test_extract_cdf_to_parquet_specific_variables(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting specific variables from CDF to Parquet."""
    from crump.tabular_file import create_reader

    results = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].parquet",
        automerge=False,
        append=False,
        variable_names=["EPOCH"],
        max_records=100,
        use_parquet=True,
    )

    assert len(results) == 1
    assert results[0].output_file.suffix == ".parquet"
    assert results[0].num_rows == 100

    # Verify Parquet file content
    with create_reader(results[0].output_file) as reader:
        assert reader.fieldnames == ["EPOCH"]
        rows = list(reader)
        assert len(rows) == 100


def test_extract_cdf_to_parquet_with_config(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting CDF to Parquet with config-based column mapping."""
    from crump.config import CrumpConfig
    from crump.tabular_file import create_reader

    # Create config file
    config_file = tmp_path / "crump_config.yml"
    config_file.write_text("""
jobs:
  mag_data:
    target_table: magnetic_field
    id_mapping:
      EPOCH: time_id
    columns:
      EPOCH: epoch_time
""")

    config = CrumpConfig.from_yaml(config_file)
    job = config.get_job("mag_data")
    assert job is not None

    # Extract with config using Parquet
    results = extract_cdf_with_config(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        job=job,
        max_records=50,
        automerge=True,
        variable_names=None,
        append=False,
        filename_template="[SOURCE_FILE]_transformed.parquet",
        use_parquet=True,
    )

    assert len(results) > 0

    # Verify Parquet file with transformed column names
    parquet_result = results[0]
    assert parquet_result.output_file.suffix == ".parquet"

    with create_reader(parquet_result.output_file) as reader:
        # Should have transformed column name
        assert "epoch_time" in reader.fieldnames
        rows = list(reader)
        assert len(rows) > 0
        assert len(rows) <= 50


def test_extract_parquet_append_mode(solo_cdf_file: Path, tmp_path: Path) -> None:
    """Test extracting CDF to Parquet with append mode."""
    from crump.tabular_file import create_reader

    # First extraction
    results1 = extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].parquet",
        automerge=False,
        append=False,
        variable_names=["EPOCH"],
        max_records=100,
        use_parquet=True,
    )

    assert len(results1) == 1
    original_rows = results1[0].num_rows
    output_file = results1[0].output_file

    # Second extraction with append
    extract_cdf_to_tabular_file(
        cdf_file_path=solo_cdf_file,
        output_dir=tmp_path,
        filename_template="[SOURCE_FILE]-[VARIABLE_NAME].parquet",
        automerge=False,
        append=True,
        variable_names=["EPOCH"],
        max_records=100,
        use_parquet=True,
    )

    # File should now have double the rows
    with create_reader(output_file) as reader:
        rows = list(reader)
        assert len(rows) == original_rows * 2
