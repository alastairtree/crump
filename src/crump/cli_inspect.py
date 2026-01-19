"""Inspect command for examining CSV and CDF files."""

from __future__ import annotations

from pathlib import Path

import click
import numpy as np
from rich.console import Console
from rich.table import Table

from crump.tabular_file import create_reader

console = Console()

# Constants
MAX_COLUMNS_TO_DISPLAY = 10
MAX_VALUE_LENGTH = 80


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted file size string
    """
    size: float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def inspect_tabular(file_path: Path, num_records: int) -> None:
    """Inspect a tabular file (CSV or Parquet) and display summary information.

    Args:
        file_path: Path to the tabular file
        num_records: Number of sample records to display

    Raises:
        click.ClickException: If the file cannot be read or parsed
    """
    # Detect file type for display
    from crump.file_types import InputFileType

    try:
        detected_type = InputFileType.from_path(str(file_path))
        file_type = "Parquet" if detected_type == InputFileType.PARQUET else "CSV"
    except ValueError:
        file_type = "CSV"  # Default to CSV for unknown extensions

    console.print(f"\n[bold cyan]{file_type} File: {file_path.name}[/bold cyan]")
    console.print(f"[dim]Path: {file_path}[/dim]")

    # Get file size
    try:
        file_size = file_path.stat().st_size
        console.print(f"[dim]Size: {format_file_size(file_size)}[/dim]\n")
    except OSError as e:
        raise click.ClickException(f"Cannot access file: {e}") from e

    try:
        # Get total row count efficiently for Parquet files
        total_rows = None
        if file_type == "Parquet":
            try:
                import pyarrow.parquet as pq  # type: ignore[import-untyped]

                parquet_file = pq.ParquetFile(file_path)
                total_rows = parquet_file.metadata.num_rows
            except Exception:
                # If we can't get metadata, we'll count while reading
                pass

        with create_reader(file_path) as reader:
            if not reader.fieldnames:
                console.print(f"[red]Error: No columns found in {file_type} file[/red]")
                return

            # Display header
            console.print(f"[bold]Columns ({len(reader.fieldnames)}):[/bold]")
            console.print(f"  {', '.join(reader.fieldnames)}\n")

            # Create table for sample records
            table = Table(title=f"Sample Records (first {num_records})")
            for col in reader.fieldnames:
                table.add_column(col, style="cyan", overflow="fold")

            # Read and display only the sample records we need
            rows_read = 0
            for i, row in enumerate(reader):
                if i < num_records:
                    # Convert all values to strings for display
                    row_values = [str(row.get(col, "")) for col in reader.fieldnames]
                    table.add_row(*row_values)
                    rows_read += 1
                else:
                    # If we already have the total from Parquet metadata, stop reading
                    if total_rows is not None:
                        break
                    # Otherwise, just count remaining rows without storing them
                    rows_read += 1

            # If we didn't get total from metadata, use what we counted
            if total_rows is None:
                total_rows = rows_read

            console.print(table)

            # Display summary
            console.print(
                f"\n[green]Summary: {total_rows:,} rows total, "
                f"{len(reader.fieldnames)} columns, {format_file_size(file_size)}[/green]"
            )

    except Exception as e:
        raise click.ClickException(f"Unexpected error reading {file_type} file: {e}") from e


def _format_attribute_value(attr_values: object) -> str:
    """Format CDF attribute value for display.

    Args:
        attr_values: Attribute value(s) to format

    Returns:
        Formatted string representation
    """
    if isinstance(attr_values, list) and len(attr_values) == 1:
        value_str = str(attr_values[0])
    elif isinstance(attr_values, list) and len(attr_values) > 1:
        value_str = f"{attr_values[0]} (+ {len(attr_values) - 1} more)"
    else:
        value_str = str(attr_values)

    # Truncate long values
    if len(value_str) > MAX_VALUE_LENGTH:
        value_str = value_str[: MAX_VALUE_LENGTH - 3] + "..."

    return value_str


def _format_data_value(value: object, is_numeric: bool = False) -> str:
    """Format a data value for display.

    Args:
        value: The value to format
        is_numeric: Whether the value is numeric

    Returns:
        Formatted string representation
    """
    if is_numeric:
        try:
            return f"{float(str(value)):.4g}"
        except (ValueError, TypeError):
            return str(value)
    return str(value)


def inspect_cdf(file_path: Path, num_records: int) -> None:
    """Inspect a CDF file and display summary information.

    Args:
        file_path: Path to the CDF file
        num_records: Number of sample records to display per variable

    Raises:
        click.ClickException: If the file cannot be read or parsed
    """
    try:
        import cdflib  # type: ignore[import-untyped]
    except ImportError:
        console.print(
            "[red]Error: cdflib is not installed. Install it with: pip install cdflib[/red]"
        )
        raise click.ClickException("cdflib is required for CDF file inspection") from None

    console.print(f"\n[bold cyan]CDF File: {file_path.name}[/bold cyan]")
    console.print(f"[dim]Path: {file_path}[/dim]")

    # Get file size
    try:
        file_size = file_path.stat().st_size
        console.print(f"[dim]Size: {format_file_size(file_size)}[/dim]\n")
    except OSError as e:
        raise click.ClickException(f"Cannot access file: {e}") from e

    try:
        # Read variables using our reader to get EPOCH conversion
        from crump.cdf_reader import read_cdf_variables

        cdf_variables = read_cdf_variables(file_path)

        with cdflib.CDF(str(file_path)) as cdf:
            # Get CDF info
            info = cdf.cdf_info()
            console.print(f"[bold]CDF Version:[/bold] {info.Version}")
            console.print(f"[bold]Encoding:[/bold] {info.Encoding}")
            console.print(f"[bold]Majority:[/bold] {info.Majority}\n")

            # Display global attributes
            console.print("[bold]Global Attributes:[/bold]")
            global_attrs = cdf.globalattsget()
            attr_table = Table(show_header=True, box=None, padding=(0, 1))
            attr_table.add_column("Attribute", style="yellow")
            attr_table.add_column("Value", style="dim")

            for attr_name, attr_values in sorted(global_attrs.items()):
                value_str = _format_attribute_value(attr_values)
                attr_table.add_row(attr_name, value_str)

            console.print(attr_table)

            # Get all variables using the converted data
            var_info_list = []
            for var in cdf_variables:
                var_info_list.append((var.name, var.data, var.num_records))

            # Sort by number of records (descending)
            var_info_list.sort(key=lambda x: x[2], reverse=True)

            # Display variable summary
            console.print(f"\n[bold]Variables ({len(var_info_list)}):[/bold]")
            var_summary_table = Table(show_header=True)
            var_summary_table.add_column("Variable", style="cyan")
            var_summary_table.add_column("Type", style="yellow")
            var_summary_table.add_column("Shape", style="green")
            var_summary_table.add_column("Records", style="magenta", justify="right")

            for var_name, data, num_recs in var_info_list:
                if isinstance(data, np.ndarray):
                    dtype_str = str(data.dtype)
                    shape_str = str(data.shape)
                else:
                    dtype_str = type(data).__name__
                    shape_str = "scalar"

                var_summary_table.add_row(var_name, dtype_str, shape_str, f"{num_recs:,}")

            console.print(var_summary_table)

            # Display detailed information for each variable with sample data
            console.print("\n[bold]Variable Details (sorted by record count):[/bold]\n")

            for var_name, data, num_recs in var_info_list:
                console.print(f"[bold cyan]{var_name}[/bold cyan]")

                # Get variable attributes
                try:
                    var_attrs = cdf.varattsget(var_name)
                except Exception:
                    var_attrs = {}

                # Show key attributes
                if var_attrs:
                    attr_lines = []
                    for key in ["FIELDNAM", "CATDESC", "UNITS", "VAR_TYPE"]:
                        if key in var_attrs:
                            attr_lines.append(f"{key}: {var_attrs[key]}")
                    if attr_lines:
                        console.print(f"  [dim]{' | '.join(attr_lines)}[/dim]")

                # Show data structure
                if isinstance(data, np.ndarray):
                    console.print(
                        f"  Shape: {data.shape} | Type: {data.dtype} | Records: {num_recs:,}"
                    )

                    # Create table for sample data
                    if len(data.shape) == 1:
                        # 1D array - show as single column
                        sample_table = Table(show_header=True, box=None, padding=(0, 1))
                        sample_table.add_column("Index", style="dim", justify="right")
                        sample_table.add_column("Value")

                        for i in range(min(num_records, num_recs)):
                            sample_table.add_row(str(i), str(data[i]))

                        console.print(sample_table)

                        if num_recs > num_records:
                            console.print(
                                f"  [dim]... {num_recs - num_records:,} more records[/dim]"
                            )

                    elif len(data.shape) == 2:
                        # 2D array - show as table with columns
                        sample_table = Table(show_header=True, box=None, padding=(0, 1))
                        sample_table.add_column("Index", style="dim", justify="right")

                        # Add columns for each component
                        num_cols_to_show = min(data.shape[1], MAX_COLUMNS_TO_DISPLAY)
                        for col_idx in range(num_cols_to_show):
                            sample_table.add_column(f"[{col_idx}]")

                        if data.shape[1] > MAX_COLUMNS_TO_DISPLAY:
                            sample_table.add_column("...")

                        for i in range(min(num_records, num_recs)):
                            row_values = [str(i)]
                            for col_idx in range(num_cols_to_show):
                                row_values.append(
                                    _format_data_value(data[i, col_idx], is_numeric=True)
                                )
                            if data.shape[1] > MAX_COLUMNS_TO_DISPLAY:
                                row_values.append("...")
                            sample_table.add_row(*row_values)

                        console.print(sample_table)

                        if num_recs > num_records:
                            console.print(
                                f"  [dim]... {num_recs - num_records:,} more records[/dim]"
                            )

                    elif len(data.shape) > 2:
                        # Multi-dimensional - just show shape info
                        console.print(f"  [dim]Multi-dimensional data: {data.shape}[/dim]")
                        if num_recs > 0:
                            console.print(f"  [dim]First record shape: {data[0].shape}[/dim]")
                            console.print(
                                f"  [dim]Sample value: {str(data[0].flatten()[:5])}...[/dim]"
                            )

                    # Show value range for numeric data
                    if np.issubdtype(data.dtype, np.number) and num_recs > 0:
                        try:
                            flat_data = data.flatten()
                            if not np.all(np.isnan(flat_data)):
                                valid_data = flat_data[~np.isnan(flat_data)]
                                if len(valid_data) > 0:
                                    console.print(
                                        f"  [dim]Value range: [{np.min(valid_data):.4g}, "
                                        f"{np.max(valid_data):.4g}][/dim]"
                                    )
                        except Exception:
                            # Silently skip if we can't compute range
                            pass
                else:
                    console.print(f"  Type: {type(data).__name__} | Value: {data}")

                console.print()  # Blank line between variables

    except Exception as e:
        raise click.ClickException(f"Error reading CDF file: {e}") from e


@click.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True)
@click.option(
    "--max-records",
    "-n",
    type=int,
    default=10,
    help="Number of sample records to display (default: 10)",
)
def inspect(files: tuple[Path, ...], max_records: int) -> None:
    """Inspect CSV, Parquet, or CDF files and display summary information.

    Displays file metadata, structure, and sample data for each file.
    Supports CSV, Parquet, and CDF file formats.

    Arguments:
        FILES: One or more file paths to inspect

    Examples:
        # Inspect a single CSV file
        crump inspect data.csv

        # Inspect a Parquet file
        crump inspect data.parquet

        # Inspect multiple files with custom record count
        crump inspect file1.csv file2.parquet file3.cdf --max-records 20

        # Inspect all CSV files in a directory
        crump inspect data/*.csv
    """
    try:
        from crump.file_types import InputFileType

        for file_path in files:
            # Determine file type and inspect
            try:
                file_type = InputFileType.from_path(str(file_path))

                if file_type in [InputFileType.CSV, InputFileType.PARQUET]:
                    inspect_tabular(file_path, max_records)
                elif file_type == InputFileType.CDF:
                    inspect_cdf(file_path, max_records)
                else:
                    console.print(
                        f"\n[yellow]Warning: Unsupported file type '{file_path.suffix}' "
                        f"for {file_path.name}[/yellow]"
                    )
            except ValueError:
                console.print(
                    f"\n[yellow]Warning: Unsupported file type '{file_path.suffix}' "
                    f"for {file_path.name}[/yellow]"
                )

            # Add separator between files if multiple
            if len(files) > 1:
                console.print("\n" + "=" * 80 + "\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort() from e
