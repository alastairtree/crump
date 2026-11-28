"""CDF file reading utilities for data_sync."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class CDFVariable:
    """Represents a variable from a CDF file."""

    name: str
    data: np.ndarray | Any
    num_records: int
    shape: tuple[int, ...]
    dtype: str
    attributes: dict[str, Any]

    @property
    def is_array(self) -> bool:
        """Check if this variable contains array data (2D)."""
        return isinstance(self.data, np.ndarray) and len(self.shape) == 2

    @property
    def array_size(self) -> int:
        """Get the size of array elements (for 2D arrays)."""
        return self.shape[1] if self.is_array else 1

    def get_column_names(self, cdf_file: Any) -> list[str]:
        """Generate column names for this variable.

        Args:
            cdf_file: The CDF file object to read label metadata

        Returns:
            List of column names for this variable
        """
        if not self.is_array:
            # Simple 1D variable - use variable name
            return [self.name]

        # Try to get labels from CDF metadata
        labels = self._get_labels_from_metadata(cdf_file)
        if labels and len(labels) == self.array_size:
            return [f"{self.name}_{label}" for label in labels]

        # Fall back to generic names based on common patterns
        return self._generate_generic_column_names()

    def _get_labels_from_metadata(self, cdf_file: Any) -> list[str] | None:
        """Try to extract labels from CDF metadata.

        Args:
            cdf_file: The CDF file object

        Returns:
            List of labels if found, None otherwise
        """

        def _is_useful_label(label: str) -> bool:
            """Check if a label is useful (not just a number or index)."""
            # Filter out labels that are just numbers or single digits
            if label.isdigit():
                return False
            # Filter out very short labels that look like indices
            return not len(label) <= 1

        def _process_labels(label_data: np.ndarray) -> list[str] | None:
            """Process and validate label data."""
            labels = [str(label).strip() for label in label_data]
            # Only return if at least some labels are useful
            useful_labels = [lbl for lbl in labels if _is_useful_label(lbl)]
            if len(useful_labels) >= len(labels) // 2:  # At least half should be useful
                return labels
            return None

        # Try LABL_PTR_1 attribute (points to a label variable)
        if "LABL_PTR_1" in self.attributes:
            label_var_name = self.attributes["LABL_PTR_1"]
            try:
                label_data = cdf_file.varget(label_var_name)
                if isinstance(label_data, np.ndarray):
                    labels = _process_labels(label_data)
                    if labels:
                        return labels
            except Exception:
                pass

        # Try LBL1_{varname} or similar patterns
        potential_label_vars = [
            f"LBL1_{self.name}",
            f"LABL_{self.name}",
            f"{self.name}_LABEL",
            f"{self.name}_label",
        ]

        for label_var in potential_label_vars:
            try:
                label_data = cdf_file.varget(label_var)
                if isinstance(label_data, np.ndarray):
                    labels = _process_labels(label_data)
                    if labels:
                        return labels
            except Exception:
                continue

        # Try REP1_{varname} for representation labels (like r, t, n)
        for rep_var in [f"REP1_{self.name}", f"{self.name}_rep"]:
            try:
                rep_data = cdf_file.varget(rep_var)
                if isinstance(rep_data, np.ndarray):
                    labels = _process_labels(rep_data)
                    if labels:
                        return labels
            except Exception:
                continue

        return None

    def _generate_generic_column_names(self) -> list[str]:
        """Generate generic column names based on variable name and size.

        Returns:
            List of column names
        """
        # Check if variable name suggests coordinate system
        var_lower = self.name.lower()

        # Check for vector-like names
        is_vector = any(pattern in var_lower for pattern in ["vector", "vec", "mag", "field"])

        # Common coordinate suffixes
        if self.array_size == 3:
            if "rtn" in var_lower:
                return [f"{self.name}_r", f"{self.name}_t", f"{self.name}_n"]
            elif "xyz" in var_lower or is_vector:
                return [f"{self.name}_x", f"{self.name}_y", f"{self.name}_z"]

        if self.array_size == 4 and is_vector:
            return [
                f"{self.name}_x",
                f"{self.name}_y",
                f"{self.name}_z",
                f"{self.name}_w",
            ]

        # Default: use numeric indices
        return [f"{self.name}_{i}" for i in range(self.array_size)]


def _is_epoch_variable(var_info: Any, var_name: str, data: np.ndarray | Any) -> bool:
    """Check if a variable is a CDF EPOCH time variable.

    Args:
        var_info: Variable information from CDF
        var_name: Variable name
        data: Variable data

    Returns:
        True if this is an EPOCH variable, False otherwise
    """
    # Check if data type is CDF_TIME_TT2000 (data type 33)
    if hasattr(var_info, "Data_Type") and var_info.Data_Type == 33:
        return True

    # Check if data type description indicates EPOCH
    if (
        hasattr(var_info, "Data_Type_Description")
        and "TIME_TT2000" in var_info.Data_Type_Description
    ):
        return True

    # Fallback: check if variable name contains "epoch" and data is int64
    return "epoch" in var_name.lower() and isinstance(data, np.ndarray) and data.dtype == np.int64


def _convert_epoch_to_datetime(data: np.ndarray) -> np.ndarray:
    """Convert CDF EPOCH values to datetime64 array.

    Args:
        data: Array of EPOCH values (int64 nanoseconds since J2000)

    Returns:
        Array of datetime64[ns] values
    """
    try:
        from cdflib import cdfepoch  # type: ignore[import-untyped]

        # Convert EPOCH to datetime64[ns]
        # cdfepoch.to_datetime returns numpy.datetime64 array
        datetime_values = cdfepoch.to_datetime(data)

        # Return as-is (already datetime64[ns])
        return datetime_values  # type: ignore[no-any-return]
    except Exception:
        # If conversion fails, return original data
        return data


def _import_cdflib() -> Any:
    """Import cdflib, raising a helpful error if it is missing."""
    try:
        import cdflib
    except ImportError as e:
        raise ImportError(
            "cdflib is required for CDF operations. Install with: pip install cdflib"
        ) from e
    return cdflib


def _read_variable_data(
    cdf: Any, var_name: str, var_info: Any, max_records: int | None
) -> tuple[np.ndarray | Any, int | None]:
    """Read a variable's data, never reading more than ``max_records`` records.

    Args:
        cdf: Open ``cdflib.CDF`` object
        var_name: Name of the variable to read
        var_info: Result of ``cdf.varinq`` for the variable (or None if unavailable)
        max_records: Maximum number of records to read, or None to read everything

    Returns:
        Tuple of (data, true_total_records). ``true_total_records`` is None when it
        should be derived from the data itself (unbounded read, non-record-varying
        variable, or no variable info available).
    """
    if max_records is None:
        return cdf.varget(var_name), None

    if var_info is not None and not getattr(var_info, "Rec_Vary", True):
        # Non-record-varying variables hold a single value
        return cdf.varget(var_name), None

    total: int | None = None
    if var_info is not None and hasattr(var_info, "Last_Rec"):
        total = int(var_info.Last_Rec) + 1

    if total is not None and total <= 0:
        # Zero records: cdflib raises, so let the caller report it as unreadable
        raise ValueError(f"No records found for variable {var_name}")

    end = max_records if total is None else min(max_records, total)
    return cdf.varget(var_name, startrec=0, endrec=end - 1), total


def read_cdf_variables(
    file_path: Path,
    max_records: int | None = None,
    skipped: list[str] | None = None,
) -> list[CDFVariable]:
    """Read variables from a CDF file.

    Args:
        file_path: Path to the CDF file
        max_records: If given, read at most this many records (from the start) of each
            record-varying variable. ``CDFVariable.num_records`` still reports the
            variable's true total record count in the file, while ``data``, ``shape``
            and ``dtype`` describe only the records actually read. Non-record-varying
            variables always hold their single value. None reads everything.
        skipped: Optional list that is extended in place with the names of variables
            that could not be read (including variables with zero records). Such
            variables are always left out of the result.

    Returns:
        List of CDFVariable objects sorted by record count (descending)

    Raises:
        ImportError: If cdflib is not installed
        ValueError: If ``max_records`` is less than 1
        Exception: If the file cannot be read
    """
    if max_records is not None and max_records < 1:
        raise ValueError("max_records must be at least 1")

    cdflib = _import_cdflib()

    variables = []

    with cdflib.CDF(str(file_path)) as cdf:
        info = cdf.cdf_info()
        all_vars = info.rVariables + info.zVariables

        for var_name in all_vars:
            try:
                # Get variable info to check for EPOCH type and true record count
                try:
                    var_info = cdf.varinq(var_name)
                except Exception:
                    var_info = None

                data, total_records = _read_variable_data(cdf, var_name, var_info, max_records)

                # Convert EPOCH variables to datetime
                if (
                    var_info
                    and _is_epoch_variable(var_info, var_name, data)
                    and isinstance(data, np.ndarray)
                ):
                    data = _convert_epoch_to_datetime(data)

                # Determine number of records
                if isinstance(data, np.ndarray):
                    num_records = data.shape[0] if len(data.shape) > 0 else 1
                    shape = data.shape
                    dtype = str(data.dtype)
                else:
                    num_records = 1
                    shape = ()
                    dtype = type(data).__name__
                if total_records is not None:
                    num_records = total_records

                # Get variable attributes
                try:
                    attributes = cdf.varattsget(var_name)
                except Exception:
                    attributes = {}

                variables.append(
                    CDFVariable(
                        name=var_name,
                        data=data,
                        num_records=num_records,
                        shape=shape,
                        dtype=dtype,
                        attributes=attributes,
                    )
                )
            except Exception:
                # Skip variables that can't be read
                if skipped is not None:
                    skipped.append(var_name)
                continue

    # Sort by number of records (descending)
    variables.sort(key=lambda v: v.num_records, reverse=True)

    return variables


def group_variables_by_record_count(
    variables: list[CDFVariable],
) -> dict[int, list[CDFVariable]]:
    """Group variables into tables by their record count.

    Variables that share a record count belong to the same table. Non-record-varying
    variables (a single value) therefore form their own group under key 1.

    Args:
        variables: List of CDFVariable objects

    Returns:
        Dictionary mapping record count to the variables with that count, ordered by
        record count (largest first). Variable order within a group is preserved.
    """
    groups: dict[int, list[CDFVariable]] = {}

    for var in variables:
        groups.setdefault(var.num_records, []).append(var)

    return dict(sorted(groups.items(), key=lambda item: -item[0]))


def read_cdf_global_attributes(file_path: Path) -> dict[str, Any]:
    """Read the global attributes of a CDF file.

    Args:
        file_path: Path to the CDF file

    Returns:
        Dictionary mapping global attribute name to its value(s)

    Raises:
        ImportError: If cdflib is not installed
        Exception: If the file cannot be read
    """
    cdflib = _import_cdflib()

    with cdflib.CDF(str(file_path)) as cdf:
        return dict(cdf.globalattsget())


def get_column_names_for_variable(variable: CDFVariable, cdf_file_path: Path) -> list[str]:
    """Get column names for a CDF variable.

    Args:
        variable: The CDFVariable to get names for
        cdf_file_path: Path to the CDF file (needed to read label metadata)

    Returns:
        List of column names
    """
    try:
        import cdflib

        with cdflib.CDF(str(cdf_file_path)) as cdf:
            return variable.get_column_names(cdf)
    except Exception:
        # Fall back to basic column names if we can't read metadata
        if variable.is_array:
            return [f"{variable.name}_{i}" for i in range(variable.array_size)]
        return [variable.name]
