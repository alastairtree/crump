# Changelog

## 0.8.0

Adds `time`, `timetz`, `timestamptz` and `datetime_format`.
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
