# Dates, times and nanoseconds

Crump automatically recognises common temporal formats in `prepare` and in untyped
column mappings during `sync`. An explicit `type` always overrides inference.
Configured temporal columns without `datetime_format` use the same automatic parser.
All parsing validates real calendar dates and consumes the complete value.

## Automatically recognised formats

| Kind | Examples |
|---|---|
| Year-first dates | `2024-02-29`, `2024-2-9`, `2024/02/29`, `2024.02.29` |
| Day-first dates | `29/02/2024`, `29-02-2024`, `29.02.2024` |
| Compact dates | `20240229` (see the whole-column rule below) |
| Named months, either order | `29 Feb 2024`, `29 February 2024`, `Feb 29, 2024`, `February 29, 2024` |
| Times | `14:30`, `14:30:45`, `14:30:45.123456` |
| 12-hour times | `2:30 PM`, `02:30:45 am` |
| Datetimes | `2024-02-29T14:30`, `2024-02-29 14:30:45`, `29/02/2024 14:30:45`, `29-02-2024 2:30 PM` |
| Named-month datetimes | `29 Feb 2024 14:30:45`, `Feb 29, 2024 2:30 PM` |
| Fractional datetimes | `2024-02-29T14:30:45.123456` |
| Aware datetimes | `2024-02-29T14:30:45Z`, `2024-02-29T14:30:45+02:00`, `2024-02-29T14:30:45+0200` |
| Aware times | `14:30:45+02:00` |

**Numeric month-first dates and datetimes are never detected automatically.**
`03/04/2024` always means **3 April**, regardless of PostgreSQL `DateStyle`.
`12/31/2024` and `12/31/2024 2:30 PM` require an explicit Python format.
Named-month values such as `Feb 29, 2024` are supported because the month is explicit.
Automatic English month names do not depend on the machine's locale.

Surrounding whitespace is ignored. Mixed supported formats are allowed in one column.
Mixed dates and naive datetimes become `datetime`, with dates at midnight.
Mixed naive and aware datetimes are not inferred as one temporal type: specify how
to resolve the missing timezone in a custom function first. If any value prevents
temporal inference, an untyped column keeps its non-temporal type, normally text.
Explicitly temporal columns instead validate each row.
Computed (`function`/`expression`) mappings should specify their output `type`;
Crump does not execute custom calculations during inference.

### Compact integer dates

Before inferring integers, Crump checks whether **every non-empty value in the entire
column** is an eight-digit integer between **19700101 and 20991231 inclusive**, and
is a valid `%Y%m%d` calendar date. If so, it infers `date`. This checks values beyond
row 1,000. Empty values affect nullability; entirely empty columns are not dates.

`19700101`, `20240229` and `20991231` qualify. If a numeric column also contains
`19691231`, `21000101` or invalid `20240230`, it remains numeric.
Use explicit `type: integer`, `type: bigint` or `type: text` to disable this inference.
No other integer is automatically interpreted as an epoch timestamp.

## Configuration and CLI

An untyped mapping enables automatic temporal inference:

```yaml
jobs:
  observations:
    target_table: observations
    id_mapping:
      id:
        db_column: id
        type: integer
    columns:
      observation_date: observation_date
      observation_time: observation_time
      observed_at: observed_at
```

Save this as `observations.yml` and supply `observations.csv`:

```csv
id,observation_date,observation_time,observed_at
1,29/02/2024,2:30 PM,2024-02-29T14:30:45Z
```

```bash
crump sync observations.csv -c observations.yml --db-url sqlite:///observations.db --dry-run
crump sync observations.csv -c observations.yml --db-url sqlite:///observations.db
```

Both `sync` and `sync --dry-run` print one default-visible **INFO message per
automatically parsed temporal column per source file**, listing the selected parser
formats. They do not print one message per row. Mixed-format columns list all
selected formats in a single message.
Source-column formats are reported before writes. For explicitly temporal computed
columns, formats are collected during processing and reported once at the end,
so custom functions are not executed twice.

```text
INFO: observations.csv: automatically parsing observation_date -> observation_date as date using %d/%m/%Y (numeric dates are year-first or day-first, never month-first).
```

The reported `%f` means up to six fractional digits; `%z` accepts `Z`, `+HH:MM` or
`+HHMM`. Messages show whether the actual date/time separator is a space or `T`.
Explicit `datetime_format` mappings are not reported as automatic decisions.

### Explicit Python formats

Use `datetime_format` with a temporal `type` for any format supported by Python
`datetime.strptime`. This overrides automatic parsing and is supported in regular
columns, `id_mapping` and `filename_to_column`.

```yaml
jobs:
  explicit_observations:
    target_table: explicit_observations
    id_mapping:
      id:
        db_column: id
        type: integer
    columns:
      observation_date:
        db_column: observation_date
        type: date
        datetime_format: "%d/%m/%Y"
      observation_time:
        db_column: observation_time
        type: time
        datetime_format: "%I:%M %p"
      observed_at:
        db_column: observed_at
        type: datetime
        datetime_format: "%d-%b-%Y %H:%M:%S"
      received_at:
        db_column: received_at
        type: timestamptz
        datetime_format: "%Y%m%dT%H%M%S%z"
      us_datetime:
        db_column: us_datetime
        type: datetime
        datetime_format: "%m/%d/%Y %I:%M %p"
```

For example, `us_datetime` accepts `12/31/2024 2:30 PM`; it is never inferred this way.
`%Y` is a four-digit year, `%m` a numeric month, `%d` a day, `%H` a 24-hour hour,
`%I` a 12-hour hour, `%M` minutes, `%S` seconds, `%p` AM/PM, `%b`/`%B` month names,
`%f` microseconds, and `%z` a numeric timezone offset.
Unlike automatic English-month parsing, explicit `%b`, `%B` and `%p` follow Python's
locale rules. See the [Python format directives](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes).

Custom punctuation and filename dates are supported:

```yaml
jobs:
  daily_readings:
    target_table: daily_readings
    id_mapping:
      id: id
    columns:
      captured_at:
        db_column: captured_at
        type: datetime
        datetime_format: "%Y|%m|%d %Hh%Mm%Ss"
    filename_to_column:
      template: "readings_[date].csv"
      columns:
        date:
          db_column: file_date
          type: date
          datetime_format: "%Y%m%d"
          use_to_delete_old_rows: true
```

This parses `2024|02|29 14h30m45s` and filenames such as `readings_20240229.csv`.
Temporal primary keys and filename cleanup use the same normalised values.

## Storage, timezones and validation

| Configuration type | PostgreSQL | SQLite representation |
|---|---|---|
| `date` | DATE | ISO date TEXT |
| `time` | TIME WITHOUT TIME ZONE | ISO time TEXT |
| `datetime` / `timestamp` | TIMESTAMP WITHOUT TIME ZONE | ISO naive datetime TEXT |
| `timestamptz` | TIMESTAMP WITH TIME ZONE | UTC ISO datetime TEXT with offset |
| `timetz` | TIME WITH TIME ZONE | ISO time TEXT with offset |

Automatic inference chooses aware types when offsets are present. Aware datetimes
are normalised to UTC, preserving the instant, not the original offset spelling.
PostgreSQL may display a different offset depending on its session timezone.
An offset supplied to an explicitly naive type is an error, not silently discarded.
Times with offsets retain their fixed offset; no date-dependent daylight-saving
rules are inferred. Time-only offsets must be less than 16 hours in magnitude,
matching PostgreSQL's TIMETZ range.

Normal temporal parsing supports years **1–9999** and at most **microsecond precision**.
PostgreSQL has a wider native year range, but the shared Python parser does not.
Python format strings do not extend the year range or precision.
More than six fractional digits are not silently rounded: untyped columns retain
text with a warning; explicitly temporal columns treat them as invalid.
Use the lossless options below for scientific/CDF nanoseconds.

For malformed non-empty temporal values:

| Mode | Nullable column | Non-nullable column / primary key |
|---|---|---|
| `strict` | Skip row | Skip row |
| `permissive` (default) | Store NULL | Skip row |

Warnings include a representative selected-row number, column and reason, followed
by grouped counts. If strict mode rejects every selected row, the operation fails.
Empty values retain existing behaviour: nullable fields become NULL; strict mode
skips non-nullable blanks; permissive mode uses the minimum date/datetime or midnight
for non-nullable temporal blanks. Invalid non-empty dates never become minimum dates.
Invalid format configuration is rejected before writes.

Dry-run applies the same parsing and row validation and reports eligible-row counts,
without creating tables, modifying rows or recording history.

## Lossless nanosecond storage

**PostgreSQL TIMESTAMP has microsecond precision, not nanosecond precision.**
SQLite has no native nanosecond datetime type. Use TEXT or a signed 64-bit epoch
integer for lossless storage on either backend.

### Preserve the original timestamp as TEXT

```yaml
jobs:
  precise_text:
    target_table: precise_text
    id_mapping:
      id:
        db_column: id
        type: integer
    columns:
      observed_at:
        db_column: observed_at_ns_text
        type: text
```

`2024-02-29T14:30:45.123456789Z` is preserved exactly, including fractional digits
and offset. TEXT ordering is chronological only with consistent fixed-width
timestamps and a common timezone. SQL date/time functions can lose nanoseconds.

### Store existing epoch nanoseconds as BIGINT

```yaml
jobs:
  precise_integer:
    target_table: precise_integer
    id_mapping:
      id:
        db_column: id
        type: integer
    columns:
      observed_at_ns:
        db_column: observed_at_epoch_ns
        type: bigint
```

The input contains integer nanoseconds since **1970-01-01T00:00:00Z**, not seconds
or milliseconds. PostgreSQL uses BIGINT; SQLite uses its signed 64-bit INTEGER.
Explicit `bigint` prevents all temporal inference.

The exact limits are `-9223372036854775808` through `9223372036854775807`:
`1677-09-21T00:12:43.145224192Z` through `2262-04-11T23:47:16.854775807Z`.
Negative integers represent instants before 1970. Original timezone offsets are not
retained. NumPy's `datetime64[ns]` reserves the minimum integer for `NaT`, so its
smallest valid instant is one nanosecond later.

Order and compare integers directly, without floating-point or SQL timestamp conversion:

```sql
SELECT observed_at_epoch_ns
FROM precise_integer
ORDER BY observed_at_epoch_ns;

SELECT observed_at_epoch_ns
FROM precise_integer
WHERE observed_at_epoch_ns >= 0 AND observed_at_epoch_ns < 1000000000;
```

The second query selects instants in the first second of 1970. Subtraction is exact
only while the result fits the backend's integer range; SQLite can promote an
overflowing subtraction to REAL. Use Python integers for arbitrary-range differences.

### Convert ISO timestamp strings without losing digits

Crump supplies the tested helper `crump.temporal.iso_to_epoch_ns`. It requires an
explicit offset, accepts up to nine fractional digits and checks signed 64-bit bounds.
It uses integer arithmetic, never floating-point `timestamp() * 1e9`.

```yaml
jobs:
  precise_conversion:
    target_table: precise_conversion
    id_mapping:
      id:
        db_column: id
        type: integer
    columns:
      observed_at:
        db_column: observed_at_epoch_ns
        type: bigint
        function: crump.temporal.iso_to_epoch_ns
        input_columns:
          - observed_at
```

For example, `1969-12-31T23:59:59.999999999Z` becomes `-1`, and
`1970-01-01T00:00:00.000000001Z` becomes `1`. Invalid inputs or overflow raise an
explicit custom-function error in both sync and dry-run.

The complete helper, also usable as `timestamp_helpers.py`, is:

```python
import re
from datetime import datetime, timezone


def iso_to_epoch_ns(value: str) -> int:
    """Convert an offset-aware ISO timestamp to signed 64-bit epoch nanoseconds."""
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?"
        r"(Z|[+-]\d{2}:?\d{2})", value.strip()
    )
    if match is None:
        raise ValueError("expected an ISO datetime with an explicit UTC offset and <=9 fractional digits")
    base, fraction, offset = match.groups()
    parsed = datetime.strptime(base.replace(" ", "T") + offset, "%Y-%m-%dT%H:%M:%S%z")
    delta = parsed.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    result = (delta.days * 86400 + delta.seconds) * 1_000_000_000
    result += int((fraction or "").ljust(9, "0"))
    if not -(2**63) <= result <= 2**63 - 1:
        raise ValueError("epoch nanoseconds exceed signed 64-bit range")
    return result
```

To customise it, save the module in an importable directory, add that directory to
`PYTHONPATH`, and change the YAML function to `timestamp_helpers.iso_to_epoch_ns`.
The built-in helper needs no additional module or dependency.

CDF-extracted timestamps can have nine fractional digits without an offset. TEXT
storage preserves them. For epoch conversion, append `Z` in a custom helper **only
if the source time convention is known to be UTC**:

```python
from crump.temporal import iso_to_epoch_ns


def cdf_utc_to_epoch_ns(value: str) -> int:
    return iso_to_epoch_ns(value + "Z")
```

Save this as `timestamp_helpers.py` on `PYTHONPATH`, set
`function: timestamp_helpers.cdf_utc_to_epoch_ns`, and select the CDF timestamp
column in `input_columns`. Do not assume a timezone for general CSV timestamps.

## Upgrading from 0.7

Version 0.8 adds `time`, `timetz`, `timestamptz` and `datetime_format`.
Previously untyped mappings now infer temporal values automatically; other untyped
values retain their existing TEXT storage. Compact date-like integers take precedence
over integer inference in `prepare`. Use explicit types for identifiers.

Numeric dates are now deterministic day-first/year-first, not PostgreSQL-dependent.
SQLite temporal strings and configured extraction outputs are normalised to ISO.
Offsets and sub-microsecond precision are no longer silently discarded or rounded.
Review existing tables before changing configuration: Crump refuses incompatible
naive/aware PostgreSQL temporal columns rather than silently converting them.
Other existing column types are not automatically migrated to temporal types; create
a new table or perform a deliberate migration after reviewing the data.
