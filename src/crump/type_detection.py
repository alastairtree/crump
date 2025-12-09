"""Type detection for CSV columns."""

import re
from pathlib import Path

from crump.tabular_file import create_reader


def detect_column_type(values: list[str]) -> str:
    """Detect the most appropriate data type for a column based on sample values.

    Args:
        values: List of string values from the column (excluding empty strings)

    Returns:
        Detected type: 'bigint', 'integer', 'float', 'date', 'datetime', 'text', or 'varchar(N)'
    """
    if not values:
        return "text"

    # Sample up to 1000 values for performance
    sample = values[:1000]
    non_empty = [v for v in sample if v.strip()]

    if not non_empty:
        return "text"

    # Check if ANY value is a bigint AND all values are numeric (integers)
    # This handles mixed cases where some values are small integers and some are large
    if any(_is_bigint(v) for v in non_empty) and all(_is_any_integer(v) for v in non_empty):
        return "bigint"

    # Check if all values are integers (within INTEGER range)
    if all(_is_integer(v) for v in non_empty):
        return "integer"

    # Check if all values are floats
    if all(_is_float(v) for v in non_empty):
        return "float"

    # Check if all values are dates
    if all(_is_date(v) for v in non_empty):
        return "date"

    # Check if all values are datetimes
    if all(_is_datetime(v) for v in non_empty):
        return "datetime"

    # Check if it's a short text field (could use varchar)
    max_length = max(len(v) for v in non_empty)
    if max_length <= 255:
        return f"varchar({max_length})"

    return "text"


def _is_integer(value: str) -> bool:
    """Check if a string represents an integer within PostgreSQL INTEGER range.

    PostgreSQL INTEGER range: -2147483648 to 2147483647 (-2^31 to 2^31-1)
    """
    try:
        int_val = int(value)
        # Check if value fits in PostgreSQL INTEGER range
        return -2147483648 <= int_val <= 2147483647
    except ValueError:
        return False


def _is_bigint(value: str) -> bool:
    """Check if a string represents a large integer that requires BIGINT.

    This checks if the value is an integer but exceeds the PostgreSQL INTEGER range.
    PostgreSQL BIGINT range: -9223372036854775808 to 9223372036854775807 (-2^63 to 2^63-1)
    """
    try:
        int_val = int(value)
        # Check if value exceeds INTEGER range but fits in BIGINT range
        return (int_val < -2147483648 or int_val > 2147483647) and (
            -9223372036854775808 <= int_val <= 9223372036854775807
        )
    except ValueError:
        return False


def _is_any_integer(value: str) -> bool:
    """Check if a string represents any integer (within INTEGER or BIGINT range).

    This returns True for both small integers and large integers.
    """
    try:
        int_val = int(value)
        # Check if value fits in BIGINT range
        return -9223372036854775808 <= int_val <= 9223372036854775807
    except ValueError:
        return False


def _is_float(value: str) -> bool:
    """Check if a string represents a float."""
    try:
        float(value)
        return True
    except ValueError:
        return False


def _is_date(value: str) -> bool:
    """Check if a string represents a date (YYYY-MM-DD format)."""
    # Common date patterns
    date_patterns = [
        r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
        r"^\d{4}/\d{2}/\d{2}$",  # YYYY/MM/DD
        r"^\d{2}-\d{2}-\d{4}$",  # DD-MM-YYYY
        r"^\d{2}/\d{2}/\d{4}$",  # DD/MM/YYYY or MM/DD/YYYY
    ]

    return any(re.match(pattern, value.strip()) for pattern in date_patterns)


def _is_datetime(value: str) -> bool:
    """Check if a string represents a datetime."""
    # Common datetime patterns
    datetime_patterns = [
        r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}",  # YYYY-MM-DD HH:MM:SS
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",  # ISO format
        r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}",  # MM/DD/YYYY HH:MM:SS
    ]

    return any(re.match(pattern, value.strip()) for pattern in datetime_patterns)


def detect_nullable(values: list[str], total_rows: int) -> bool:
    """Detect if a column should be nullable based on sample values.

    Args:
        values: List of non-empty string values from the column
        total_rows: Total number of rows in the CSV

    Returns:
        True if column has any empty/null values, False otherwise
    """
    # If we have fewer values than total rows, there are empty values
    return len(values) < total_rows


def analyze_tabular_file_types(file_path: Path) -> dict[str, str]:
    """Analyze a tabular file (CSV or Parquet) and detect data types for each column.

    Args:
        file_path: Path to the tabular file

    Returns:
        Dictionary mapping column names to detected types
    """
    column_values: dict[str, list[str]] = {}

    with create_reader(file_path) as reader:
        if not reader.fieldnames:
            return {}

        # Initialize empty lists for each column
        for col in reader.fieldnames:
            column_values[col] = []

        # Collect values for each column
        for row in reader:
            for col in reader.fieldnames:
                if col in row and row[col]:
                    column_values[col].append(str(row[col]))

    # Detect type for each column
    return {col: detect_column_type(values) for col, values in column_values.items()}


def analyze_tabular_file_types_and_nullable(file_path: Path) -> dict[str, tuple[str, bool]]:
    """Analyze a tabular file (CSV or Parquet) and detect data types and nullable status for each column.

    Args:
        file_path: Path to the tabular file

    Returns:
        Dictionary mapping column names to (data_type, nullable) tuples
    """
    column_values: dict[str, list[str]] = {}
    total_rows = 0

    with create_reader(file_path) as reader:
        if not reader.fieldnames:
            return {}

        # Initialize empty lists for each column
        for col in reader.fieldnames:
            column_values[col] = []

        # Collect values for each column and count total rows
        for row in reader:
            total_rows += 1
            for col in reader.fieldnames:
                if col in row and row[col]:
                    val_str = str(row[col]).strip()
                    if val_str:
                        column_values[col].append(val_str)

    # Detect type and nullable for each column
    result = {}
    for col, values in column_values.items():
        data_type = detect_column_type(values)
        nullable = detect_nullable(values, total_rows)
        result[col] = (data_type, nullable)

    return result


def suggest_id_column(columns: list[str], matchers: list[str] | None = None) -> str:
    """Suggest which column should be the ID column.

    Args:
        columns: List of column names
        matchers: Optional list of column name patterns to match (in priority order).
                 If None, uses default patterns: ['id', 'uuid', 'key', 'code']

    Returns:
        Name of suggested ID column
    """
    # Use provided matchers or default ones
    id_candidates = ["id", "uuid", "epoch", "key", "code"] if matchers is None else matchers

    # Check for exact matches
    lower_columns = {col.lower(): col for col in columns}
    for candidate in id_candidates:
        if candidate.lower() in lower_columns:
            return lower_columns[candidate.lower()]

    # Check for columns ending with _id (only if using default matchers)
    if matchers is None:
        for col in columns:
            if col.lower().endswith("_id"):
                return col

    # Default to first column
    return columns[0] if columns else "id"
