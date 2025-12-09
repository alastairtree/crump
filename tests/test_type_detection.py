"""Tests for type detection module."""

import csv
from pathlib import Path

from crump.type_detection import (
    analyze_tabular_file_types,
    detect_column_type,
    suggest_id_column,
)


class TestDetectColumnType:
    """Test suite for detect_column_type function."""

    def test_detect_integer(self) -> None:
        """Test detection of integer values."""
        values = ["1", "2", "3", "100", "-5"]
        assert detect_column_type(values) == "integer"

    def test_detect_bigint(self) -> None:
        """Test detection of bigint values (large integers)."""
        values = ["815230591184000000", "999999999999999", "-999999999999999"]
        assert detect_column_type(values) == "bigint"

    def test_detect_bigint_example_value(self) -> None:
        """Test detection of the specific example bigint value."""
        values = ["815230591184000000"]
        assert detect_column_type(values) == "bigint"

    def test_integer_at_max_range(self) -> None:
        """Test that values at INTEGER max range are still detected as integer."""
        # PostgreSQL INTEGER max: 2147483647
        values = ["2147483647", "2147483646", "-2147483648"]
        assert detect_column_type(values) == "integer"

    def test_bigint_just_over_integer_range(self) -> None:
        """Test that values just over INTEGER range are detected as bigint."""
        # Just over PostgreSQL INTEGER max
        values = ["2147483648", "-2147483649"]
        assert detect_column_type(values) == "bigint"

    def test_mixed_integer_and_bigint(self) -> None:
        """Test that mixed small and large integers are detected as bigint."""
        # Mix of regular integers and bigints - should be classified as bigint
        values = ["1", "100", "815230591184000000", "42"]
        assert detect_column_type(values) == "bigint"

    def test_mixed_with_bigint_at_end(self) -> None:
        """Test bigint detection when large value appears later in the data."""
        # Bigint value at the end - should still be detected
        values = ["1", "2", "3", "4", "5", "999999999999999999"]
        assert detect_column_type(values) == "bigint"

    def test_mixed_bigint_integer_and_text(self) -> None:
        """Test that mixed bigint, integer, and text values are detected as text/varchar."""
        # Mix of bigint, integer, and text - should NOT be bigint, should be text
        values = ["815230591184000000", "100", "hello", "42"]
        result = detect_column_type(values)
        # Should be text or varchar, NOT bigint or integer
        assert result == "text" or result.startswith("varchar(")

    def test_mixed_integer_and_text(self) -> None:
        """Test that mixed integer and text values are detected as text/varchar."""
        # Mix of integer and text - should NOT be integer, should be text
        values = ["1", "100", "abc", "42"]
        result = detect_column_type(values)
        # Should be text or varchar, NOT integer
        assert result == "text" or result.startswith("varchar(")

    def test_mixed_bigint_at_start_with_text(self) -> None:
        """Test that bigint at start with text later is detected as text/varchar."""
        # Bigint first, then text - should be text/varchar
        values = ["999999999999999999", "test", "100"]
        result = detect_column_type(values)
        assert result == "text" or result.startswith("varchar(")

    def test_detect_float(self) -> None:
        """Test detection of float values."""
        values = ["1.5", "2.3", "3.14", "100.0", "-5.5"]
        assert detect_column_type(values) == "float"

    def test_detect_date(self) -> None:
        """Test detection of date values."""
        values = ["2024-01-15", "2024-02-20", "2023-12-31"]
        assert detect_column_type(values) == "date"

    def test_detect_datetime(self) -> None:
        """Test detection of datetime values."""
        values = ["2024-01-15 10:30:00", "2024-02-20 14:45:30"]
        assert detect_column_type(values) == "datetime"

    def test_detect_varchar(self) -> None:
        """Test detection of short text (varchar)."""
        values = ["Alice", "Bob", "Charlie"]
        result = detect_column_type(values)
        assert result.startswith("varchar(")

    def test_detect_text(self) -> None:
        """Test detection of long text."""
        values = ["This is a very long text" * 20]
        assert detect_column_type(values) == "text"

    def test_empty_values(self) -> None:
        """Test with empty values."""
        assert detect_column_type([]) == "text"
        assert detect_column_type([""]) == "text"
        assert detect_column_type(["", "", ""]) == "text"

    def test_mixed_integers_and_floats(self) -> None:
        """Test that mixed integers and floats are detected as float."""
        values = ["1", "2.5", "3", "4.7"]
        assert detect_column_type(values) == "float"


class TestSuggestIdColumn:
    """Test suite for suggest_id_column function."""

    def test_suggest_id(self) -> None:
        """Test suggesting column named 'id'."""
        columns = ["name", "id", "value"]
        assert suggest_id_column(columns) == "id"

    def test_suggest_uuid(self) -> None:
        """Test suggesting column named 'uuid'."""
        columns = ["name", "uuid", "value"]
        assert suggest_id_column(columns) == "uuid"

    def test_suggest_with_id_suffix(self) -> None:
        """Test suggesting column ending with '_id'."""
        columns = ["name", "user_id", "value"]
        assert suggest_id_column(columns) == "user_id"

    def test_suggest_first_column(self) -> None:
        """Test default to first column if no ID-like column found."""
        columns = ["name", "value", "description"]
        assert suggest_id_column(columns) == "name"

    def test_case_insensitive(self) -> None:
        """Test that ID detection is case insensitive."""
        columns = ["Name", "ID", "Value"]
        assert suggest_id_column(columns) == "ID"

    def test_custom_matchers(self) -> None:
        """Test using custom ID column matchers."""
        columns = ["customer_id", "name", "value"]
        matchers = ["customer_id", "account_id"]
        assert suggest_id_column(columns, matchers) == "customer_id"

    def test_custom_matchers_priority(self) -> None:
        """Test that custom matchers respect priority order."""
        columns = ["account_id", "customer_id", "name"]
        matchers = ["customer_id", "account_id"]
        # customer_id should be chosen because it appears first in matchers
        assert suggest_id_column(columns, matchers) == "customer_id"

    def test_custom_matchers_no_match(self) -> None:
        """Test custom matchers fallback to first column when no match."""
        columns = ["name", "value", "description"]
        matchers = ["customer_id", "account_id"]
        # No match found, should default to first column
        assert suggest_id_column(columns, matchers) == "name"

    def test_custom_matchers_no_suffix_check(self) -> None:
        """Test that custom matchers don't check for _id suffix."""
        columns = ["name", "user_id", "value"]
        matchers = ["customer_id"]
        # With custom matchers, _id suffix shouldn't be checked
        # Should default to first column since customer_id not found
        assert suggest_id_column(columns, matchers) == "name"

    def test_default_matchers_still_check_suffix(self) -> None:
        """Test that default matchers still check for _id suffix."""
        columns = ["name", "user_id", "value"]
        # No custom matchers, should use default logic including _id suffix
        assert suggest_id_column(columns) == "user_id"

    def test_default_matchers_handle_science_files(self) -> None:
        columns = ["val_x", "thing_y", "epoch"]
        # No custom matchers, should use default logic including _id suffix
        assert suggest_id_column(columns) == "epoch"


class TestAnalyzeCsvTypes:
    """Test suite for analyze_csv_types function."""

    def test_analyze_simple_csv(self, tmp_path: Path) -> None:
        """Test analyzing a simple CSV file."""
        csv_file = tmp_path / "test.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name", "age", "price"])
            writer.writeheader()
            writer.writerow({"id": "1", "name": "Alice", "age": "25", "price": "19.99"})
            writer.writerow({"id": "2", "name": "Bob", "age": "30", "price": "29.99"})

        types = analyze_tabular_file_types(csv_file)

        assert types["id"] == "integer"
        assert types["name"].startswith("varchar(")
        assert types["age"] == "integer"
        assert types["price"] == "float"

    def test_analyze_empty_csv(self, tmp_path: Path) -> None:
        """Test analyzing an empty CSV file."""
        csv_file = tmp_path / "empty.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name"])
            writer.writeheader()

        types = analyze_tabular_file_types(csv_file)

        # Empty columns should default to text
        assert types["id"] == "text"
        assert types["name"] == "text"

    def test_analyze_with_nulls(self, tmp_path: Path) -> None:
        """Test analyzing CSV with NULL/empty values."""
        csv_file = tmp_path / "nulls.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "value": "10"})
            writer.writerow({"id": "2", "value": ""})
            writer.writerow({"id": "3", "value": "20"})

        types = analyze_tabular_file_types(csv_file)

        assert types["id"] == "integer"
        assert types["value"] == "integer"  # Should ignore empty values
