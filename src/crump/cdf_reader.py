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


def read_cdf_variables(file_path: Path) -> list[CDFVariable]:
    """Read all variables from a CDF file.

    Args:
        file_path: Path to the CDF file

    Returns:
        List of CDFVariable objects sorted by record count (descending)

    Raises:
        ImportError: If cdflib is not installed
        Exception: If the file cannot be read
    """
    try:
        import cdflib
    except ImportError as e:
        raise ImportError(
            "cdflib is required for CDF operations. Install with: pip install cdflib"
        ) from e

    variables = []

    with cdflib.CDF(str(file_path)) as cdf:
        info = cdf.cdf_info()
        all_vars = info.rVariables + info.zVariables

        for var_name in all_vars:
            try:
                data = cdf.varget(var_name)

                # Get variable info to check for EPOCH type
                try:
                    var_info = cdf.varinq(var_name)
                except Exception:
                    var_info = None

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
                continue

    # Sort by number of records (descending)
    variables.sort(key=lambda v: v.num_records, reverse=True)

    return variables


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
