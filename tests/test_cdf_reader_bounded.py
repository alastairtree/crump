"""Tests for bounded CDF reads, grouping and global attributes."""

from __future__ import annotations

from pathlib import Path

import cdflib
import numpy as np
import pytest
from cdflib import cdfwrite

import crump
from crump.cdf_reader import (
    CDFVariable,
    group_variables_by_record_count,
    read_cdf_global_attributes,
    read_cdf_variables,
)

N_MAIN = 10
N_SLOW = 4


def _var(
    w: cdfwrite.CDF,
    name: str,
    data_type: int,
    data: np.ndarray | None,
    *,
    rec_vary: bool = True,
    dims: list[int] | None = None,
    num_elements: int = 1,
    attrs: dict | None = None,
) -> None:
    w.write_var(
        {
            "Variable": name,
            "Data_Type": data_type,
            "Num_Elements": num_elements,
            "Rec_Vary": rec_vary,
            "Dim_Sizes": dims or [],
        },
        var_attrs=attrs,
        var_data=data,
    )


@pytest.fixture
def cdf_path(tmp_path: Path) -> Path:
    """CDF with two record counts, a 2-D labelled variable, a constant and an empty variable."""
    path = tmp_path / "sample.cdf"
    w = cdfwrite.CDF(str(path))
    w.write_globalattrs(
        {"Project": {0: "Demo"}, "Mods": {0: "first", 1: "second"}},
    )
    epoch = (np.arange(N_MAIN, dtype=np.int64) + 1) * 1_000_000_000
    _var(w, "Epoch", 33, epoch)
    _var(w, "flux", 45, np.arange(N_MAIN, dtype=np.float64))
    _var(w, "f32", 44, np.arange(N_MAIN, dtype=np.float32))
    _var(
        w,
        "B",
        45,
        np.arange(N_MAIN * 3, dtype=np.float64).reshape(N_MAIN, 3),
        dims=[3],
        attrs={"LABL_PTR_1": "B_labels"},
    )
    _var(
        w,
        "B_labels",
        51,
        np.array(["Bx", "By", "Bz"]),
        rec_vary=False,
        dims=[3],
        num_elements=2,
    )
    _var(w, "calib", 45, np.float64(5.0), rec_vary=False)
    _var(w, "slow", 45, np.arange(N_SLOW, dtype=np.float64))
    _var(w, "empty", 44, None)
    w.close()
    return path


def by_name(variables: list[CDFVariable]) -> dict[str, CDFVariable]:
    return {v.name: v for v in variables}


@pytest.mark.parametrize("limit", [1, 3, N_SLOW, 7, N_MAIN])
def test_bounded_read_keeps_true_record_count(cdf_path: Path, limit: int) -> None:
    v = by_name(read_cdf_variables(cdf_path, max_records=limit))
    assert v["f32"].num_records == N_MAIN
    assert len(v["f32"].data) == min(limit, N_MAIN)
    assert v["f32"].shape == (min(limit, N_MAIN),)
    assert v["slow"].num_records == N_SLOW
    assert len(v["slow"].data) == min(limit, N_SLOW)
    assert v["B"].num_records == N_MAIN
    assert v["B"].shape == (min(limit, N_MAIN), 3)
    assert v["B"].is_array and v["B"].array_size == 3
    np.testing.assert_array_equal(v["flux"].data, np.arange(min(limit, N_MAIN)))


def test_max_records_larger_than_file(cdf_path: Path) -> None:
    v = by_name(read_cdf_variables(cdf_path, max_records=1000))
    assert len(v["f32"].data) == N_MAIN
    assert v["f32"].num_records == N_MAIN
    assert len(v["slow"].data) == N_SLOW


def test_epoch_converted_in_bounded_read(cdf_path: Path) -> None:
    v = by_name(read_cdf_variables(cdf_path, max_records=2))
    assert np.issubdtype(v["Epoch"].data.dtype, np.datetime64)
    assert len(v["Epoch"].data) == 2
    assert v["Epoch"].num_records == N_MAIN


def test_dtype_preserved(cdf_path: Path) -> None:
    for limit in (None, 3):
        v = by_name(read_cdf_variables(cdf_path, max_records=limit))
        assert v["f32"].data.dtype == np.float32
        assert v["f32"].dtype == "float32"
        assert v["flux"].data.dtype == np.float64


def test_non_record_varying_has_one_value(cdf_path: Path) -> None:
    v = by_name(read_cdf_variables(cdf_path, max_records=3))
    assert v["calib"].num_records == 1
    assert float(v["calib"].data) == 5.0
    assert v["B_labels"].num_records == 3  # one-dimensional constant of 3 labels, unbounded by rows


def test_zero_record_variable_skipped_and_reported(cdf_path: Path) -> None:
    for limit in (None, 5):
        skipped: list[str] = []
        names = {v.name for v in read_cdf_variables(cdf_path, max_records=limit, skipped=skipped)}
        assert "empty" not in names
        assert skipped == ["empty"]


def test_skipped_is_optional_and_untouched_when_nothing_skipped(tmp_path: Path) -> None:
    path = tmp_path / "ok.cdf"
    w = cdfwrite.CDF(str(path))
    _var(w, "a", 45, np.arange(3, dtype=np.float64))
    w.close()
    skipped: list[str] = []
    assert len(read_cdf_variables(path, skipped=skipped)) == 1
    assert skipped == []


def test_max_records_validation(cdf_path: Path) -> None:
    with pytest.raises(ValueError):
        read_cdf_variables(cdf_path, max_records=0)


def test_unbounded_read_unchanged(cdf_path: Path) -> None:
    v = by_name(read_cdf_variables(cdf_path))
    assert v["f32"].num_records == N_MAIN
    assert len(v["f32"].data) == N_MAIN
    assert v["B"].shape == (N_MAIN, 3)
    assert v["slow"].num_records == N_SLOW
    counts = [x.num_records for x in read_cdf_variables(cdf_path)]
    assert counts == sorted(counts, reverse=True)
    # Same result as explicit max_records=None
    other = by_name(read_cdf_variables(cdf_path, max_records=None))
    assert other.keys() == v.keys()


def test_column_names_from_labels_with_bounded_read(cdf_path: Path) -> None:
    v = by_name(read_cdf_variables(cdf_path, max_records=5))
    with cdflib.CDF(str(cdf_path)) as cdf:
        assert v["B"].get_column_names(cdf) == ["B_Bx", "B_By", "B_Bz"]


def test_grouping_largest_first(cdf_path: Path) -> None:
    groups = group_variables_by_record_count(read_cdf_variables(cdf_path, max_records=2))
    assert list(groups) == [N_MAIN, N_SLOW, 3, 1]
    assert {x.name for x in groups[N_MAIN]} == {"Epoch", "flux", "f32", "B"}
    assert [x.name for x in groups[N_SLOW]] == ["slow"]
    assert [x.name for x in groups[1]] == ["calib"]


def test_grouping_unsorted_input() -> None:
    def mk(name: str, n: int) -> CDFVariable:
        return CDFVariable(name, np.zeros(1), n, (1,), "float64", {})

    groups = group_variables_by_record_count([mk("a", 2), mk("b", 9), mk("c", 2)])
    assert list(groups) == [9, 2]
    assert [x.name for x in groups[2]] == ["a", "c"]


def test_global_attributes(cdf_path: Path) -> None:
    attrs = read_cdf_global_attributes(cdf_path)
    assert attrs["Project"] == ["Demo"]
    assert attrs["Mods"] == ["first", "second"]


def test_public_exports() -> None:
    for name in (
        "read_cdf_variables",
        "read_cdf_global_attributes",
        "group_variables_by_record_count",
        "CDFVariable",
    ):
        assert hasattr(crump, name)
        assert name in crump.__all__


def test_never_reads_more_than_max_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    n = 1_000_000
    path = tmp_path / "big.cdf"
    w = cdfwrite.CDF(str(path))
    _var(w, "big", 44, np.zeros(n, dtype=np.float32))
    _var(w, "big2", 45, np.zeros((n, 2), dtype=np.float64), dims=[2])
    _var(w, "small", 45, np.arange(5, dtype=np.float64))
    w.close()

    calls: list[tuple[str, dict]] = []
    original = cdflib.CDF.varget

    def spy(self, variable=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        result = original(self, variable, *args, **kwargs)
        calls.append((variable, kwargs))
        if variable in {"big", "big2", "small"}:
            assert len(result) <= 100
        return result

    monkeypatch.setattr(cdflib.CDF, "varget", spy)
    v = by_name(read_cdf_variables(path, max_records=100))

    assert v["big"].num_records == n
    assert len(v["big"].data) == 100
    assert len(v["big2"].data) == 100
    assert v["small"].num_records == 5 and len(v["small"].data) == 5
    data_calls = [(name, kw) for name, kw in calls if name in {"big", "big2", "small"}]
    assert len(data_calls) == 3
    for name, kw in data_calls:
        assert kw["startrec"] == 0
        assert kw["endrec"] == (4 if name == "small" else 99)
