"""Configuration file handling for data_sync."""

from __future__ import annotations

import fnmatch
import importlib
import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


class DuplicateKeySafeLoader(yaml.SafeLoader):
    """Custom YAML loader that handles duplicate null keys by converting them to a list."""

    pass


def dict_constructor(loader: yaml.Loader, node: yaml.Node) -> dict[Any, Any]:
    """Custom dict constructor that preserves duplicate null keys in a list.

    When a dict has multiple entries with None (null/~) as the key, instead of
    overwriting them, collect them all in a list under the None key.
    """
    pairs = loader.construct_pairs(node)
    result: dict[Any, Any] = {}

    for key, value in pairs:
        if key is None and key in result:
            # Duplicate null key found
            if not isinstance(result[None], list):
                # Convert first occurrence to list
                result[None] = [result[None]]
            result[None].append(value)
        elif key is None and any(k is None for k, _ in pairs[: pairs.index((key, value))]):
            # This is not the first null key, skip (already handled above)
            continue
        else:
            result[key] = value

    return result


# Register the custom constructor
DuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, dict_constructor
)


class ColumnMapping:
    """Mapping between CSV and database columns."""

    def __init__(
        self,
        csv_column: str | None,
        db_column: str,
        data_type: str | None = None,
        nullable: bool | None = None,
        lookup: dict[str, Any] | None = None,
        expression: str | None = None,
        function: str | None = None,
        input_columns: list[str] | None = None,
    ) -> None:
        """Initialize column mapping.

        Args:
            csv_column: Name of the column in the CSV file. Can be None for custom functions
                       creating new columns. Can be specified with expression/function to provide
                       a named reference for the transformation.
            db_column: Name of the column in the database
            data_type: Optional data type (integer, float, date, datetime, text, varchar(N))
            nullable: Optional flag indicating if NULL values are allowed (True=NULL, False=NOT NULL)
            lookup: Optional dictionary to map CSV values to database values.
                   Values not in the lookup are passed through unchanged.
                   Example: {"active": 1, "inactive": 0} to convert status strings to integers.
            expression: Optional inline Python expression for custom calculations.
                       Example: "float(temperature) * 1.8 + 32" for Celsius to Fahrenheit
            function: Optional reference to external function in format "module.function".
                     Example: "my_functions.calculate_percentage"
            input_columns: List of CSV column names to pass as parameters to expression/function.
                          Required if expression or function is specified.

        Raises:
            ValueError: If both expression and function are specified, or if expression/function
                       is specified without input_columns.
        """
        # Validation
        if expression is not None and function is not None:
            raise ValueError("Cannot specify both 'expression' and 'function'")

        if (expression is not None or function is not None) and not input_columns:
            raise ValueError("Must specify 'input_columns' when using 'expression' or 'function'")

        self.csv_column = csv_column
        self.db_column = db_column
        self.data_type = data_type
        self.nullable = nullable
        self.lookup = lookup
        self.expression = expression
        self.function = function
        self.input_columns = input_columns

    def apply_lookup(self, value: str) -> Any:
        """Apply lookup transformation to a value.

        Args:
            value: The value from the CSV

        Returns:
            The transformed value if found in lookup, otherwise the original value
        """
        if self.lookup is None:
            return value
        return self.lookup.get(value, value)

    def apply_custom_function(self, row_data: dict[str, Any]) -> Any:
        """Apply custom function or expression to compute a value.

        Args:
            row_data: Dictionary of column name to value from the CSV row

        Returns:
            The computed value from the expression or function

        Raises:
            ValueError: If input columns are missing from row_data
            RuntimeError: If expression evaluation or function execution fails
        """
        if self.expression is None and self.function is None:
            raise RuntimeError("No expression or function defined for custom function")

        if not self.input_columns:
            raise RuntimeError("No input_columns defined for custom function")

        # Collect input values
        input_values = []
        for col_name in self.input_columns:
            if col_name not in row_data:
                raise ValueError(f"Input column '{col_name}' not found in row data")
            input_values.append(row_data[col_name])

        if self.expression:
            # Execute inline expression
            # Create a namespace with only the input values and safe built-ins
            namespace = {}
            for i, col_name in enumerate(self.input_columns):
                namespace[col_name] = input_values[i]

            # Add safe built-in functions
            namespace["__builtins__"] = {
                "abs": abs,
                "min": min,
                "max": max,
                "round": round,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "len": len,
            }

            try:
                result = eval(self.expression, namespace)
                return result
            except Exception as e:
                raise RuntimeError(f"Failed to evaluate expression '{self.expression}': {e}") from e
        else:
            # Execute external function
            try:
                # Parse module and function name
                parts = self.function.split(".")  # type: ignore[union-attr]
                if len(parts) < 2:
                    raise ValueError(
                        f"Function must be in format 'module.function', got '{self.function}'"
                    )

                module_name = ".".join(parts[:-1])
                function_name = parts[-1]

                # Import module and get function
                module = importlib.import_module(module_name)
                func = getattr(module, function_name)

                # Call function with input values
                result = func(*input_values)
                return result
            except Exception as e:
                raise RuntimeError(f"Failed to execute function '{self.function}': {e}") from e


class FilenameColumnMapping:
    """Mapping for a single column extracted from filename."""

    def __init__(
        self,
        name: str,
        db_column: str | None = None,
        data_type: str | None = None,
        use_to_delete_old_rows: bool = False,
    ) -> None:
        """Initialize filename column mapping.

        Args:
            name: Name of the extracted value (from template/regex)
            db_column: Database column name (defaults to name if not specified)
            data_type: Data type (varchar(N), integer, float, date, datetime, text)
            use_to_delete_old_rows: If True, this column is used to identify stale rows
        """
        self.name = name
        self.db_column = db_column or name
        self.data_type = data_type
        self.use_to_delete_old_rows = use_to_delete_old_rows


class FilenameToColumn:
    """Configuration for extracting multiple values from filename."""

    def __init__(
        self,
        columns: dict[str, FilenameColumnMapping],
        template: str | None = None,
        regex: str | None = None,
    ) -> None:
        """Initialize filename to column mapping.

        Args:
            columns: Dictionary of column name to FilenameColumnMapping
            template: Filename template with [column_name] syntax (mutually exclusive with regex)
            regex: Regex pattern with named groups (mutually exclusive with template)

        Raises:
            ValueError: If both template and regex are specified, or neither is specified
        """
        if (template is None) == (regex is None):
            raise ValueError("Must specify exactly one of 'template' or 'regex'")

        self.columns = columns
        self.template = template
        self.regex = regex

        # Pre-compile regex
        if template:
            self._compiled_regex = self._template_to_regex(template)
        else:
            self._compiled_regex = re.compile(regex)

    def _template_to_regex(self, template: str) -> re.Pattern:
        r"""Convert template string to regex pattern.

        Args:
            template: Template string with [column_name] placeholders

        Returns:
            Compiled regex pattern with named groups

        Example:
            >>> mapping = FilenameToColumn(...)
            >>> # Template: "[mission]level2[sensor]_[date].cdf"
            >>> # becomes: "(?P<mission>.+?)level2(?P<sensor>.+?)_(?P<date>.+?)\.cdf"
        """
        # Escape special regex characters
        escaped = re.escape(template)
        # Replace \[column_name\] with named groups using non-greedy matching
        pattern = re.sub(r"\\\[(\w+)\\\]", r"(?P<\1>.+?)", escaped)
        return re.compile(pattern)

    def extract_values_from_filename(self, filename: str | Path) -> dict[str, str] | None:
        """Extract values from filename using template or regex.

        Args:
            filename: The filename (or path) to extract values from

        Returns:
            Dictionary of column name to extracted value, or None if no match

        Example:
            >>> mapping = FilenameToColumn(
            ...     columns={...},
            ...     template="[mission]level2[sensor]_[date]_v[version].cdf"
            ... )
            >>> mapping.extract_values_from_filename("imap_level2_primary_20000102_v002.cdf")
            {'mission': 'imap', 'sensor': 'primary', 'date': '20000102', 'version': '002'}
        """
        if isinstance(filename, Path):
            filename = filename.name

        match = self._compiled_regex.search(filename)
        if not match:
            return None

        return match.groupdict()

    def get_delete_key_columns(self) -> list[str]:
        """Get list of database column names used for stale row deletion.

        Returns:
            List of db_column names where use_to_delete_old_rows is True
        """
        return [col.db_column for col in self.columns.values() if col.use_to_delete_old_rows]


class IndexColumn:
    """Column definition for a database index."""

    def __init__(self, column: str, order: str = "ASC") -> None:
        """Initialize index column.

        Args:
            column: Column name
            order: Sort order - 'ASC' or 'DESC' (default: 'ASC')

        Raises:
            ValueError: If order is not 'ASC' or 'DESC'
        """
        if order.upper() not in ("ASC", "DESC"):
            raise ValueError(f"Index order must be 'ASC' or 'DESC', got '{order}'")
        self.column = column
        self.order = order.upper()


class Index:
    """Database index configuration."""

    def __init__(self, name: str, columns: list[IndexColumn]) -> None:
        """Initialize index.

        Args:
            name: Index name
            columns: List of columns with sort order

        Raises:
            ValueError: If columns list is empty
        """
        if not columns:
            raise ValueError("Index must have at least one column")
        self.name = name
        self.columns = columns


class CrumpJob:
    """Configuration for a single sync job."""

    def __init__(
        self,
        name: str,
        target_table: str,
        id_mapping: list[ColumnMapping],
        columns: list[ColumnMapping] | None = None,
        filename_match: str | None = None,
        filename_to_column: FilenameToColumn | None = None,
        indexes: list[Index] | None = None,
        sample_percentage: float | None = None,
    ) -> None:
        """Initialize a sync job.

        Args:
            name: Name of the job
            target_table: Target database table name
            id_mapping: List of mappings for ID columns (supports compound primary keys)
            columns: List of column mappings to sync (all columns if None)
            filename_to_column: Optional filename-to-column extraction configuration
            filename_match: Allow automatic job selection from config file if this is specified
            indexes: Optional list of database indexes to create
            sample_percentage: Optional percentage of rows to sample (0-100). If None or 100,
                              syncs all rows. Values like 10 mean 1 in every 10 rows.
                              Always includes first and last row.
        """
        self.name = name
        self.target_table = target_table
        self.id_mapping = id_mapping
        self.columns = columns or []
        self.filename_to_column = filename_to_column
        self.indexes = indexes or []
        self.sample_percentage = sample_percentage
        self.filename_match = filename_match

        # Validate sample_percentage
        if sample_percentage is not None and not (0 <= sample_percentage <= 100):
            raise ValueError(
                f"sample_percentage must be between 0 and 100, got {sample_percentage}"
            )


class CrumpConfig:
    """Configuration for data synchronization."""

    def __init__(
        self, jobs: dict[str, CrumpJob], id_column_matchers: list[str] | None = None
    ) -> None:
        """Initialize sync configuration.

        Args:
            jobs: Dictionary of job name to CrumpJob
            id_column_matchers: Optional list of column name patterns to match as ID columns
                               (e.g., ['id', 'uuid', 'key']). If None, uses default patterns.
        """
        self.jobs = jobs
        self.id_column_matchers = id_column_matchers

    def get_job(self, name: str) -> CrumpJob | None:
        """Get a job by name.

        Args:
            name: Name of the job

        Returns:
            CrumpJob if found, None otherwise
        """
        return self.jobs.get(name)

    def get_job_or_auto_detect(
        self, name: str | None = None, filename: str | None = None
    ) -> tuple[CrumpJob, str] | None:
        """Get a job by name, or auto-detect if there's only one job.

        Args:
            name: Name of the job (optional - if None, auto-detect single job)

        Returns:
            Tuple of (CrumpJob, job_name) if found/detected, None otherwise

        Raises:
            ValueError: If name is None and config has multiple jobs
        """
        if name is not None:
            # Job name explicitly provided
            job = self.jobs.get(name)
            if job:
                return (job, name)
            return None

        # Auto-detect: only allowed if there's exactly one job
        if len(self.jobs) == 0:
            return None

        if len(self.jobs) == 1:
            # Only one job - use it automatically
            job_name = next(iter(self.jobs.keys()))
            return (self.jobs[job_name], job_name)

        if filename is not None:
            # Try to auto-detect job based on filename_match
            for job_name, job in self.jobs.items():
                if job.filename_match:
                    # match using the full path as a string
                    if fnmatch.fnmatch(filename, job.filename_match):
                        return (job, job_name)
                    # or match using just the filename part
                    if fnmatch.fnmatch(Path(filename).name, job.filename_match):
                        return (job, job_name)
                    # support regex as well but check if it is a valid regex
                    try:
                        pattern = re.compile(job.filename_match)
                        if pattern.search(filename):
                            return (job, job_name)
                    except re.error:
                        continue

            # No matching job found

        # Multiple jobs - cannot auto-detect
        raise ValueError(
            f"Config contains {len(self.jobs)} jobs and unable to match one automatically. "
            "Please specify --job to select which one to use or configure filename_match in the job config."
        )

    @classmethod
    def from_yaml(cls, config_path: Path) -> CrumpConfig:
        r"""Load configuration from a YAML file.

        Args:
            config_path: Path to the YAML configuration file

        Returns:
            CrumpConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid

        Example YAML structure:
            id_column_matchers:  # Optional, root-level config
              - id
              - uuid
              - key
            jobs:
              my_job:
                target_table: users
                id_mapping:
                  user_id: id  # Single column primary key
                  # Or for compound primary key:
                  # user_id: id
                  # tenant_id: tenant
                columns:
                  name: full_name  # Simple format
                  email: email_address
                  age:
                    db_column: user_age
                    type: integer
                  salary:
                    db_column: monthly_salary
                    type: float
                sample_percentage: 10  # Optional: sync only 10% of rows (1 in 10)
                                       # Always includes first and last row
                                       # Omit or set to 100 to sync all rows
                filename_to_column:  # Optional: extract values from filename
                  template: "[mission]level2[sensor]_[date]_v[version].cdf"
                  # OR use regex with named groups:
                  # regex: "(?P<mission>[a-z]+)_level2_(?P<sensor>[a-z]+)_(?P<date>\\d{8})_v(?P<version>\\d+)\\.cdf"
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
                      use_to_delete_old_rows: true  # Use this column to identify stale rows
                    version:
                      db_column: file_version
                      type: varchar(10)
                indexes:  # Optional
                  - name: idx_email
                    columns:
                      - column: email
                        order: ASC
                  - name: idx_observation_date
                    columns:
                      - column: observation_date
                        order: DESC
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            data = yaml.load(f, Loader=DuplicateKeySafeLoader)

        if not data or "jobs" not in data:
            raise ValueError("Config file must contain 'jobs' section")

        # Parse optional id_column_matchers
        id_column_matchers = data.get("id_column_matchers")
        if id_column_matchers is not None and not isinstance(id_column_matchers, list):
            raise ValueError("id_column_matchers must be a list of strings")

        jobs = {}
        for job_name, job_data in data["jobs"].items():
            jobs[job_name] = cls._parse_job(job_name, job_data)

        return cls(jobs=jobs, id_column_matchers=id_column_matchers)

    @staticmethod
    def _parse_column_mapping(csv_col: str | None, value: Any, job_name: str) -> ColumnMapping:
        """Parse a column mapping from config value.

        Supports multiple formats:
        1. Simple: csv_column: db_column
        2. Extended: csv_column: {db_column: name, type: data_type, nullable: true/false, lookup: {...}}
        3. Custom function: null: {db_column: name, expression: "...", input_columns: [...]}
        4. Custom function: null: {db_column: name, function: "module.func", input_columns: [...]}

        Args:
            csv_col: CSV column name (can be None for custom functions)
            value: Either a string (db_column) or dict with db_column and optional fields
            job_name: Job name (for error messages)

        Returns:
            ColumnMapping instance

        Raises:
            ValueError: If mapping format is invalid
        """
        if isinstance(value, str):
            # Simple format: csv_column: db_column
            if csv_col is None:
                raise ValueError(
                    f"Job '{job_name}' cannot use simple format with null csv_column key"
                )
            return ColumnMapping(csv_column=csv_col, db_column=value)
        elif isinstance(value, dict):
            # Extended format with various options
            if "db_column" not in value:
                raise ValueError(
                    f"Job '{job_name}' column '{csv_col}' extended mapping must have 'db_column'"
                )
            db_column = value["db_column"]
            data_type = value.get("type")  # Optional
            nullable = value.get("nullable")  # Optional
            lookup = value.get("lookup")  # Optional
            expression = value.get("expression")  # Optional
            function = value.get("function")  # Optional
            input_columns = value.get("input_columns")  # Optional

            # Validate lookup is a dict if provided
            if lookup is not None and not isinstance(lookup, dict):
                raise ValueError(f"Job '{job_name}' column '{csv_col}' lookup must be a dictionary")

            # Validate expression is a string if provided
            if expression is not None and not isinstance(expression, str):
                raise ValueError(f"Job '{job_name}' column '{csv_col}' expression must be a string")

            # Validate function is a string if provided
            if function is not None and not isinstance(function, str):
                raise ValueError(f"Job '{job_name}' column '{csv_col}' function must be a string")

            # Validate input_columns is a list if provided
            if input_columns is not None and not isinstance(input_columns, list):
                raise ValueError(
                    f"Job '{job_name}' column '{csv_col}' input_columns must be a list"
                )

            return ColumnMapping(
                csv_column=csv_col,
                db_column=db_column,
                data_type=data_type,
                nullable=nullable,
                lookup=lookup,
                expression=expression,
                function=function,
                input_columns=input_columns,
            )
        else:
            raise ValueError(
                f"Job '{job_name}' column '{csv_col}' must be string or dict, got {type(value)}"
            )

    @staticmethod
    def _parse_job(name: str, job_data: dict[str, Any]) -> CrumpJob:
        """Parse a job from configuration data.

        Args:
            name: Name of the job
            job_data: Job configuration dictionary

        Returns:
            CrumpJob instance

        Raises:
            ValueError: If job configuration is invalid
        """
        if "target_table" not in job_data:
            raise ValueError(f"Job '{name}' missing 'target_table'")

        if "id_mapping" not in job_data:
            raise ValueError(f"Job '{name}' missing 'id_mapping'")

        # Parse id_mapping as a dict: {csv_column: db_column} or {csv_column: {db_column: x, type: y}}
        # Supports multiple columns for compound primary keys
        id_data = job_data["id_mapping"]
        if not isinstance(id_data, dict):
            raise ValueError(f"Job '{name}' id_mapping must be a dictionary")

        if len(id_data) < 1:
            raise ValueError(f"Job '{name}' id_mapping must have at least one mapping")

        id_mapping = []
        for csv_col, value in id_data.items():
            id_mapping.append(CrumpConfig._parse_column_mapping(csv_col, value, name))

        # Parse columns as a dict: {csv_column: db_column} or {csv_column: {db_column: x, type: y}}
        columns = []
        if "columns" in job_data and job_data["columns"]:
            col_data = job_data["columns"]
            if not isinstance(col_data, dict):
                raise ValueError(f"Job '{name}' columns must be a dictionary")

            for csv_col, value in col_data.items():
                # Handle multiple custom functions with null keys (collected as list)
                if csv_col is None and isinstance(value, list):
                    for item in value:
                        columns.append(CrumpConfig._parse_column_mapping(csv_col, item, name))
                else:
                    columns.append(CrumpConfig._parse_column_mapping(csv_col, value, name))

        # Parse optional filename_to_column
        filename_to_column = None
        if "filename_to_column" in job_data and job_data["filename_to_column"]:
            ftc_data = job_data["filename_to_column"]
            if not isinstance(ftc_data, dict):
                raise ValueError(f"Job '{name}' filename_to_column must be a dictionary")

            # Check that exactly one of template or regex is specified
            has_template = "template" in ftc_data and ftc_data["template"]
            has_regex = "regex" in ftc_data and ftc_data["regex"]

            if not has_template and not has_regex:
                raise ValueError(
                    f"Job '{name}' filename_to_column must have either 'template' or 'regex'"
                )

            if has_template and has_regex:
                raise ValueError(
                    f"Job '{name}' filename_to_column cannot have both 'template' and 'regex'"
                )

            # Parse columns
            if "columns" not in ftc_data or not ftc_data["columns"]:
                raise ValueError(f"Job '{name}' filename_to_column must have 'columns'")

            if not isinstance(ftc_data["columns"], dict):
                raise ValueError(f"Job '{name}' filename_to_column columns must be a dictionary")

            ftc_columns = {}
            for col_name, col_data in ftc_data["columns"].items():
                if isinstance(col_data, dict):
                    db_column = col_data.get("db_column")
                    data_type = col_data.get("type")
                    use_to_delete_old_rows = col_data.get("use_to_delete_old_rows", False)
                elif col_data is None:
                    # Simple format: column_name: null (use defaults)
                    db_column = None
                    data_type = None
                    use_to_delete_old_rows = False
                else:
                    raise ValueError(
                        f"Job '{name}' filename_to_column column '{col_name}' must be a dictionary or null"
                    )

                ftc_columns[col_name] = FilenameColumnMapping(
                    name=col_name,
                    db_column=db_column,
                    data_type=data_type,
                    use_to_delete_old_rows=use_to_delete_old_rows,
                )

            filename_to_column = FilenameToColumn(
                columns=ftc_columns,
                template=ftc_data.get("template"),
                regex=ftc_data.get("regex"),
            )

        # Parse optional indexes
        indexes = []
        if "indexes" in job_data and job_data["indexes"]:
            indexes_data = job_data["indexes"]
            if not isinstance(indexes_data, list):
                raise ValueError(f"Job '{name}' indexes must be a list")

            for idx_data in indexes_data:
                if not isinstance(idx_data, dict):
                    raise ValueError(f"Job '{name}' index entry must be a dictionary")

                if "name" not in idx_data:
                    raise ValueError(f"Job '{name}' index missing 'name'")

                if "columns" not in idx_data:
                    raise ValueError(f"Job '{name}' index missing 'columns'")

                idx_columns = []
                for col_data in idx_data["columns"]:
                    if not isinstance(col_data, dict):
                        raise ValueError(f"Job '{name}' index column must be a dictionary")

                    if "column" not in col_data:
                        raise ValueError(f"Job '{name}' index column missing 'column' field")

                    order = col_data.get("order", "ASC")
                    idx_columns.append(IndexColumn(column=col_data["column"], order=order))

                indexes.append(Index(name=idx_data["name"], columns=idx_columns))

        # Parse optional sample_percentage
        sample_percentage = None
        if "sample_percentage" in job_data and job_data["sample_percentage"] is not None:
            sample_percentage = job_data["sample_percentage"]
            # Validate it's a number
            if not isinstance(sample_percentage, (int, float)):
                raise ValueError(f"Job '{name}' sample_percentage must be a number")
            if not (0 <= sample_percentage <= 100):
                raise ValueError(
                    f"Job '{name}' sample_percentage must be between 0 and 100, got {sample_percentage}"
                )

        filename_match = None
        if "filename_match" in job_data and job_data["filename_match"]:
            filename_match = job_data["filename_match"]
            if not isinstance(filename_match, str):
                raise ValueError(f"Job '{name}' filename_match must be a string")

        return CrumpJob(
            name=name,
            target_table=job_data["target_table"],
            id_mapping=id_mapping,
            columns=columns if columns else None,
            filename_to_column=filename_to_column,
            filename_match=filename_match,
            indexes=indexes if indexes else None,
            sample_percentage=sample_percentage,
        )

    def add_or_update_job(self, job: CrumpJob, force: bool = False) -> bool:
        """Add a new job or update an existing one.

        Args:
            job: CrumpJob to add or update
            force: If True, overwrite existing job. If False, raise error if job exists.

        Returns:
            True if job was added/updated

        Raises:
            ValueError: If job already exists and force=False
        """
        if job.name in self.jobs and not force:
            raise ValueError(f"Job '{job.name}' already exists. Use force=True to overwrite.")

        self.jobs[job.name] = job
        return True

    def to_yaml_dict(self) -> dict[str, Any]:
        """Convert config to dictionary suitable for YAML serialization.

        Returns:
            Dictionary representation of config
        """
        jobs_dict = {}

        for job_name, job in self.jobs.items():
            # Build id_mapping dict (supports compound primary keys)
            id_mapping_dict: dict[str, Any] = {}
            for id_col in job.id_mapping:
                needs_extended = (
                    id_col.data_type
                    or id_col.nullable is not None
                    or id_col.lookup is not None
                    or id_col.expression is not None
                    or id_col.function is not None
                    or id_col.input_columns is not None
                )
                if needs_extended:
                    mapping_dict: dict[str, Any] = {"db_column": id_col.db_column}
                    if id_col.data_type:
                        mapping_dict["type"] = id_col.data_type
                    if id_col.nullable is not None:
                        mapping_dict["nullable"] = id_col.nullable
                    if id_col.lookup is not None:
                        mapping_dict["lookup"] = id_col.lookup
                    if id_col.expression is not None:
                        mapping_dict["expression"] = id_col.expression
                    if id_col.function is not None:
                        mapping_dict["function"] = id_col.function
                    if id_col.input_columns is not None:
                        mapping_dict["input_columns"] = id_col.input_columns
                    # Use None as key for custom functions (no csv_column)
                    key = id_col.csv_column if id_col.csv_column is not None else None
                    id_mapping_dict[key] = mapping_dict  # type: ignore[index]
                else:
                    id_mapping_dict[id_col.csv_column] = id_col.db_column  # type: ignore[index]

            job_dict: dict[str, Any] = {
                "target_table": job.target_table,
                "id_mapping": id_mapping_dict,
            }

            # Add columns if present
            if job.columns:
                columns_dict: dict[str, Any] = {}
                for col in job.columns:
                    needs_extended = (
                        col.data_type
                        or col.nullable is not None
                        or col.lookup is not None
                        or col.expression is not None
                        or col.function is not None
                        or col.input_columns is not None
                    )
                    if needs_extended:
                        mapping_dict = {"db_column": col.db_column}
                        if col.data_type:
                            mapping_dict["type"] = col.data_type
                        if col.nullable is not None:
                            mapping_dict["nullable"] = col.nullable
                        if col.lookup is not None:
                            mapping_dict["lookup"] = col.lookup
                        if col.expression is not None:
                            mapping_dict["expression"] = col.expression
                        if col.function is not None:
                            mapping_dict["function"] = col.function
                        if col.input_columns is not None:
                            mapping_dict["input_columns"] = col.input_columns
                        # Use None as key for custom functions (no csv_column)
                        key = col.csv_column if col.csv_column is not None else None
                        columns_dict[key] = mapping_dict  # type: ignore[index]
                    else:
                        columns_dict[col.csv_column] = col.db_column  # type: ignore[index]
                job_dict["columns"] = columns_dict

            # Add filename_to_column if present
            if job.filename_to_column:
                ftc_dict: dict[str, Any] = {}
                if job.filename_to_column.template:
                    ftc_dict["template"] = job.filename_to_column.template
                else:
                    ftc_dict["regex"] = job.filename_to_column.regex

                ftc_columns_dict: dict[str, Any] = {}
                for col_name, col_mapping in job.filename_to_column.columns.items():
                    col_dict: dict[str, Any] = {}
                    if col_mapping.db_column != col_mapping.name:
                        col_dict["db_column"] = col_mapping.db_column
                    if col_mapping.data_type:
                        col_dict["type"] = col_mapping.data_type
                    if col_mapping.use_to_delete_old_rows:
                        col_dict["use_to_delete_old_rows"] = True

                    # If col_dict is empty, use None to keep it minimal
                    ftc_columns_dict[col_name] = col_dict if col_dict else None

                ftc_dict["columns"] = ftc_columns_dict
                job_dict["filename_to_column"] = ftc_dict

            # Add indexes if present
            if job.indexes:
                indexes_list = []
                for index in job.indexes:
                    index_dict = {
                        "name": index.name,
                        "columns": [
                            {"column": col.column, "order": col.order} for col in index.columns
                        ],
                    }
                    indexes_list.append(index_dict)
                job_dict["indexes"] = indexes_list

            # Add sample_percentage if present and not default
            if job.sample_percentage is not None and job.sample_percentage != 100:
                job_dict["sample_percentage"] = job.sample_percentage

            jobs_dict[job_name] = job_dict

        result: dict[str, Any] = {"jobs": jobs_dict}

        # Add id_column_matchers if present
        if self.id_column_matchers is not None:
            result["id_column_matchers"] = self.id_column_matchers

        return result

    def save_to_yaml(self, config_path: Path) -> None:
        """Save configuration to a YAML file.

        Args:
            config_path: Path to save the YAML file
        """
        config_dict = self.to_yaml_dict()

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)


def apply_row_transformations(
    row: dict[str, Any],
    sync_columns: list[ColumnMapping],
    filename_to_column: FilenameToColumn | None = None,
    filename_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Apply column transformations to a CSV row.

    This is a shared helper function used by both sync and extract operations
    to apply the same transformations consistently.

    Args:
        row: Dictionary representing a CSV row (column_name -> value)
        sync_columns: List of ColumnMapping objects defining transformations
        filename_to_column: Optional FilenameToColumn configuration
        filename_values: Optional dict of values extracted from filename

    Returns:
        Dictionary with transformed values (db_column_name -> value)
    """
    row_data = {}

    # Process each column mapping
    for col_mapping in sync_columns:
        # Check if this column uses a custom function/expression
        if col_mapping.expression or col_mapping.function:
            # Apply custom function/expression
            row_data[col_mapping.db_column] = col_mapping.apply_custom_function(row)
        elif col_mapping.csv_column and col_mapping.csv_column in row:
            csv_value = row[col_mapping.csv_column]
            # Apply lookup transformation if configured
            row_data[col_mapping.db_column] = col_mapping.apply_lookup(csv_value)

    # Add filename values if configured
    if filename_to_column and filename_values:
        for col_name, filename_col_mapping in filename_to_column.columns.items():
            if col_name in filename_values:
                row_data[filename_col_mapping.db_column] = filename_values[col_name]

    return row_data
