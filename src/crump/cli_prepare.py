"""Prepare command for analyzing CSV files and generating config."""

import re
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from crump.cdf_extractor import extract_cdf_to_tabular_file
from crump.config import (
    ColumnMapping,
    CrumpConfig,
    CrumpJob,
    FilenameColumnMapping,
    FilenameToColumn,
    Index,
    IndexColumn,
)
from crump.console_utils import CHECKMARK
from crump.type_detection import analyze_tabular_file_types_and_nullable, suggest_id_column

console = Console()


def generate_job_name_from_filename(filename: str) -> str:
    """Generate a job name from a filename.

    Args:
        filename: The filename to convert (with or without extension)

    Returns:
        A cleaned job name

    Rules:
        - Strip file extension
        - Remove all numbers
        - Convert multiple underscores to single underscore
        - Convert multiple hyphens to single hyphen
        - Strip leading/trailing underscores and hyphens
        - Convert to lowercase

    Examples:
        >>> generate_job_name_from_filename("sales_data_2024.csv")
        'sales_data'
        >>> generate_job_name_from_filename("user__info__123.csv")
        'user_info'
        >>> generate_job_name_from_filename("test--file--456.csv")
        'test-file'
    """
    # Strip extension
    name = Path(filename).stem

    # Remove all numbers
    name = re.sub(r"\d+", "", name)

    # Convert multiple underscores to single
    name = re.sub(r"_+", "_", name)

    # Convert multiple hyphens to single
    name = re.sub(r"-+", "-", name)

    # Strip leading/trailing underscores and hyphens
    name = name.strip("_-")

    # Convert to lowercase
    name = name.lower()

    # If empty after cleaning, use a default
    if not name:
        name = "job"

    return name


def suggest_indexes(column_info: dict[str, tuple[str, bool]], id_column: str) -> list[Index]:
    """Suggest database indexes based on column types and names.

    Args:
        column_info: Dictionary mapping column names to (data_type, nullable) tuples
        id_column: Name of the ID column (to exclude from indexing)

    Returns:
        List of suggested Index objects

    Rules:
        - Date/datetime columns get descending indexes
        - Columns ending in '_id' or '_key' get ascending indexes
        - ID column is excluded (already a primary key)
    """
    indexes = []

    for col_name, (col_type, _nullable) in column_info.items():
        # Skip the ID column (it's already a primary key)
        if col_name == id_column:
            continue

        index_name = None
        order = None

        # Date/datetime columns get descending indexes
        if col_type in ("date", "datetime"):
            index_name = f"idx_{col_name}"
            order = "DESC"

        # Columns ending in _id or _key get ascending indexes
        elif col_name.lower().endswith("_id") or col_name.lower().endswith("_key"):
            index_name = f"idx_{col_name}"
            order = "ASC"

        # Create the index if we determined it should have one
        if index_name and order:
            indexes.append(
                Index(name=index_name, columns=[IndexColumn(column=col_name, order=order)])
            )

    return indexes


def detect_filename_patterns(filename: str) -> FilenameToColumn | None:
    """Detect common date patterns in filename and suggest filename_to_column mapping.

    Args:
        filename: The filename to analyze (with or without extension)

    Returns:
        FilenameToColumn object if patterns detected, None otherwise

    Detects patterns like:
        - YYYYMMDD (20241231)
        - YYYY-MM-DD (2024-12-31)
        - YYYY_MM_DD (2024_12_31)

    Examples:
        >>> detect_filename_patterns("data_20241231.csv")
        FilenameToColumn with date column
        >>> detect_filename_patterns("report_2024-12-31_v1.csv")
        FilenameToColumn with date and version columns
    """
    # Strip extension
    name = Path(filename).stem

    # Define date patterns to detect
    date_patterns = [
        # YYYYMMDD pattern
        (r"(\d{8})", "date", "YYYYMMDD", "date"),
        # YYYY-MM-DD pattern
        (r"(\d{4}-\d{2}-\d{2})", "date", "YYYY-MM-DD", "date"),
        # YYYY_MM_DD pattern
        (r"(\d{4}_\d{2}_\d{2})", "date", "YYYY_MM_DD", "date"),
    ]

    # Try to find a date pattern
    for pattern, _col_name, _pattern_desc, _col_type in date_patterns:
        match = re.search(pattern, name)
        if match:
            # Build a template from the filename
            # Replace the matched pattern with [date] placeholder
            template = name[: match.start()] + f"[{_col_name}]" + name[match.end() :]
            template += Path(filename).suffix  # Add extension back

            # Create the FilenameToColumn mapping
            columns = {
                _col_name: FilenameColumnMapping(
                    name=_col_name,
                    db_column="file_date",
                    data_type=_col_type,
                    use_to_delete_old_rows=True,
                )
            }

            return FilenameToColumn(columns=columns, template=template)

    return None


def _create_column_mappings(
    columns: list[str],
    id_column: str,
    column_info: dict[str, tuple[str, bool]],
) -> list[ColumnMapping]:
    """Create column mappings for non-ID columns.

    Args:
        columns: List of all column names
        id_column: Name of the ID column to exclude
        column_info: Dictionary mapping column names to (data_type, nullable) tuples

    Returns:
        List of ColumnMapping objects for non-ID columns
    """
    column_mappings = []
    for col in columns:
        if col != id_column:
            col_type, nullable = column_info[col]
            column_mappings.append(
                ColumnMapping(csv_column=col, db_column=col, data_type=col_type, nullable=nullable)
            )
    return column_mappings


def _extract_cdf_to_temp_tabular_files(
    cdf_file: Path, temp_dir: Path, max_records: int = 50
) -> list[Path]:
    """Extract CDF file to temporary tabular files (CSV).

    Args:
        cdf_file: Path to the CDF file
        temp_dir: Temporary directory to store files
        max_records: Maximum number of records to extract (default: 50)

    Returns:
        List of paths to temporary files created

    Raises:
        ValueError: If CDF extraction fails
    """
    console.print(f"[cyan]Extracting data from CDF file: {cdf_file.name}[/cyan]")
    console.print(f"[dim]  Extracting first {max_records} records from each variable...[/dim]")

    try:
        # Extract with automerge enabled to group variables by record count
        results = extract_cdf_to_tabular_file(
            cdf_file_path=cdf_file,
            output_dir=temp_dir,
            filename_template=f"{cdf_file.stem}_[VARIABLE_NAME].csv",
            automerge=True,
            append=False,
            variable_names=None,
            max_records=max_records,
        )

        if not results:
            console.print(
                "[yellow]  No data extracted from CDF file (no suitable variables)[/yellow]"
            )
            return []

        # Display extraction summary
        console.print(f"[green]  Extracted {len(results)} CSV file(s) from CDF[/green]")
        for result in results:
            console.print(
                f"[dim]    - {result.output_file.name}: "
                f"{result.num_rows} rows, {result.num_columns} columns[/dim]"
            )

        return [result.output_file for result in results]

    except Exception as e:
        raise ValueError(f"Failed to extract CDF file: {e}") from e


def _display_prepare_results(
    job: CrumpJob,
    config: Path,
    id_column: str,
    column_info: dict[str, tuple[str, bool]],
    column_mappings: list[ColumnMapping],
    suggested_indexes: list[Index],
) -> None:
    """Display the results of the prepare command.

    Args:
        job: The created CrumpJob
        config: Path to config file
        id_column: Name of the ID column
        column_info: Dictionary mapping column names to (data_type, nullable) tuples
        column_mappings: List of column mappings (excluding ID)
        suggested_indexes: List of suggested indexes
    """
    console.print(f"[green]{CHECKMARK} Job configuration created successfully![/green]")
    console.print(f"[dim]  Config file: {config}[/dim]")
    console.print(f"[dim]  Job name: {job.name}[/dim]")
    console.print(f"[dim]  Target table: {job.target_table}[/dim]")

    # Display column mappings in a table
    table = Table(title="Column Mappings")
    table.add_column("CSV Column", style="cyan")
    table.add_column("DB Column", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Nullable", style="magenta")

    # Add ID mapping
    id_type, id_nullable = column_info[id_column]
    nullable_str = "NULL" if id_nullable else "NOT NULL"
    table.add_row(id_column, "id", id_type + " (ID)", nullable_str)

    # Add other columns
    for col_mapping in column_mappings:
        nullable_str = "NULL" if col_mapping.nullable else "NOT NULL"
        table.add_row(
            col_mapping.csv_column,
            col_mapping.db_column,
            col_mapping.data_type or "text",
            nullable_str,
        )

    console.print(table)

    # Display suggested indexes if any
    if suggested_indexes:
        index_table = Table(title="Suggested Indexes")
        index_table.add_column("Index Name", style="cyan")
        index_table.add_column("Column", style="green")
        index_table.add_column("Order", style="yellow")

        for index in suggested_indexes:
            for idx_col in index.columns:
                index_table.add_row(index.name, idx_col.column, idx_col.order)

        console.print(index_table)

    console.print("[dim]Review the configuration and adjust as needed before syncing.[/dim]")


@click.command()
@click.argument("file_paths", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option(
    "--config",
    "-c",
    "config",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to the YAML configuration file",
)
@click.option(
    "--job",
    "-j",
    "job",
    type=str,
    default=None,
    help="Name of the job to create (auto-generated from filename if not provided)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite job if it already exists in config",
)
def prepare(file_paths: tuple[Path, ...], config: Path, job: str | None, force: bool) -> None:
    """Prepare config entries by analyzing CSV and CDF files.

    Analyzes CSV and CDF files to detect column names and data types, then generates
    configuration entries. Each CSV file creates one job in the config file.
    For CDF files, each variable group (grouped by record count) creates one job.
    If job name is not provided, it will be auto-generated from the filename.

    Arguments:
        FILE_PATHS: One or more CSV or CDF files to analyze (required)

    Options:
        --config, -c: Path to the YAML configuration file (required)
        --job, -j: Name of the job to create (optional - auto-generated from filename if not provided)
        --force, -f: Overwrite job if it already exists in config

    Examples:
        # Create job config with auto-generated name
        crump prepare data.csv --config crump_config.yml

        # Process a CDF file (creates multiple jobs, one per variable group)
        crump prepare data.cdf --config crump_config.yml

        # Create job config with custom name
        crump prepare data.csv --config crump_config.yml --job my_job

        # Process multiple CSV files (auto-generates job names)
        crump prepare file1.csv file2.csv file3.csv --config crump_config.yml

        # Process multiple files with glob pattern (CSV and CDF supported)
        crump prepare data/*.csv data/*.cdf -c crump_config.yml

        # Overwrite existing job config
        crump prepare data.csv -c crump_config.yml -j my_job --force
    """
    temp_dir: Path | None = None
    temp_csv_files: list[Path] = []

    try:
        from crump.file_types import InputFileType

        # Separate CSV and CDF files using InputFileType
        csv_files = []
        cdf_files = []
        unsupported_files = []

        for f in file_paths:
            try:
                file_type = InputFileType.from_path(str(f))
                if file_type == InputFileType.CSV:
                    csv_files.append(f)
                elif file_type == InputFileType.CDF:
                    cdf_files.append(f)
                else:
                    unsupported_files.append(f)
            except ValueError:
                unsupported_files.append(f)

        # Warn about unsupported files
        if unsupported_files:
            for f in unsupported_files:
                console.print(
                    f"[yellow]Warning: Unsupported file type '{f.suffix}' for {f.name}. "
                    "Only .csv and .cdf files are supported.[/yellow]"
                )

        # Validate: if job name provided, only one file allowed
        if job and len(file_paths) > 1:
            console.print(
                "[red]Error:[/red] Cannot specify job name when processing multiple files. "
                "Job names will be auto-generated from filenames."
            )
            raise click.Abort()

        # Validate: if job name provided with CDF file, warn user
        if job and cdf_files:
            console.print(
                "[yellow]Warning:[/yellow] Custom job name will be ignored for CDF files. "
                "Job names will be auto-generated from variable names."
            )

        # Extract CDF files to temporary CSV files
        if cdf_files:
            console.print(f"\n[bold]Processing {len(cdf_files)} CDF file(s)...[/bold]\n")
            temp_dir = Path(tempfile.mkdtemp(prefix="data_sync_cdf_"))

            for cdf_file in cdf_files:
                try:
                    extracted_csvs = _extract_cdf_to_temp_tabular_files(
                        cdf_file, temp_dir, max_records=50
                    )
                    temp_csv_files.extend(extracted_csvs)
                    console.print(
                        f"[green]{CHECKMARK} CDF extraction complete: {cdf_file.name}[/green]\n"
                    )
                except ValueError as e:
                    console.print(f"[red]Error extracting {cdf_file.name}:[/red] {e}\n")
                    if len(file_paths) == 1:
                        raise click.Abort() from e
                    continue

        # Combine original CSV files with extracted temp CSV files
        all_csv_files = csv_files + temp_csv_files

        if not all_csv_files:
            console.print("[yellow]No CSV files to process[/yellow]")
            return

        # Display summary of files to process
        if temp_csv_files:
            console.print(
                f"\n[bold]Processing {len(all_csv_files)} CSV file(s) "
                f"({len(csv_files)} original, {len(temp_csv_files)} from CDF)...[/bold]\n"
            )

        # Load or create config once (used for all files)
        crump_config = CrumpConfig.from_yaml(config) if config.exists() else CrumpConfig(jobs={})

        jobs_created = 0
        jobs_updated = 0

        # Process each CSV file
        for file_path in all_csv_files:
            # Determine job name
            job_name = job or generate_job_name_from_filename(file_path.name)

            console.print(f"\n[cyan]Analyzing {file_path.name}...[/cyan]")
            console.print(f"[dim]  Job name: {job_name}[/dim]")

            # Analyze CSV file to detect types and nullable status
            column_info = analyze_tabular_file_types_and_nullable(file_path)

            if not column_info:
                console.print("[red]Error:[/red] No columns found in CSV file")
                continue

            columns = list(column_info.keys())
            console.print(f"[dim]  Found {len(columns)} columns[/dim]")

            # Suggest ID column using matchers from config if available
            id_column = suggest_id_column(columns, crump_config.id_column_matchers)
            console.print(f"[dim]  Suggested ID column: {id_column}[/dim]")

            # Create column mappings and suggest indexes
            column_mappings = _create_column_mappings(columns, id_column, column_info)
            suggested_indexes = suggest_indexes(column_info, id_column)
            console.print(f"[dim]  Suggested {len(suggested_indexes)} index(es)[/dim]")

            # Detect filename patterns and suggest filename_to_column mapping
            filename_to_column = detect_filename_patterns(file_path.name)
            if filename_to_column:
                console.print("[dim]  Detected date pattern in filename[/dim]")
                console.print(f"[dim]    Template: {filename_to_column.template}[/dim]")

            # Create the job with ID mapping that includes nullable info
            id_type, id_nullable = column_info[id_column]
            new_job = CrumpJob(
                name=job_name,
                target_table=job_name,  # Use job name as table name
                id_mapping=[
                    ColumnMapping(
                        csv_column=id_column,
                        db_column="id",
                        data_type=id_type,
                        nullable=id_nullable,
                    )
                ],
                columns=column_mappings if column_mappings else None,
                filename_to_column=filename_to_column,
                indexes=suggested_indexes if suggested_indexes else None,
            )

            # Add or update job
            try:
                job_exists = job_name in crump_config.jobs
                crump_config.add_or_update_job(new_job, force=force)

                if job_exists:
                    jobs_updated += 1
                else:
                    jobs_created += 1

            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                console.print("[dim]Use --force to overwrite the existing job[/dim]")
                if len(file_paths) == 1:
                    raise click.Abort() from e
                continue

            # Display results for this file
            _display_prepare_results(
                new_job, config, id_column, column_info, column_mappings, suggested_indexes
            )

        # Save config once after processing all files
        if jobs_created > 0 or jobs_updated > 0:
            crump_config.save_to_yaml(config)
            console.print(f"\n[green]{CHECKMARK} Configuration saved to {config}[/green]")
            if jobs_created > 0:
                console.print(f"[dim]  Jobs created: {jobs_created}[/dim]")
            if jobs_updated > 0:
                console.print(f"[dim]  Jobs updated: {jobs_updated}[/dim]")
            if temp_csv_files:
                console.print(f"[dim]  CSV files extracted from CDF: {len(temp_csv_files)}[/dim]")
        else:
            console.print("\n[yellow]No jobs were created or updated[/yellow]")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort() from e
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort() from e
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise click.Abort() from e
    finally:
        # Clean up temporary files
        if temp_csv_files:
            console.print("\n[dim]Cleaning up temporary files...[/dim]")
            for temp_file in temp_csv_files:
                try:
                    temp_file.unlink()
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not delete {temp_file}: {e}[/yellow]")

        # Clean up temporary directory
        if temp_dir and temp_dir.exists():
            try:
                temp_dir.rmdir()
            except Exception as e:
                console.print(f"[yellow]Warning: Could not delete temp directory: {e}[/yellow]")
