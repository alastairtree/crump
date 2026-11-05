"""Temporal inference, explicit formats, storage and CLI contracts."""

import csv
import logging
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml
from click.testing import CliRunner

from crump.cli import main
from crump.config import ColumnMapping, CrumpConfig, apply_row_transformations
from crump.database import DatabaseConnection
from crump.temporal import iso_to_epoch_ns, parse_automatic, parse_temporal
from crump.type_detection import detect_column_type
from tests.db_test_utils import execute_query

AUTOMATIC_CASES = [
    ("2024-02-29", "date", "2024-02-29"),
    ("2024-2-9", "date", "2024-02-09"),
    ("2024/02/29", "date", "2024-02-29"),
    ("2024.02.29", "date", "2024-02-29"),
    ("29/02/2024", "date", "2024-02-29"),
    ("29-02-2024", "date", "2024-02-29"),
    ("29.02.2024", "date", "2024-02-29"),
    ("03/04/2024", "date", "2024-04-03"),
    ("20240229", "date", "2024-02-29"),
    ("29 Feb 2024", "date", "2024-02-29"),
    ("29 February 2024", "date", "2024-02-29"),
    ("Feb 29, 2024", "date", "2024-02-29"),
    ("February 29, 2024", "date", "2024-02-29"),
    ("14:30", "time", "14:30:00"),
    ("14:30:45", "time", "14:30:45"),
    ("14:30:45.123456", "time", "14:30:45.123456"),
    ("2:30 PM", "time", "14:30:00"),
    ("02:30:45 am", "time", "02:30:45"),
    ("12:00 AM", "time", "00:00:00"),
    ("12:00 PM", "time", "12:00:00"),
    ("2024-02-29T14:30", "datetime", "2024-02-29 14:30:00"),
    ("2024-02-29 14:30:45", "datetime", "2024-02-29 14:30:45"),
    ("29/02/2024 14:30:45", "datetime", "2024-02-29 14:30:45"),
    ("29-02-2024 2:30 PM", "datetime", "2024-02-29 14:30:00"),
    ("29 Feb 2024 14:30:45", "datetime", "2024-02-29 14:30:45"),
    ("Feb 29, 2024 2:30 PM", "datetime", "2024-02-29 14:30:00"),
    ("2024-02-29T14:30:45.123456", "datetime", "2024-02-29 14:30:45.123456"),
    ("2024-02-29T14:30:45Z", "timestamptz", "2024-02-29 14:30:45+00:00"),
    ("2024-02-29T14:30:45+02:00", "timestamptz", "2024-02-29 12:30:45+00:00"),
    ("2024-02-29T14:30:45+0200", "timestamptz", "2024-02-29 12:30:45+00:00"),
    ("14:30:45+02:00", "timetz", "14:30:45+02:00"),
    ("14:30:45+15:59", "timetz", "14:30:45+15:59"),
    ("2024-02-29T14:30:45+23:59", "timestamptz", "2024-02-28 14:31:45+00:00"),
    ("0001-01-01", "date", "0001-01-01"),
    ("9999-12-31", "date", "9999-12-31"),
    ("1969-12-31 23:59:59", "datetime", "1969-12-31 23:59:59"),
    ("2038-01-19T03:14:08", "datetime", "2038-01-19 03:14:08"),
]


@pytest.mark.parametrize(("value", "kind", "expected"), AUTOMATIC_CASES)
def test_automatic_formats(value: str, kind: str, expected: str) -> None:
    assert detect_column_type([value, "", f"  {value}  "]) == kind
    assert parse_temporal(value, kind) == expected


@pytest.mark.parametrize(
    "value",
    [
        "12/31/2024",
        "12-31-2024",
        "12/31/2024 2:30 PM",
        "2024-02-30",
        "2023-02-29",
        "2024-02-29T25:30:00",
        "2024-02-29T12:30:00garbage",
        "2024-02-29T12:30:00.123456789",
        "14:30:45.1234567",
        "00:30 PM",
        "14:30:00+16:00",
        "13:30 AM",
        "12:60",
        "2024-02-29T12:30:00+02:60",
        "2024-02-29T12:30:00+24:00",
        "10000-01-01",
        "2024-02-29X12:30:00",
    ],
)
def test_invalid_or_nonautomatic_formats(value: str) -> None:
    assert detect_column_type([value]).startswith("varchar(")
    with pytest.raises(ValueError):
        parse_automatic(value)


@pytest.mark.parametrize("value", ["19700101", "20240229", "20991231"])
def test_compact_boundaries(value: str) -> None:
    assert detect_column_type([value, ""]) == "date"


@pytest.mark.parametrize("value", ["19691231", "21000101", "20240230", "20230229", "+20240229"])
def test_compact_requires_entire_column(value: str) -> None:
    assert detect_column_type(["20240229"] * 1001 + [value]) == "integer"


def test_mixed_formats_and_kinds() -> None:
    assert detect_column_type(["29/02/2024", "Feb 29, 2024", "20240229"]) == "date"
    assert detect_column_type(["2024-02-29", "29/02/2024 14:30"]) == "datetime"
    assert parse_temporal("2024-02-29", "datetime") == "2024-02-29 00:00:00"
    for values in [
        ["31/12/2024", "12/31/2024"],
        ["2024-02-29T14:30", "2024-02-29T14:30Z"],
        ["2024-02-29", "14:30"],
    ]:
        assert detect_column_type(values).startswith("varchar(")


@pytest.mark.parametrize(
    ("value", "kind", "fmt", "expected"),
    [
        ("12/31/2024", "date", "%m/%d/%Y", "2024-12-31"),
        ("03/04/2024", "date", "%m/%d/%Y", "2024-03-04"),
        ("12/31/2024 2:30 PM", "datetime", "%m/%d/%Y %I:%M %p", "2024-12-31 14:30:00"),
        ("2024|02|29 14h30m45s", "datetime", "%Y|%m|%d %Hh%Mm%Ss", "2024-02-29 14:30:45"),
        ("2024060", "date", "%Y%j", "2024-02-29"),
        ("02:30 PM", "time", "%I:%M %p", "14:30:00"),
        ("20240229T143045+0200", "timestamptz", "%Y%m%dT%H%M%S%z", "2024-02-29 12:30:45+00:00"),
    ],
)
def test_explicit_format(value: str, kind: str, fmt: str, expected: str) -> None:
    mapping = ColumnMapping("source", "target", kind, datetime_format=fmt)
    assert apply_row_transformations({"source": value}, [mapping]) == {"target": expected}


@pytest.mark.parametrize(
    ("kind", "fmt"),
    [
        ("text", "%Y"),
        (None, "%Y"),
        ("date", ""),
        ("date", "%Q"),
        ("date", "%Y-%Y"),
        ("date", "%"),
        ("date", 42),
    ],
)
def test_invalid_format_configuration(kind: str | None, fmt: str) -> None:
    with pytest.raises(ValueError):
        ColumnMapping("source", "target", kind, datetime_format=fmt)


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("2024-02-29T12:30Z", "datetime"),
        ("2024-02-29T12:30", "timestamptz"),
        ("12:30Z", "time"),
        ("12:30", "timetz"),
        ("2024-02-29T12:30", "date"),
    ],
)
def test_no_silent_timezone_or_time_loss(value: str, kind: str) -> None:
    with pytest.raises(ValueError):
        parse_temporal(value, kind)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1970-01-01T00:00:00Z", 0),
        ("1970-01-01T00:00:00.000000001Z", 1),
        ("1969-12-31T23:59:59.999999999Z", -1),
        ("1970-01-01T02:00:00.000000001+02:00", 1),
        ("1970-01-01T02:00:00.000000001+0200", 1),
        ("1677-09-21T00:12:43.145224192Z", -(2**63)),
        ("2262-04-11T23:47:16.854775807Z", 2**63 - 1),
    ],
)
def test_epoch_ns_exact(value: str, expected: int) -> None:
    assert iso_to_epoch_ns(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "1677-09-21T00:12:43.145224191Z",
        "2262-04-11T23:47:16.854775808Z",
        "2024-02-29T12:30:00",
        "2024-02-30T12:30:00Z",
        "2024-02-29T12:30:00.1234567890Z",
        "2024-02-29T12:30:00+24:00",
        "2024-02-29T12:30:00+02:60",
    ],
)
def test_epoch_ns_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        iso_to_epoch_ns(value)


def write_job(tmp_path: Path, columns: dict, **extra: object) -> Path:
    config = tmp_path / "dates.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "jobs": {
                    "dates": {
                        "target_table": "dates",
                        "id_mapping": {"id": {"db_column": "id", "type": "integer"}},
                        "columns": columns,
                        **extra,
                    }
                }
            }
        )
    )
    return config


def write_values(path: Path, values: list[str], column: str = "value") -> Path:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", column])
        writer.writerows(enumerate(values, 1))
    return path


def invoke_sync(runner: CliRunner, csv_path: Path, config: Path, url: str, dry: bool = False):
    return runner.invoke(
        main,
        [
            "sync",
            str(csv_path),
            "-c",
            str(config),
            "--db-url",
            url,
            *(["--dry-run"] if dry else []),
        ],
        terminal_width=240,
    )


def test_yaml_round_trip(tmp_path: Path) -> None:
    config = write_job(
        tmp_path,
        {"value": {"db_column": "value", "type": "datetime", "datetime_format": "%Y|%m|%d"}},
        id_mapping={"id": {"db_column": "id", "type": "date", "datetime_format": "%Y%m%d"}},
        filename_to_column={
            "template": "data_[date].csv",
            "columns": {
                "date": {"db_column": "file_date", "type": "date", "datetime_format": "%d-%m-%Y"},
            },
        },
    )
    loaded = CrumpConfig.from_yaml(config)
    loaded.save_to_yaml(tmp_path / "roundtrip.yml")
    assert yaml.safe_load(config.read_text()) == yaml.safe_load(
        (tmp_path / "roundtrip.yml").read_text()
    )


@pytest.mark.parametrize(("value", "kind", "expected"), AUTOMATIC_CASES)
def test_cli_stored_formats(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, value: str, kind: str, expected: str, caplog
) -> None:
    caplog.set_level(logging.INFO)
    config = write_job(tmp_path, {"value": "value"})
    source = write_values(tmp_path / "readings.csv", [value])
    preview = invoke_sync(cli_runner, source, config, db_url, dry=True)
    assert preview.exit_code == 0, preview.output
    preview_messages = list(caplog.messages)
    caplog.clear()
    with DatabaseConnection(db_url) as db:
        assert not db.table_exists("dates")
    result = invoke_sync(cli_runner, source, config, db_url)
    assert result.exit_code == 0, result.output
    for messages in (caplog.messages, preview_messages):
        parser_messages = [message for message in messages if "automatically parsing" in message]
        assert len(parser_messages) == 1
        assert f"as {kind} using" in parser_messages[0]
        assert parse_automatic(value).format in parser_messages[0]
    stored = execute_query(db_url, "SELECT value FROM dates")[0][0]
    assert str(stored) == expected
    with DatabaseConnection(db_url) as db:
        types = db.get_existing_columns_with_types("dates")
    expected_types = {
        "date": "date",
        "time": "time without time zone",
        "datetime": "timestamp without time zone",
        "timestamptz": "timestamp with time zone",
        "timetz": "time with time zone",
    }
    assert types["value"] == ("text" if db_url.startswith("sqlite") else expected_types[kind])


def test_cli_mixed_formats_logged_once(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, caplog
) -> None:
    caplog.set_level(logging.INFO)
    config = write_job(tmp_path, {"value": "value"})
    source = write_values(tmp_path / "readings.csv", ["29/02/2024", "Feb 29, 2024", "20240229"] * 3)
    for dry in (True, False, True, False):
        caplog.clear()
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code == 0, result.output
        messages = [message for message in caplog.messages if "automatically parsing" in message]
        assert len(messages) == 1
        assert all(fmt in messages[0] for fmt in ("%d/%m/%Y", "%b %d, %Y", "%Y%m%d"))
    assert execute_query(db_url, "SELECT COUNT(*) FROM dates")[0][0] == 9


def test_cli_prepare_sync(cli_runner: CliRunner, tmp_path: Path, db_url: str) -> None:
    source = write_values(tmp_path / "readings.csv", ["19700101", "20991231"])
    config = tmp_path / "prepared.yml"
    result = cli_runner.invoke(main, ["prepare", str(source), "-c", str(config)])
    assert result.exit_code == 0, result.output
    assert CrumpConfig.from_yaml(config).jobs["readings"].columns[0].data_type == "date"
    result = invoke_sync(cli_runner, source, config, db_url)
    assert result.exit_code == 0, result.output
    assert [
        str(row[0]) for row in execute_query(db_url, "SELECT value FROM readings ORDER BY id")
    ] == [
        "1970-01-01",
        "2099-12-31",
    ]


@pytest.mark.parametrize("kind", ["integer", "bigint", "text"])
def test_cli_explicit_override(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, kind: str, caplog
) -> None:
    caplog.set_level(logging.INFO)
    config = write_job(tmp_path, {"value": {"db_column": "value", "type": kind}})
    source = write_values(tmp_path / "readings.csv", ["20240229"])
    result = invoke_sync(cli_runner, source, config, db_url)
    assert result.exit_code == 0, result.output
    assert not any("automatically parsing" in message for message in caplog.messages)
    assert str(execute_query(db_url, "SELECT value FROM dates")[0][0]) == "20240229"


@pytest.mark.parametrize("mode", ["strict", "permissive"])
@pytest.mark.parametrize("nullable", [True, False])
def test_cli_validation_parity(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, caplog, mode: str, nullable: bool
) -> None:
    config = write_job(
        tmp_path,
        {
            "value": {
                "db_column": "value",
                "type": "datetime",
                "nullable": nullable,
            }
        },
        failure_mode=mode,
    )
    source = write_values(
        tmp_path / "readings.csv",
        [
            "29/02/2024 14:30:00",
            "2024-02-30T12:30:00",
            "12/31/2024 14:30:00",
        ],
    )
    with caplog.at_level(logging.WARNING):
        preview = invoke_sync(cli_runner, source, config, db_url, True)
        result = invoke_sync(cli_runner, source, config, db_url)
    assert preview.exit_code == result.exit_code == 0
    expected = 3 if mode == "permissive" and nullable else 1
    assert f"{expected} row(s)" in preview.output
    assert f"Successfully synced {expected} rows" in result.output
    assert execute_query(db_url, "SELECT COUNT(*) FROM dates")[0][0] == expected
    assert "selected row 2" in caplog.text
    assert "invalid temporal" in caplog.text


def test_cli_explicit_format(cli_runner: CliRunner, tmp_path: Path, db_url: str, caplog) -> None:
    caplog.set_level(logging.INFO)
    config = write_job(
        tmp_path,
        {
            "value": {
                "db_column": "value",
                "type": "datetime",
                "datetime_format": "%m/%d/%Y %I:%M %p",
            }
        },
    )
    source = write_values(tmp_path / "readings.csv", ["12/31/2024 2:30 PM"])
    for dry in (True, False):
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code == 0, result.output
        assert not any("automatically parsing" in message for message in caplog.messages)
    assert str(execute_query(db_url, "SELECT value FROM dates")[0][0]) == "2024-12-31 14:30:00"


def test_cli_date_order_independent_of_postgres(
    cli_runner: CliRunner, tmp_path: Path, db_url: str
) -> None:
    if db_url.startswith("sqlite"):
        pytest.skip("PostgreSQL DateStyle-specific test")
    source = write_values(tmp_path / "readings.csv", ["03/04/2024", "29/02/2024"])
    config = write_job(tmp_path, {"value": "value"})
    for order in ("MDY", "DMY"):
        url = db_url + "?options=" + quote(f"-c DateStyle=ISO,{order}")
        result = invoke_sync(cli_runner, source, config, url)
        assert result.exit_code == 0, result.output
        assert [
            str(row[0]) for row in execute_query(url, "SELECT value FROM dates ORDER BY id")
        ] == [
            "2024-04-03",
            "2024-02-29",
        ]


def test_cli_nanosecond_storage(cli_runner: CliRunner, tmp_path: Path, db_url: str) -> None:
    source = write_values(
        tmp_path / "readings.csv",
        [
            "1969-12-31T23:59:59.999999999Z",
            "1970-01-01T00:00:00.000000000Z",
            "1970-01-01T00:00:00.000000001Z",
            "1677-09-21T00:12:43.145224192Z",
            "2262-04-11T23:47:16.854775807Z",
        ],
    )
    config = write_job(
        tmp_path,
        {
            "value": {"db_column": "original", "type": "text"},
            None: {
                "db_column": "epoch_ns",
                "type": "bigint",
                "function": "crump.temporal.iso_to_epoch_ns",
                "input_columns": ["value"],
            },
        },
    )
    for dry in (True, False):
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code == 0, result.output
    rows = execute_query(db_url, "SELECT original, epoch_ns FROM dates ORDER BY id")
    assert [row[1] for row in rows] == [-1, 0, 1, -(2**63), 2**63 - 1]
    assert rows[0][0] == "1969-12-31T23:59:59.999999999Z"


def test_cli_temporal_key_and_filename_cleanup(
    cli_runner: CliRunner, tmp_path: Path, db_url: str
) -> None:
    config = write_job(
        tmp_path,
        {"value": {"db_column": "value", "type": "text"}},
        id_mapping={"id": {"db_column": "id", "type": "date", "datetime_format": "%d/%m/%Y"}},
        filename_to_column={
            "template": "readings_[date].csv",
            "columns": {
                "date": {
                    "db_column": "file_date",
                    "type": "date",
                    "datetime_format": "%Y%m%d",
                    "use_to_delete_old_rows": True,
                },
            },
        },
    )
    source = tmp_path / "readings_20240229.csv"
    source.write_text("id,value\n28/02/2024,old\n29/02/2024,keep\n")
    result = invoke_sync(cli_runner, source, config, db_url)
    assert result.exit_code == 0, result.output
    source.write_text("id,value\n29/02/2024,updated\n")
    preview = invoke_sync(cli_runner, source, config, db_url, True)
    assert preview.exit_code == 0, preview.output
    assert "1 stale row(s)" in preview.output
    assert execute_query(db_url, "SELECT COUNT(*) FROM dates")[0][0] == 2
    result = invoke_sync(cli_runner, source, config, db_url)
    assert result.exit_code == 0, result.output
    row = execute_query(db_url, "SELECT id, value, file_date FROM dates")[0]
    assert tuple(map(str, row)) == ("2024-02-29", "updated", "2024-02-29")


def test_cli_existing_timezone_mismatch(cli_runner: CliRunner, tmp_path: Path, db_url: str) -> None:
    if db_url.startswith("sqlite"):
        pytest.skip("PostgreSQL schema timezone check")
    source = write_values(tmp_path / "readings.csv", ["2024-02-29T12:30:00"])
    config = write_job(tmp_path, {"value": "value"})
    assert invoke_sync(cli_runner, source, config, db_url).exit_code == 0
    source = write_values(source, ["2024-02-29T12:30:00+02:00"])
    for dry in (True, False):
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code != 0
        assert "migrate it explicitly" in " ".join(result.output.split())
    assert str(execute_query(db_url, "SELECT value FROM dates")[0][0]) == "2024-02-29 12:30:00"


@pytest.mark.parametrize("value", ["12/31/2024", "12/31/2024 2:30 PM"])
def test_cli_never_infers_numeric_us(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, value: str, caplog
) -> None:
    caplog.set_level(logging.INFO)
    config = write_job(tmp_path, {"value": "value"})
    source = write_values(tmp_path / "readings.csv", [value])
    for dry in (True, False):
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code == 0, result.output
        assert not any("automatically parsing" in message for message in caplog.messages)
    assert execute_query(db_url, "SELECT value FROM dates")[0][0] == value


def test_cli_compact_checks_after_1000(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, caplog
) -> None:
    caplog.set_level(logging.INFO)
    source = write_values(tmp_path / "readings.csv", ["20240229"] * 1001 + ["21000101"])
    config = tmp_path / "prepared.yml"
    result = cli_runner.invoke(main, ["prepare", str(source), "-c", str(config)])
    assert result.exit_code == 0, result.output
    assert CrumpConfig.from_yaml(config).jobs["readings"].columns[0].data_type == "integer"
    config = write_job(tmp_path, {"value": "value"})
    result = invoke_sync(cli_runner, source, config, db_url)
    assert result.exit_code == 0, result.output
    assert not any("automatically parsing" in message for message in caplog.messages)
    assert execute_query(db_url, "SELECT value FROM dates WHERE id = 1002")[0][0] == "21000101"


def test_cli_logger_lifetime_and_file_scope(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, caplog
) -> None:
    caplog.set_level(logging.INFO)
    config = write_job(tmp_path, {"value": "value"})
    logger = logging.getLogger("crump.database")
    handlers, level = list(logger.handlers), logger.level
    propagate = logger.propagate
    for name in ("first.csv", "second.csv"):
        source = write_values(tmp_path / name, ["29/02/2024"] * 4)
        for dry in (True, False):
            caplog.clear()
            result = invoke_sync(cli_runner, source, config, db_url, dry)
            assert result.exit_code == 0, result.output
            messages = [
                message for message in caplog.messages if "automatically parsing" in message
            ]
            assert len(messages) == 1
            assert messages[0].startswith(f"{name}:")
            assert logger.handlers == handlers
            assert logger.level == level
            assert logger.propagate == propagate


@pytest.mark.parametrize("mode", ["strict", "permissive"])
def test_cli_invalid_temporal_primary_key(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, mode: str
) -> None:
    config = write_job(
        tmp_path,
        {"value": "value"},
        id_mapping={"id": {"db_column": "id", "type": "date"}},
        failure_mode=mode,
    )
    source = tmp_path / "readings.csv"
    source.write_text("id,value\n2024-02-29,valid\n2024-02-30,invalid\n")
    for dry in (True, False):
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code == 0, result.output
    assert execute_query(db_url, "SELECT COUNT(*) FROM dates")[0][0] == 1


def test_cli_all_invalid_strict_and_invalid_format_before_writes(
    cli_runner: CliRunner, tmp_path: Path, db_url: str
) -> None:
    source = write_values(tmp_path / "readings.csv", ["2024-02-30"])
    config = write_job(
        tmp_path,
        {
            "value": {
                "db_column": "value",
                "type": "date",
                "datetime_format": "%Q",
            }
        },
        failure_mode="strict",
    )
    for dry in (True, False):
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code != 0
        assert "Invalid datetime_format" in result.output
    with DatabaseConnection(db_url) as db:
        assert not db.table_exists("dates")
    config = write_job(
        tmp_path,
        {
            "value": {
                "db_column": "value",
                "type": "date",
            }
        },
        failure_mode="strict",
    )
    for dry in (True, False):
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code != 0
        assert "All 1 row(s) were rejected" in result.output


def test_documented_nanosecond_helpers(tmp_path: Path, monkeypatch) -> None:
    from tests.test_docs_examples import extract_code_blocks

    doc = Path(__file__).parent.parent / "docs" / "date-and-time.md"
    python_blocks = [
        block["content"]
        for block in extract_code_blocks(doc.read_text())
        if block["language"] == "python"
    ]
    assert len(python_blocks) == 1
    module = tmp_path / "timestamp_helpers.py"
    module.write_text(python_blocks[0])
    monkeypatch.syspath_prepend(str(tmp_path))
    mapping = ColumnMapping(
        "value",
        "ns",
        "bigint",
        function="timestamp_helpers.iso_to_epoch_ns",
        input_columns=["value"],
    )
    for value, expected in [
        ("1970-01-01T00:00:00.000000001Z", 1),
        ("1969-12-31T23:59:59.999999999Z", -1),
        ("1970-01-01T02:00:00.000000001+02:00", 1),
        ("1677-09-21T00:12:43.145224192Z", -(2**63)),
        ("2262-04-11T23:47:16.854775807Z", 2**63 - 1),
    ]:
        assert apply_row_transformations({"value": value}, [mapping])["ns"] == expected
    for value in [
        "1970-01-01T00:00:00",
        "2262-04-11T23:47:16.854775808Z",
        "2024-02-29T12:30:00.1234567890Z",
    ]:
        with pytest.raises(RuntimeError, match="Failed to execute function"):
            apply_row_transformations({"value": value}, [mapping])


def test_documented_yaml_examples(cli_runner: CliRunner, tmp_path: Path, db_url: str) -> None:
    from tests.test_docs_examples import extract_code_blocks

    doc = Path(__file__).parent.parent / "docs" / "date-and-time.md"
    configs = [
        block["content"]
        for block in extract_code_blocks(doc.read_text())
        if block["language"] == "yaml"
    ]
    sources = [
        (
            "observations.csv",
            "id,observation_date,observation_time,observed_at\n1,29/02/2024,2:30 PM,2024-02-29T14:30:45Z\n",
            "observations",
            "observed_at",
            "2024-02-29 14:30:45+00:00",
        ),
        (
            "explicit.csv",
            "id,observation_date,observation_time,observed_at,received_at,us_datetime\n"
            "1,29/02/2024,2:30 PM,29-Feb-2024 14:30:45,20240229T143045+0200,12/31/2024 2:30 PM\n",
            "explicit_observations",
            "us_datetime",
            "2024-12-31 14:30:00",
        ),
        (
            "text.csv",
            "id,observed_at\n1,2024-02-29T14:30:45.123456789Z\n",
            "precise_text",
            "observed_at_ns_text",
            "2024-02-29T14:30:45.123456789Z",
        ),
        (
            "integer.csv",
            "id,observed_at_ns\n1,-1\n2,0\n3,1\n",
            "precise_integer",
            "observed_at_epoch_ns",
            "-1",
        ),
        (
            "conversion.csv",
            "id,observed_at\n1,1969-12-31T23:59:59.999999999Z\n",
            "precise_conversion",
            "observed_at_epoch_ns",
            "-1",
        ),
    ]
    assert len(configs) == len(sources)
    for index, (config_text, (filename, contents, table, column, expected)) in enumerate(
        zip(configs, sources, strict=True)
    ):
        config = tmp_path / f"example{index}.yml"
        config.write_text(config_text)
        source = tmp_path / filename
        source.write_text(contents)
        for dry in (True, False):
            result = invoke_sync(cli_runner, source, config, db_url, dry)
            assert result.exit_code == 0, result.output
        rows = execute_query(db_url, f"SELECT {column} FROM {table} ORDER BY id")
        assert str(rows[0][0]) == expected


def test_cdf_nanoseconds_preserved(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, monkeypatch
) -> None:
    from crump.cdf_reader import read_cdf_variables

    (tmp_path / "cdf_timestamp_helpers.py").write_text(
        "from crump.temporal import iso_to_epoch_ns\n\n"
        "def cdf_utc_to_epoch_ns(value):\n"
        "    return iso_to_epoch_ns(value + 'Z')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    variables = read_cdf_variables(Path("tests/data/imap_mag_l1c_norm-magi_20251010_v001.cdf"))
    epoch = next(var for var in variables if var.name == "epoch")
    values = [str(value) for value in epoch.data[:3]]
    assert all(len(value.rsplit(".", 1)[-1]) == 9 for value in values)
    source = write_values(tmp_path / "cdf_epochs.csv", values)
    config = write_job(
        tmp_path,
        {
            "value": {"db_column": "original", "type": "text"},
            None: {
                "db_column": "ns",
                "type": "bigint",
                "function": "cdf_timestamp_helpers.cdf_utc_to_epoch_ns",
                "input_columns": ["value"],
            },
        },
    )
    for dry in (True, False):
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code == 0, result.output
    rows = execute_query(db_url, "SELECT original, ns FROM dates ORDER BY id")
    assert rows == [(value, iso_to_epoch_ns(value + "Z")) for value in values]


def test_computed_temporal_executes_once(
    cli_runner: CliRunner, tmp_path: Path, db_url: str, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)
    calls = []

    def calculate(mapping, row):
        calls.append(row["value"])
        return row["value"]

    monkeypatch.setattr(ColumnMapping, "apply_custom_function", calculate)
    config = write_job(
        tmp_path,
        {
            "value": {
                "db_column": "value",
                "type": "datetime",
                "function": "example.calculate",
                "input_columns": ["value"],
            }
        },
    )
    values = ["2024-02-29T12:30:00", "29 Feb 2024 12:31:00"]
    source = write_values(tmp_path / "readings.csv", values)
    for dry in (True, False):
        caplog.clear()
        calls.clear()
        result = invoke_sync(cli_runner, source, config, db_url, dry)
        assert result.exit_code == 0, result.output
        assert calls == values
        messages = [message for message in caplog.messages if "automatically parsing" in message]
        assert len(messages) == 1
        assert "%Y-%m-%dT%H:%M:%S" in messages[0]
        assert "%d %b %Y %H:%M:%S" in messages[0]
