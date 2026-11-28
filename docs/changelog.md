# Changelog

## 0.10.0

### Added

- Automatic date/time parsing shared by `prepare`, `sync`, dry-run and configured
  extraction. See [Date and Time](date-and-time.md).
- `time`, `timetz` and `timestamptz` column types.
- Optional `datetime_format` (Python `strptime` format) on columns, primary keys and
  filename mappings.

### Changed

- Previously untyped mappings now infer temporal values automatically; other untyped
  values retain their existing TEXT storage. Compact date-like integers take precedence
  over integer inference in `prepare`. Use explicit types for identifiers.
- Numeric dates are now deterministic day-first/year-first, not PostgreSQL-dependent.
  `03/04/2024` always means 3 April; numeric US month-first dates need an explicit
  `datetime_format` such as `%m/%d/%Y`.
- SQLite temporal strings and configured extraction outputs are normalised to ISO.
- Offsets and sub-microsecond precision are no longer silently discarded or rounded.

### Upgrading

- Untyped mappings onto existing non-temporal columns (e.g. PostgreSQL `TEXT` or `BIGINT`)
  keep their raw values, so upgrading does not change how existing tables are filled.
- Crump refuses incompatible naive/aware PostgreSQL temporal columns rather than
  silently converting them. Review existing tables before changing configuration.
- Other existing column types are not automatically migrated to temporal types; create
  a new table or perform a deliberate migration after reviewing the data.

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
