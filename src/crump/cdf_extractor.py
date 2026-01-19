"""CDF to CSV/Parquet extraction functionality."""

from __future__ import annotations

import csv
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from crump.cdf_reader import CDFVariable, get_column_names_for_variable, read_cdf_variables
from crump.config import CrumpJob, apply_row_transformations
from crump.tabular_file import create_writer


@dataclass
class ExtractionResult:
    """Result of extracting data from a CDF file."""

    output_file: Path
    num_rows: int
    num_columns: int
    column_names: list[str]
    file_size: int
    variable_names: list[str]


def _make_unique_column_names(column_names: list[str]) -> list[str]:
    """Ensure all column names are unique by adding suffixes if needed.

    Args:
        column_names: List of column names that may contain duplicates

    Returns:
        List of unique column names
    """
    seen: dict[str, int] = {}
    unique_names = []

    for name in column_names:
        if name not in seen:
            seen[name] = 0
            unique_names.append(name)
        else:
            seen[name] += 1
            unique_names.append(f"{name}_{seen[name]}")

    return unique_names


def _group_variables_by_record_count(
    variables: list[CDFVariable],
) -> dict[int, list[CDFVariable]]:
    """Group variables by their record count.

    Args:
        variables: List of CDFVariable objects

    Returns:
        Dictionary mapping record count to list of variables
    """
    groups: dict[int, list[CDFVariable]] = {}

    for var in variables:
        if var.num_records not in groups:
            groups[var.num_records] = []
        groups[var.num_records].append(var)

    return groups


def _expand_variable_to_columns(
    variable: CDFVariable, cdf_file_path: Path, max_records: int | None = None
) -> tuple[list[str], list[list[Any]], int]:
    """Expand a CDF variable into column names and data columns.

    Args:
        variable: The variable to expand
        cdf_file_path: Path to the CDF file
        max_records: Maximum number of records to extract (None = all)

    Returns:
        Tuple of (column_names, data_columns, actual_records) where data_columns is a list of columns
        and actual_records is the number of records actually extracted
    """
    column_names = get_column_names_for_variable(variable, cdf_file_path)

    # Determine how many records to extract
    actual_records = variable.num_records
    if max_records is not None:
        actual_records = min(actual_records, max_records)

    if not variable.is_array:
        # 1D variable - single column
        if isinstance(variable.data, np.ndarray):
            data_array = variable.data[:actual_records]
            # Convert datetime64 to ISO format strings
            if np.issubdtype(data_array.dtype, np.datetime64):
                data: list[Any] = [str(dt) for dt in data_array]
            else:
                data = data_array.tolist()
        else:
            data = [variable.data]
        data_columns = [data]
    else:
        # 2D variable - multiple columns
        data_columns = []
        for i in range(variable.array_size):
            col_array = variable.data[:actual_records, i]
            # Convert datetime64 to ISO format strings
            if np.issubdtype(col_array.dtype, np.datetime64):
                column_data: list[Any] = [str(dt) for dt in col_array]
            else:
                column_data = col_array.tolist()
            data_columns.append(column_data)

    return column_names, data_columns, actual_records


def _generate_output_filename(
    template: str, source_file: Path, variable_name: str | None = None
) -> str:
    """Generate output filename from template.

    Args:
        template: Filename template with [SOURCE_FILE] and [VARIABLE_NAME] placeholders
        source_file: Source CDF file path
        variable_name: Variable name (optional)

    Returns:
        Generated filename
    """
    filename = template
    filename = filename.replace("[SOURCE_FILE]", source_file.stem)

    if variable_name:
        filename = filename.replace("[VARIABLE_NAME]", variable_name)
    else:
        # If no variable name, remove the placeholder
        filename = filename.replace("-[VARIABLE_NAME]", "").replace("_[VARIABLE_NAME]", "")
        filename = filename.replace("[VARIABLE_NAME]-", "").replace("[VARIABLE_NAME]_", "")
        filename = filename.replace("[VARIABLE_NAME]", "")

    return filename


def _get_unique_filename(base_filename: str, used_filenames: set[str]) -> str:
    """Get a unique filename by adding a numerical suffix if needed.

    Args:
        base_filename: The base filename to use
        used_filenames: Set of filenames already used in this extraction

    Returns:
        A unique filename
    """
    # If filename hasn't been used yet in this extraction, use it as-is
    if base_filename not in used_filenames:
        return base_filename

    # Add numerical suffix to make it unique
    base_name = Path(base_filename).stem
    extension = Path(base_filename).suffix
    counter = 1

    while True:
        new_filename = f"{base_name}_{counter}{extension}"
        if new_filename not in used_filenames:
            return new_filename
        counter += 1


def _validate_existing_file_header(file_path: Path, expected_columns: list[str]) -> bool:
    """Validate that an existing CSV or Parquet file has the expected header.

    File format is auto-detected from the file extension.

    Args:
        file_path: Path to the file
        expected_columns: Expected column names

    Returns:
        True if headers match, False otherwise
    """
    try:
        from crump.tabular_file import create_reader

        with create_reader(file_path) as reader:
            existing_header = reader.fieldnames
            return existing_header == expected_columns
    except Exception:
        return False


def extract_cdf_to_tabular_file(
    cdf_file_path: Path,
    output_dir: Path,
    filename_template: str = "[SOURCE_FILE]-[VARIABLE_NAME].csv",
    automerge: bool = True,
    append: bool = False,
    variable_names: list[str] | None = None,
    max_records: int | None = None,
    use_parquet: bool = False,  # noqa: ARG001  # Deprecated parameter kept for compatibility
) -> list[ExtractionResult]:
    """Extract data from a CDF file to CSV or Parquet files.

    The output format is determined automatically from the filename extension
    in the filename_template (.csv for CSV, .parquet or .pq for Parquet).

    Args:
        cdf_file_path: Path to the CDF file
        output_dir: Directory to save output files
        filename_template: Template for output filenames (extension determines format)
        automerge: Whether to merge variables with same record count
        append: Whether to append to existing files
        variable_names: List of specific variables to extract (None = all)
        max_records: Maximum number of records to extract per variable (None = all)
        use_parquet: Deprecated. Use filename extension instead.

    Returns:
        List of ExtractionResult objects

    Raises:
        ValueError: If specified variables are not found
        FileExistsError: If output file exists and append is False
        ValueError: If appending but headers don't match
    """
    # Read all variables
    all_variables = read_cdf_variables(cdf_file_path)

    # Filter variables if specific ones are requested
    if variable_names:
        filtered_vars = []
        requested_set = set(variable_names)
        found_set = set()

        for var in all_variables:
            if var.name in requested_set:
                filtered_vars.append(var)
                found_set.add(var.name)

        # Check for missing variables
        missing = requested_set - found_set
        if missing:
            raise ValueError(f"Variables not found in CDF file: {', '.join(sorted(missing))}")

        variables = filtered_vars
    else:
        variables = all_variables

    if not variables:
        return []

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    used_filenames: set[str] = set()  # Track filenames used in this extraction

    if automerge:
        # Group variables by record count and create merged CSV files
        groups = _group_variables_by_record_count(variables)

        for record_count, group_vars in sorted(groups.items(), key=lambda x: -x[0]):
            # Skip variables with very few records (likely metadata)
            if record_count < 2:
                continue

            # Collect all columns from this group
            all_column_names = []
            all_data_columns = []
            var_names_in_group = []
            actual_records_list = []

            for var in group_vars:
                col_names, data_cols, actual_records = _expand_variable_to_columns(
                    var, cdf_file_path, max_records
                )
                all_column_names.extend(col_names)
                all_data_columns.extend(data_cols)
                var_names_in_group.append(var.name)
                actual_records_list.append(actual_records)

            # Use the minimum actual records across all variables in the group
            actual_record_count = min(actual_records_list) if actual_records_list else 0

            # Make column names unique
            all_column_names = _make_unique_column_names(all_column_names)

            # Generate filename using first variable name
            primary_var = var_names_in_group[0]
            base_filename = _generate_output_filename(filename_template, cdf_file_path, primary_var)

            # Get unique filename (add numerical suffix if needed)
            output_filename = _get_unique_filename(base_filename, used_filenames)
            used_filenames.add(output_filename)
            output_path = output_dir / output_filename

            # Check for existing file
            if output_path.exists() and not append:
                raise FileExistsError(
                    f"Output file already exists: {output_path}. "
                    "Use --append to add data to existing file."
                )

            # Validate header if appending
            if (
                append
                and output_path.exists()
                and not _validate_existing_file_header(output_path, all_column_names)
            ):
                raise ValueError(
                    f"Cannot append to {output_path}: "
                    f"existing file has different columns. "
                    f"Expected columns: {', '.join(all_column_names)}"
                )

            # Write to file using tabular writer (format auto-detected from extension)
            write_append = append and output_path.exists()

            with create_writer(output_path, append=write_append) as writer:
                # Write header only if not appending
                if not write_append:
                    writer.writerow(all_column_names)

                # Transpose data to write rows
                for row_idx in range(actual_record_count):
                    row = [col[row_idx] for col in all_data_columns]
                    writer.writerow(row)

            file_size = output_path.stat().st_size
            results.append(
                ExtractionResult(
                    output_file=output_path,
                    num_rows=actual_record_count,
                    num_columns=len(all_column_names),
                    column_names=all_column_names,
                    file_size=file_size,
                    variable_names=var_names_in_group,
                )
            )

    else:
        # Create separate CSV for each variable
        for var in variables:
            # Skip variables with very few records
            if var.num_records < 2:
                continue

            col_names, data_cols, actual_records = _expand_variable_to_columns(
                var, cdf_file_path, max_records
            )
            col_names = _make_unique_column_names(col_names)

            base_filename = _generate_output_filename(filename_template, cdf_file_path, var.name)

            # Get unique filename (add numerical suffix if needed)
            output_filename = _get_unique_filename(base_filename, used_filenames)
            used_filenames.add(output_filename)
            output_path = output_dir / output_filename

            # Check for existing file
            if output_path.exists() and not append:
                raise FileExistsError(
                    f"Output file already exists: {output_path}. "
                    "Use --append to add data to existing file."
                )

            # Validate header if appending
            if (
                append
                and output_path.exists()
                and not _validate_existing_file_header(output_path, col_names)
            ):
                raise ValueError(
                    f"Cannot append to {output_path}: "
                    f"existing file has different columns. "
                    f"Expected columns: {', '.join(col_names)}"
                )

            # Write to file using tabular writer (format auto-detected from extension)
            write_append = append and output_path.exists()

            with create_writer(output_path, append=write_append) as writer:
                # Write header only if not appending
                if not write_append:
                    writer.writerow(col_names)

                # Transpose data to write rows
                for row_idx in range(actual_records):
                    row = [col[row_idx] for col in data_cols]
                    writer.writerow(row)

            file_size = output_path.stat().st_size
            results.append(
                ExtractionResult(
                    output_file=output_path,
                    num_rows=actual_records,
                    num_columns=len(col_names),
                    column_names=col_names,
                    file_size=file_size,
                    variable_names=[var.name],
                )
            )

    return results


def extract_cdf_with_config(
    cdf_file_path: Path,
    output_dir: Path,
    job: CrumpJob,
    max_records: int | None = None,
    automerge: bool = True,
    variable_names: list[str] | None = None,
    append: bool = False,
    filename_template: str = "[SOURCE_FILE]_[VARIABLE_NAME].csv",
    use_parquet: bool = False,
) -> list[ExtractionResult]:
    """Extract data from a CDF file to CSV/Parquet using job configuration for column selection and mapping.

    This function extracts CDF data and applies the same column mappings and transformations
    that would be used when syncing to a database, but outputs to CSV/Parquet instead.

    A CDF file may contain multiple groups of variables with different record counts, resulting
    in multiple output files. This function attempts to transform each one and returns results
    for those that successfully match the column mappings.

    Args:
        cdf_file_path: Path to the CDF file
        output_dir: Directory to write output CSV file(s)
        job: CrumpJob configuration with column mappings and transformations
        max_records: Maximum number of records to extract (None = all)
        automerge: Whether to merge variables with same record count during raw extraction
        variable_names: Specific variable names to extract (None = all)
        append: Whether to append to existing CSV files instead of overwriting
        filename_template: Template for output filenames (use [SOURCE_FILE] and [VARIABLE_NAME])

    Returns:
        List of ExtractionResult objects for successfully transformed CSVs (may be empty)

    Raises:
        ValueError: If CDF extraction fails completely or append header mismatch
        FileNotFoundError: If CDF file doesn't exist
        FileExistsError: If output file exists and append is False
    """
    # Step 1: Extract CDF to temporary CSV files (raw dump)
    temp_dir = Path(tempfile.mkdtemp(prefix="data_sync_extract_"))
    results = []

    try:
        raw_results = extract_cdf_to_tabular_file(
            cdf_file_path=cdf_file_path,
            output_dir=temp_dir,
            filename_template=f"{cdf_file_path.stem}_[VARIABLE_NAME].csv",
            automerge=automerge,
            append=False,
            variable_names=variable_names,
            max_records=max_records,
        )

        if not raw_results:
            raise ValueError("No data could be extracted from CDF file")

        # Step 2: Extract values from filename if configured
        filename_values = None
        if job.filename_to_column:
            filename_values = job.filename_to_column.extract_values_from_filename(cdf_file_path)

        # Step 3: Try to transform each extracted CSV
        for raw_result in raw_results:
            raw_csv_path = raw_result.output_file

            try:
                # Attempt to process this file with the job configuration
                result = _transform_tabular_file_with_config(
                    raw_file_path=raw_csv_path,
                    output_dir=output_dir,
                    cdf_file_path=cdf_file_path,
                    job=job,
                    filename_values=filename_values,
                    raw_result=raw_result,
                    append=append,
                    filename_template=filename_template,
                    use_parquet=use_parquet,
                )

                if result:
                    results.append(result)

            except ValueError:
                # This file doesn't match the column mappings - skip it silently
                # This is expected when a CDF has multiple variable groups
                pass

        return results

    finally:
        # Clean up temporary files
        try:
            for temp_file in temp_dir.glob("*.csv"):
                temp_file.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()
        except Exception:
            pass  # Best effort cleanup


def _transform_tabular_file_with_config(
    raw_file_path: Path,
    output_dir: Path,
    cdf_file_path: Path,
    job: CrumpJob,
    filename_values: dict[str, str] | None,
    raw_result: ExtractionResult,
    append: bool = False,
    filename_template: str = "[SOURCE_FILE]_[VARIABLE_NAME].csv",
    use_parquet: bool = False,  # noqa: ARG001  # Deprecated parameter kept for compatibility
) -> ExtractionResult | None:
    """Transform a raw tabular file using job configuration.

    Output format is auto-detected from the filename extension.

    Args:
        raw_file_path: Path to raw tabular file (CSV or Parquet)
        output_dir: Output directory for transformed output file
        cdf_file_path: Original CDF file path
        job: Job configuration
        filename_values: Extracted filename values
        raw_result: Result from raw extraction
        append: Whether to append to existing file
        filename_template: Template for output filename (extension determines format)
        use_parquet: Deprecated. Use filename extension instead.

    Returns:
        ExtractionResult if transformation succeeds, None if file doesn't match mappings

    Raises:
        ValueError: If required columns are missing from file or append header mismatch
        FileExistsError: If output file exists and append is False
    """
    with open(raw_file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return None

        csv_columns = set(reader.fieldnames)

        # Determine which columns to include in output
        output_columns = []
        sync_columns = []

        # Add ID columns
        for id_col in job.id_mapping:
            if id_col.expression or id_col.function:
                # Custom function for ID
                sync_columns.append(id_col)
                output_columns.append(id_col.db_column)
            elif id_col.csv_column and id_col.csv_column in csv_columns:
                sync_columns.append(id_col)
                output_columns.append(id_col.db_column)
            else:
                raise ValueError(
                    f"ID column '{id_col.csv_column}' not found in CSV. "
                    f"Available columns: {', '.join(sorted(csv_columns))}"
                )

        # Add data columns
        if job.columns:
            for col in job.columns:
                if col.expression or col.function:
                    # Custom function - always include
                    sync_columns.append(col)
                    output_columns.append(col.db_column)
                elif col.csv_column and col.csv_column in csv_columns:
                    sync_columns.append(col)
                    output_columns.append(col.db_column)
                elif col.csv_column:
                    # Column specified but not found - skip silently
                    pass
        else:
            # No columns specified - include all columns from CSV
            for csv_col in sorted(csv_columns):
                # Check if this column is already in id_mapping
                if not any(
                    id_col.csv_column == csv_col for id_col in job.id_mapping if id_col.csv_column
                ):
                    # Import ColumnMapping here to avoid circular import
                    from crump.config import ColumnMapping

                    col_mapping = ColumnMapping(csv_column=csv_col, db_column=csv_col)
                    sync_columns.append(col_mapping)
                    output_columns.append(csv_col)

        # Add filename-extracted columns if configured
        if filename_values and job.filename_to_column:
            for col_name, filename_col_mapping in job.filename_to_column.columns.items():
                if col_name in filename_values:
                    output_columns.append(filename_col_mapping.db_column)

        # If no columns to output, skip this CSV
        if not output_columns:
            return None

        # Generate output filename using template
        # Replace [SOURCE_FILE] with CDF filename stem
        # Replace [VARIABLE_NAME] with first variable name or joined names
        output_filename = filename_template.replace("[SOURCE_FILE]", cdf_file_path.stem)

        if "[VARIABLE_NAME]" in output_filename:
            # Use variable names from raw result
            if len(raw_result.variable_names) == 1:
                var_name = raw_result.variable_names[0]
            else:
                # Multiple variables - use first 2 + count
                var_name = "_".join(raw_result.variable_names[:2])
                if len(raw_result.variable_names) > 2:
                    var_name += f"_plus{len(raw_result.variable_names) - 2}"
            output_filename = output_filename.replace("[VARIABLE_NAME]", var_name)

        output_path = output_dir / output_filename

        # Process rows and write output file
        output_dir.mkdir(parents=True, exist_ok=True)

        # Check if we're appending and validate headers
        if append and output_path.exists():
            # Validate that existing file has same columns
            if not _validate_existing_file_header(output_path, output_columns):
                raise ValueError(
                    f"Cannot append to {output_path.name}: "
                    f"existing file has different columns. "
                    f"Expected: {output_columns}"
                )
        elif not append and output_path.exists():
            # File exists and we're not appending - error
            raise FileExistsError(
                f"Output file already exists: {output_path}. "
                f"Use --append to add to existing file or remove it first."
            )

        rows_written = 0

        # Reset reader to beginning
        f.seek(0)
        reader = csv.DictReader(f)

        # Write using tabular file writer (format auto-detected from extension)
        write_append = append and output_path.exists()
        with create_writer(output_path, append=write_append) as writer:
            # Write header only if not appending
            if not write_append:
                writer.writerow(output_columns)

            for row in reader:
                # Apply column transformations
                output_row = apply_row_transformations(
                    row, sync_columns, job.filename_to_column, filename_values
                )

                # Skip row if completely empty (all transformations produced None/empty)
                if not any(output_row.values()):
                    continue

                # Convert dict to list in column order
                row_list = [output_row.get(col, "") for col in output_columns]
                writer.writerow(row_list)
                rows_written += 1

        # Only return result if we wrote at least one row
        if rows_written == 0 and not write_append:
            output_path.unlink()  # Clean up empty file (only if we created it)
            return None

        file_size = output_path.stat().st_size

        return ExtractionResult(
            output_file=output_path,
            num_rows=rows_written,
            num_columns=len(output_columns),
            column_names=output_columns,
            file_size=file_size,
            variable_names=raw_result.variable_names,
        )
