# Changelog

## 0.10.0

### Added

- Automatic date and time detection. See [Dates and Times](date-and-time.md).
- `time`, `timetz` and `timestamptz` column types.
- Optional `datetime_format` (Python `strptime` format) on columns, primary keys and
  filename mappings.

### Upgrading

- Columns without a `type` may now be detected as dates or times. Existing non-temporal
  columns (e.g. PostgreSQL `TEXT` or `BIGINT`) are left as they are and keep raw values.
- `03/04/2024` always means 3 April; US month-first dates need an explicit
  `datetime_format` such as `%m/%d/%Y`.
- Crump refuses to change an existing PostgreSQL temporal column's type or timezone
  handling; migrate it explicitly.
- Date/time primary keys are stored in one canonical form. If an existing text key
  column (e.g. SQLite) holds another spelling such as `20240229`, sync stops before
  writing so rows are not duplicated; migrate the keys first.

## 0.9.0

- Accept common PostgreSQL connection string formats: `postgres://`, driver-qualified
  URLs such as `postgresql+psycopg://`, and libpq keyword/value and `service=` strings.
  Crump still uses psycopg 3 whatever driver suffix is given.

## 0.8.0

- Bounded CDF reads: `read_cdf_variables(..., max_records=N)` reads at most `N` records
  per variable, and reports unreadable variables through `skipped`.
- New public `read_cdf_global_attributes` and `group_variables_by_record_count`;
  `CDFVariable` and the CDF reading functions are exported from `crump`.
- Dependency updates (pygments, urllib3, certifi).

## Earlier versions

See the [GitHub releases](https://github.com/alastairtree/crump/releases).
