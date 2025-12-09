"""Database operations for crump."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg import sql

from crump.config import CrumpJob, apply_row_transformations
from crump.tabular_file import create_reader


def _detect_file_format(file_path: Path) -> Any:
    """Detect file format from extension for tabular files.

    Args:
        file_path: Path to the file

    Returns:
        InputFileType enum value (CSV or PARQUET only, defaults to CSV for unknown extensions)

    Note:
        This function only detects CSV and Parquet formats since those are the
        formats supported by the tabular file reader. CDF files are not directly
        syncable and must be extracted first.
    """
    from crump.file_types import InputFileType

    try:
        file_type = InputFileType.from_path(str(file_path))
        # Only return CSV or PARQUET; treat everything else (including CDF) as CSV
        if file_type == InputFileType.PARQUET:
            return InputFileType.PARQUET
        else:
            return InputFileType.CSV
    except ValueError:
        # Unknown extension, default to CSV
        return InputFileType.CSV


logger = logging.getLogger(__name__)


class DryRunSummary:
    """Summary of changes that would be made during a dry-run sync."""

    def __init__(self) -> None:
        """Initialize dry-run summary."""
        self.table_name: str = ""
        self.table_exists: bool = False
        self.new_columns: list[tuple[str, str]] = []
        self.new_indexes: list[str] = []
        self.rows_to_sync: int = 0
        self.rows_to_delete: int = 0


class DatabaseBackend(Protocol):
    """Protocol for database backend operations."""

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        """Execute a query."""
        ...

    def fetchall(self, query: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        """Fetch all results from a query."""
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...

    def map_data_type(self, data_type: str | None) -> str:
        """Map config data type to SQL database type."""
        ...

    def create_table_if_not_exists(
        self, table_name: str, columns: dict[str, str], primary_keys: list[str] | None = None
    ) -> None:
        """Create table if it doesn't exist."""
        ...

    def get_existing_columns(self, table_name: str) -> set[str]:
        """Get set of existing column names in a table."""
        ...

    def add_column(self, table_name: str, column_name: str, column_type: str) -> None:
        """Add a new column to an existing table."""
        ...

    def upsert_row(
        self, table_name: str, conflict_columns: list[str], row_data: dict[str, Any]
    ) -> None:
        """Upsert a row into the database."""
        ...

    def delete_stale_records_compound(
        self,
        table_name: str,
        id_columns: list[str],
        filter_columns: dict[str, str],
        current_ids: set[tuple],
    ) -> int:
        """Delete records from database that aren't in current CSV using compound filter key."""
        ...

    def count_stale_records_compound(
        self,
        table_name: str,
        id_columns: list[str],
        filter_columns: dict[str, str],
        current_ids: set[tuple],
    ) -> int:
        """Count records that would be deleted using compound filter key."""
        ...

    def get_existing_indexes(self, table_name: str) -> set[str]:
        """Get set of existing index names for a table."""
        ...

    def create_index(
        self, table_name: str, index_name: str, columns: list[tuple[str, str]]
    ) -> None:
        """Create an index on the specified columns.

        Args:
            table_name: Name of the table
            index_name: Name of the index to create
            columns: List of (column_name, order) tuples, e.g. [('email', 'ASC'), ('date', 'DESC')]
        """
        ...

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        ...


class PostgreSQLBackend:
    """PostgreSQL database backend."""

    def __init__(self, connection_string: str) -> None:
        """Initialize PostgreSQL connection."""
        self.conn = psycopg.connect(connection_string)

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        """Execute a query."""
        with self.conn.cursor() as cur:
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)

    def fetchall(self, query: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        """Fetch all results from a query."""
        with self.conn.cursor() as cur:
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            return cur.fetchall()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.conn.commit()

    def close(self) -> None:
        """Close the connection."""
        self.conn.close()

    def map_data_type(self, data_type: str | None) -> str:
        """Map config data type to PostgreSQL type."""
        if data_type is None:
            return "TEXT"

        data_type_lower = data_type.lower().strip()

        # Check for varchar(N) pattern
        if data_type_lower.startswith("varchar"):
            return data_type.upper()  # VARCHAR(N)

        # Map other types
        type_mapping = {
            "integer": "INTEGER",
            "int": "INTEGER",
            "bigint": "BIGINT",
            "float": "DOUBLE PRECISION",
            "double": "DOUBLE PRECISION",
            "date": "DATE",
            "datetime": "TIMESTAMP",
            "timestamp": "TIMESTAMP",
            "text": "TEXT",
            "string": "TEXT",
        }

        return type_mapping.get(data_type_lower, "TEXT")

    def create_table_if_not_exists(
        self, table_name: str, columns: dict[str, str], primary_keys: list[str] | None = None
    ) -> None:
        """Create table if it doesn't exist."""
        column_defs = []
        for col_name, col_type in columns.items():
            column_defs.append(sql.SQL("{} {}").format(sql.Identifier(col_name), sql.SQL(col_type)))

        # Add primary key constraint if specified
        if primary_keys:
            pk_constraint = sql.SQL("PRIMARY KEY ({})").format(
                sql.SQL(", ").join(sql.Identifier(pk) for pk in primary_keys)
            )
            column_defs.append(pk_constraint)

        query = sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
            sql.Identifier(table_name), sql.SQL(", ").join(column_defs)
        )
        self.execute(query.as_string(self.conn))
        self.commit()

    def get_existing_columns(self, table_name: str) -> set[str]:
        """Get set of existing column names in a table.

        Uses case-insensitive comparison to handle quoted identifiers that preserve case.
        """
        query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE LOWER(table_name) = LOWER(%s)
        """
        results = self.fetchall(query, (table_name,))
        return {row[0].lower() for row in results}

    def add_column(self, table_name: str, column_name: str, column_type: str) -> None:
        """Add a new column to an existing table."""
        query = sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
            sql.Identifier(table_name),
            sql.Identifier(column_name),
            sql.SQL(column_type),
        )
        self.execute(query.as_string(self.conn))
        self.commit()

    def upsert_row(
        self, table_name: str, conflict_columns: list[str], row_data: dict[str, Any]
    ) -> None:
        """Upsert a row into the database."""
        columns = list(row_data.keys())
        values = tuple(row_data.values())

        insert_query = sql.SQL(
            "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}"
        ).format(
            sql.Identifier(table_name),
            sql.SQL(", ").join(sql.Identifier(col) for col in columns),
            sql.SQL(", ").join(sql.Placeholder() * len(values)),
            sql.SQL(", ").join(sql.Identifier(col) for col in conflict_columns),
            sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(col), sql.Identifier(col))
                for col in columns
                if col not in conflict_columns
            ),
        )
        self.execute(insert_query.as_string(self.conn), values)
        self.commit()

    def count_stale_records_compound(
        self,
        table_name: str,
        id_columns: list[str],
        filter_columns: dict[str, str],
        current_ids: set[tuple],
    ) -> int:
        """Count records that would be deleted using compound filter key.

        Args:
            table_name: Name of the table
            id_columns: List of ID column names (for compound keys)
            filter_columns: Dictionary of column_name -> value to filter by (compound key)
            current_ids: Set of ID tuples from the current CSV

        Returns:
            Count of records that would be deleted
        """
        if not current_ids or not filter_columns:
            return 0

        # Build WHERE clause: WHERE col1 = ? AND col2 = ? AND (id1, id2) NOT IN (...)
        filter_conditions = [
            sql.SQL("{} = %s").format(sql.Identifier(col)) for col in filter_columns
        ]

        if len(id_columns) == 1:
            # Single key - simpler query
            current_ids_list = [
                id_val[0] if isinstance(id_val, tuple) else id_val for id_val in current_ids
            ]
            count_query = sql.SQL("SELECT COUNT(*) FROM {} WHERE {} AND {} NOT IN ({})").format(
                sql.Identifier(table_name),
                sql.SQL(" AND ").join(filter_conditions),
                sql.Identifier(id_columns[0]),
                sql.SQL(", ").join(sql.Placeholder() * len(current_ids_list)),
            )
            params = tuple(list(filter_columns.values()) + current_ids_list)
        else:
            # Compound key - use row value constructor
            id_cols_sql = sql.SQL("({})").format(
                sql.SQL(", ").join(sql.Identifier(col) for col in id_columns)
            )
            placeholders = sql.SQL(", ").join(
                sql.SQL("({})").format(sql.SQL(", ").join(sql.Placeholder() * len(id_columns)))
                for _ in current_ids
            )
            count_query = sql.SQL("SELECT COUNT(*) FROM {} WHERE {} AND {} NOT IN ({})").format(
                sql.Identifier(table_name),
                sql.SQL(" AND ").join(filter_conditions),
                id_cols_sql,
                placeholders,
            )
            # Flatten the list of tuples for params
            id_params = [val for id_tuple in current_ids for val in id_tuple]
            params = tuple(list(filter_columns.values()) + id_params)

        count_result = self.fetchall(count_query.as_string(self.conn), params)
        return count_result[0][0] if count_result else 0

    def delete_stale_records_compound(
        self,
        table_name: str,
        id_columns: list[str],
        filter_columns: dict[str, str],
        current_ids: set[tuple],
    ) -> int:
        """Delete records from database that aren't in current CSV using compound filter key.

        Args:
            table_name: Name of the table
            id_columns: List of ID column names (for compound keys)
            filter_columns: Dictionary of column_name -> value to filter by (compound key)
            current_ids: Set of ID tuples from the current CSV

        Returns:
            Count of records deleted
        """
        if not current_ids or not filter_columns:
            return 0

        # Build WHERE clause: WHERE col1 = ? AND col2 = ? AND (id1, id2) NOT IN (...)
        filter_conditions = [
            sql.SQL("{} = %s").format(sql.Identifier(col)) for col in filter_columns
        ]

        if len(id_columns) == 1:
            # Single key - simpler query
            current_ids_list = [
                id_val[0] if isinstance(id_val, tuple) else id_val for id_val in current_ids
            ]
            count_query = sql.SQL("SELECT COUNT(*) FROM {} WHERE {} AND {} NOT IN ({})").format(
                sql.Identifier(table_name),
                sql.SQL(" AND ").join(filter_conditions),
                sql.Identifier(id_columns[0]),
                sql.SQL(", ").join(sql.Placeholder() * len(current_ids_list)),
            )
            delete_query = sql.SQL("DELETE FROM {} WHERE {} AND {} NOT IN ({})").format(
                sql.Identifier(table_name),
                sql.SQL(" AND ").join(filter_conditions),
                sql.Identifier(id_columns[0]),
                sql.SQL(", ").join(sql.Placeholder() * len(current_ids_list)),
            )
            params = tuple(list(filter_columns.values()) + current_ids_list)
        else:
            # Compound key - use row value constructor
            id_cols_sql = sql.SQL("({})").format(
                sql.SQL(", ").join(sql.Identifier(col) for col in id_columns)
            )
            placeholders = sql.SQL(", ").join(
                sql.SQL("({})").format(sql.SQL(", ").join(sql.Placeholder() * len(id_columns)))
                for _ in current_ids
            )
            count_query = sql.SQL("SELECT COUNT(*) FROM {} WHERE {} AND {} NOT IN ({})").format(
                sql.Identifier(table_name),
                sql.SQL(" AND ").join(filter_conditions),
                id_cols_sql,
                placeholders,
            )
            delete_query = sql.SQL("DELETE FROM {} WHERE {} AND {} NOT IN ({})").format(
                sql.Identifier(table_name),
                sql.SQL(" AND ").join(filter_conditions),
                id_cols_sql,
                placeholders,
            )
            # Flatten the list of tuples for params
            id_params = [val for id_tuple in current_ids for val in id_tuple]
            params = tuple(list(filter_columns.values()) + id_params)

        # Count first
        count_sql = count_query.as_string(self.conn)
        logger.debug(f"PostgreSQL count query: {count_sql}")
        logger.debug(f"PostgreSQL count params: {params}")
        count_result = self.fetchall(count_sql, params)
        deleted_count = count_result[0][0] if count_result else 0

        # Then delete
        delete_sql = delete_query.as_string(self.conn)
        logger.debug(f"PostgreSQL delete query: {delete_sql}")
        logger.debug(f"PostgreSQL delete params: {params}")
        logger.debug(f"PostgreSQL deleted count: {deleted_count}")
        self.execute(delete_sql, params)
        self.commit()

        return deleted_count

    def get_existing_indexes(self, table_name: str) -> set[str]:
        """Get set of existing index names for a table.

        Uses case-insensitive comparison to handle quoted identifiers that preserve case.
        """
        query = """
            SELECT indexname
            FROM pg_indexes
            WHERE LOWER(tablename) = LOWER(%s)
        """
        results = self.fetchall(query, (table_name,))
        return {row[0].lower() for row in results}

    def create_index(
        self, table_name: str, index_name: str, columns: list[tuple[str, str]]
    ) -> None:
        """Create an index on the specified columns."""
        # Build column list with order
        column_parts = []
        for col_name, order in columns:
            column_parts.append(sql.SQL("{} {}").format(sql.Identifier(col_name), sql.SQL(order)))

        query = sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(
            sql.Identifier(index_name),
            sql.Identifier(table_name),
            sql.SQL(", ").join(column_parts),
        )

        self.execute(query.as_string(self.conn))
        self.commit()

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database.

        Uses case-insensitive comparison to handle quoted identifiers that preserve case.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE LOWER(table_name) = LOWER(%s)
            )
        """
        result = self.fetchall(query, (table_name,))
        return result[0][0] if result else False


class SQLiteBackend:
    """SQLite database backend."""

    def __init__(self, connection_string: str) -> None:
        """Initialize SQLite connection."""
        # Extract database path from connection string
        # Supports: sqlite:///path/to/db.db or sqlite:///:memory:
        if connection_string.startswith("sqlite:///"):
            db_path = connection_string[10:]  # Remove 'sqlite:///'
        elif connection_string.startswith("sqlite://"):
            db_path = connection_string[9:]  # Remove 'sqlite://'
        else:
            db_path = connection_string

        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        """Execute a query."""
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)

    def fetchall(self, query: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        """Fetch all results from a query."""
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        return self.cursor.fetchall()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.conn.commit()

    def close(self) -> None:
        """Close the connection."""
        self.cursor.close()
        self.conn.close()

    def map_data_type(self, data_type: str | None) -> str:
        """Map config data type to SQLite type."""
        if data_type is None:
            return "TEXT"

        data_type_lower = data_type.lower().strip()

        # SQLite doesn't have VARCHAR, use TEXT
        if data_type_lower.startswith("varchar"):
            return "TEXT"

        # Map other types
        type_mapping = {
            "integer": "INTEGER",
            "int": "INTEGER",
            "bigint": "INTEGER",  # SQLite INTEGER is 8-byte signed, equivalent to BIGINT
            "float": "REAL",
            "double": "REAL",
            "date": "TEXT",
            "datetime": "TEXT",
            "timestamp": "TEXT",
            "text": "TEXT",
            "string": "TEXT",
        }

        return type_mapping.get(data_type_lower, "TEXT")

    def create_table_if_not_exists(
        self, table_name: str, columns: dict[str, str], primary_keys: list[str] | None = None
    ) -> None:
        """Create table if it doesn't exist."""
        column_defs_str = ", ".join(
            f'"{col_name}" {col_type}' for col_name, col_type in columns.items()
        )

        # Add primary key constraint if specified
        if primary_keys:
            pk_columns = ", ".join(f'"{pk}"' for pk in primary_keys)
            column_defs_str += f", PRIMARY KEY ({pk_columns})"

        query = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({column_defs_str})'
        self.execute(query)
        self.commit()

    def get_existing_columns(self, table_name: str) -> set[str]:
        """Get set of existing column names in a table."""
        query = f'PRAGMA table_info("{table_name}")'
        results = self.fetchall(query)
        # PRAGMA table_info returns: (cid, name, type, notnull, dflt_value, pk)
        return {row[1].lower() for row in results}

    def add_column(self, table_name: str, column_name: str, column_type: str) -> None:
        """Add a new column to an existing table."""
        query = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'
        self.execute(query)
        self.commit()

    def upsert_row(
        self, table_name: str, conflict_columns: list[str], row_data: dict[str, Any]
    ) -> None:
        """Upsert a row into the database."""
        columns = list(row_data.keys())
        values = tuple(row_data.values())

        columns_str = ", ".join(f'"{col}"' for col in columns)
        placeholders = ", ".join("?" * len(values))
        update_str = ", ".join(
            f'"{col}" = excluded."{col}"' for col in columns if col not in conflict_columns
        )

        # SQLite ON CONFLICT clause with multiple columns
        conflict_cols_str = ", ".join(f'"{col}"' for col in conflict_columns)

        query = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders}) '
        query += f"ON CONFLICT ({conflict_cols_str}) DO UPDATE SET {update_str}"

        self.execute(query, values)
        self.commit()

    def get_existing_indexes(self, table_name: str) -> set[str]:
        """Get set of existing index names for a table."""
        query = "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?"
        results = self.fetchall(query, (table_name,))
        return {row[0].lower() for row in results}

    def create_index(
        self, table_name: str, index_name: str, columns: list[tuple[str, str]]
    ) -> None:
        """Create an index on the specified columns."""
        # Build column list with order
        column_parts = []
        for col_name, order in columns:
            column_parts.append(f'"{col_name}" {order}')

        columns_str = ", ".join(column_parts)
        query = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({columns_str})'

        self.execute(query)
        self.commit()

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        result = self.fetchall(query, (table_name,))
        return len(result) > 0

    def delete_stale_records_compound(
        self,
        table_name: str,
        id_columns: list[str],
        filter_columns: dict[str, str],
        current_ids: set[tuple],
    ) -> int:
        """Delete records from database that aren't in current CSV using compound filter key.

        Args:
            table_name: Name of the table
            id_columns: List of ID column names (for compound keys)
            filter_columns: Dictionary of column_name -> value to filter by (compound key)
            current_ids: Set of ID tuples from the current CSV

        Returns:
            Count of records deleted
        """
        if not current_ids or not filter_columns:
            return 0

        # Build WHERE clause: WHERE col1 = ? AND col2 = ? AND (id1, id2) NOT IN (...)
        filter_conditions = [f'"{col}" = ?' for col in filter_columns]

        if len(id_columns) == 1:
            # Single key - simpler query
            current_ids_list = [
                id_val[0] if isinstance(id_val, tuple) else id_val for id_val in current_ids
            ]
            placeholders = ", ".join("?" * len(current_ids_list))
            count_query = f"""
                SELECT COUNT(*) FROM "{table_name}"
                WHERE {" AND ".join(filter_conditions)}
                AND "{id_columns[0]}" NOT IN ({placeholders})
            """
            delete_query = f"""
                DELETE FROM "{table_name}"
                WHERE {" AND ".join(filter_conditions)}
                AND "{id_columns[0]}" NOT IN ({placeholders})
            """
            params = tuple(list(filter_columns.values()) + current_ids_list)
        else:
            # Compound key - use row value constructor
            quoted_cols = [f'"{col}"' for col in id_columns]
            id_cols = f"({', '.join(quoted_cols)})"
            placeholders = ", ".join(f"({', '.join('?' * len(id_columns))})" for _ in current_ids)
            count_query = f"""
                SELECT COUNT(*) FROM "{table_name}"
                WHERE {" AND ".join(filter_conditions)}
                AND {id_cols} NOT IN ({placeholders})
            """
            delete_query = f"""
                DELETE FROM "{table_name}"
                WHERE {" AND ".join(filter_conditions)}
                AND {id_cols} NOT IN ({placeholders})
            """
            # Flatten the list of tuples for params
            id_params = [val for id_tuple in current_ids for val in id_tuple]
            params = tuple(list(filter_columns.values()) + id_params)

        # Count first
        logger.debug(f"SQLite count query: {count_query}")
        logger.debug(f"SQLite count params: {params}")
        count_result = self.fetchall(count_query, params)
        deleted_count = count_result[0][0] if count_result else 0

        # Delete stale records
        logger.debug(f"SQLite delete query: {delete_query}")
        logger.debug(f"SQLite delete params: {params}")
        logger.debug(f"SQLite deleted count: {deleted_count}")
        self.execute(delete_query, params)
        self.commit()

        return deleted_count

    def count_stale_records_compound(
        self,
        table_name: str,
        id_columns: list[str],
        filter_columns: dict[str, str],
        current_ids: set[tuple],
    ) -> int:
        """Count records that would be deleted using compound filter key.

        Args:
            table_name: Name of the table
            id_columns: List of ID column names (for compound keys)
            filter_columns: Dictionary of column_name -> value to filter by (compound key)
            current_ids: Set of ID tuples from the current CSV

        Returns:
            Count of records that would be deleted
        """
        if not current_ids or not filter_columns:
            return 0

        # Build WHERE clause: WHERE col1 = ? AND col2 = ? AND (id1, id2) NOT IN (...)
        filter_conditions = [f'"{col}" = ?' for col in filter_columns]

        if len(id_columns) == 1:
            # Single key - simpler query
            current_ids_list = [
                id_val[0] if isinstance(id_val, tuple) else id_val for id_val in current_ids
            ]
            placeholders = ", ".join("?" * len(current_ids_list))
            count_query = f"""
                SELECT COUNT(*) FROM "{table_name}"
                WHERE {" AND ".join(filter_conditions)}
                AND "{id_columns[0]}" NOT IN ({placeholders})
            """
            params = tuple(list(filter_columns.values()) + current_ids_list)
        else:
            # Compound key - use row value constructor
            quoted_cols = [f'"{col}"' for col in id_columns]
            id_cols = f"({', '.join(quoted_cols)})"
            placeholders = ", ".join(f"({', '.join('?' * len(id_columns))})" for _ in current_ids)
            count_query = f"""
                SELECT COUNT(*) FROM "{table_name}"
                WHERE {" AND ".join(filter_conditions)}
                AND {id_cols} NOT IN ({placeholders})
            """
            # Flatten the list of tuples for params
            id_params = [val for id_tuple in current_ids for val in id_tuple]
            params = tuple(list(filter_columns.values()) + id_params)

        count_result = self.fetchall(count_query, params)
        return count_result[0][0] if count_result else 0


class DatabaseConnection:
    """Database connection handler supporting PostgreSQL and SQLite."""

    def __init__(self, connection_string: str) -> None:
        """Initialize database connection.

        Args:
            connection_string: Database connection string
                - PostgreSQL: postgresql://user:pass@host:port/db
                - SQLite: sqlite:///path/to/db.db or sqlite:///:memory:
        """
        self.connection_string = connection_string
        self.backend: DatabaseBackend | None = None

    def __enter__(self) -> DatabaseConnection:
        """Enter context manager."""
        if self.connection_string.startswith("sqlite"):
            self.backend = SQLiteBackend(self.connection_string)
        elif self.connection_string.startswith("postgres"):
            self.backend = PostgreSQLBackend(self.connection_string)
        else:
            raise ValueError(
                f"Unsupported database type in connection string: {self.connection_string}"
            )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        if self.backend:
            self.backend.close()

    def create_table_if_not_exists(
        self, table_name: str, columns: dict[str, str], primary_keys: list[str] | None = None
    ) -> None:
        """Create table if it doesn't exist."""
        if not self.backend:
            raise RuntimeError("Database connection not established")
        self.backend.create_table_if_not_exists(table_name, columns, primary_keys)

    def get_existing_columns(self, table_name: str) -> set[str]:
        """Get set of existing column names in a table."""
        if not self.backend:
            raise RuntimeError("Database connection not established")
        return self.backend.get_existing_columns(table_name)

    def add_column(self, table_name: str, column_name: str, column_type: str) -> None:
        """Add a new column to an existing table."""
        if not self.backend:
            raise RuntimeError("Database connection not established")
        self.backend.add_column(table_name, column_name, column_type)

    def upsert_row(
        self, table_name: str, conflict_columns: list[str], row_data: dict[str, Any]
    ) -> None:
        """Upsert a row into the database."""
        if not self.backend:
            raise RuntimeError("Database connection not established")
        self.backend.upsert_row(table_name, conflict_columns, row_data)

    def delete_stale_records_compound(
        self,
        table_name: str,
        id_columns: list[str],
        filter_columns: dict[str, str],
        current_ids: set[tuple],
    ) -> int:
        """Delete records from database that aren't in current CSV using compound filter key."""
        if not self.backend:
            raise RuntimeError("Database connection not established")
        return self.backend.delete_stale_records_compound(
            table_name, id_columns, filter_columns, current_ids
        )

    def count_stale_records_compound(
        self,
        table_name: str,
        id_columns: list[str],
        filter_columns: dict[str, str],
        current_ids: set[tuple],
    ) -> int:
        """Count records that would be deleted using compound filter key."""
        if not self.backend:
            raise RuntimeError("Database connection not established")
        return self.backend.count_stale_records_compound(
            table_name, id_columns, filter_columns, current_ids
        )

    def get_existing_indexes(self, table_name: str) -> set[str]:
        """Get set of existing index names for a table."""
        if not self.backend:
            raise RuntimeError("Database connection not established")
        return self.backend.get_existing_indexes(table_name)

    def create_index(
        self, table_name: str, index_name: str, columns: list[tuple[str, str]]
    ) -> None:
        """Create an index on the specified columns."""
        if not self.backend:
            raise RuntimeError("Database connection not established")
        self.backend.create_index(table_name, index_name, columns)

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        if not self.backend:
            raise RuntimeError("Database connection not established")
        return self.backend.table_exists(table_name)

    def _validate_id_columns(self, job: CrumpJob, csv_columns: set[str]) -> set[str]:
        """Validate that required ID columns exist in CSV.

        Args:
            job: CrumpJob configuration
            csv_columns: Set of column names from CSV

        Returns:
            Set of ID column names from CSV

        Raises:
            ValueError: If any ID column is missing from CSV
        """
        id_csv_columns = set()
        for id_col in job.id_mapping:
            # Skip validation for custom functions (no csv_column)
            if id_col.csv_column is None:
                # Custom function - validate input columns instead
                if id_col.input_columns:
                    for input_col in id_col.input_columns:
                        if input_col not in csv_columns:
                            raise ValueError(
                                f"Input column '{input_col}' for custom function "
                                f"'{id_col.db_column}' not found in CSV"
                            )
                continue

            if id_col.csv_column not in csv_columns:
                raise ValueError(f"ID column '{id_col.csv_column}' not found in CSV")
            id_csv_columns.add(id_col.csv_column)
        return id_csv_columns

    def _determine_sync_columns(
        self, job: CrumpJob, csv_columns: set[str], id_csv_columns: set[str]
    ) -> list[Any]:
        """Determine which columns to sync based on job configuration.

        Args:
            job: CrumpJob configuration
            csv_columns: Set of column names from CSV
            id_csv_columns: Set of ID column names

        Returns:
            List of ColumnMapping objects for columns to sync

        Raises:
            ValueError: If a configured column is missing from CSV
        """
        if job.columns:
            # Specific columns defined
            sync_columns = list(job.id_mapping) + job.columns
            for col_mapping in job.columns:
                # Skip validation for custom functions (no csv_column)
                if col_mapping.csv_column is None:
                    # Custom function - validate input columns instead
                    if col_mapping.input_columns:
                        for input_col in col_mapping.input_columns:
                            if input_col not in csv_columns:
                                raise ValueError(
                                    f"Input column '{input_col}' for custom function "
                                    f"'{col_mapping.db_column}' not found in CSV"
                                )
                    continue

                if col_mapping.csv_column not in csv_columns:
                    raise ValueError(f"Column '{col_mapping.csv_column}' not found in CSV")
        else:
            # Sync all columns
            from crump.config import ColumnMapping

            sync_columns = list(job.id_mapping)
            for csv_col in csv_columns:
                if csv_col not in id_csv_columns:
                    sync_columns.append(ColumnMapping(csv_col, csv_col))

        return sync_columns

    def _build_column_definitions(self, sync_columns: list[Any], job: CrumpJob) -> dict[str, str]:
        """Build column definitions with SQL types and nullable constraints.

        Args:
            sync_columns: List of ColumnMapping objects
            job: CrumpJob configuration

        Returns:
            Dictionary mapping column names to SQL type definitions (including NULL/NOT NULL)
        """
        if not self.backend:
            raise RuntimeError("Database connection not established")
        columns_def = {}
        for col_mapping in sync_columns:
            sql_type = self.backend.map_data_type(col_mapping.data_type)

            # Add nullable constraint if specified
            if col_mapping.nullable is not None:
                if col_mapping.nullable:
                    sql_type += " NULL"
                else:
                    sql_type += " NOT NULL"

            columns_def[col_mapping.db_column] = sql_type

        # Add filename_to_column columns if configured
        if job.filename_to_column:
            for col_mapping in job.filename_to_column.columns.values():
                sql_type = self.backend.map_data_type(col_mapping.data_type)
                columns_def[col_mapping.db_column] = sql_type

        return columns_def

    def _setup_table_schema(
        self, job: CrumpJob, columns_def: dict[str, str], primary_keys: list[str]
    ) -> bool:
        """Create table and add missing columns/indexes.

        Args:
            job: CrumpJob configuration
            columns_def: Dictionary mapping column names to SQL types
            primary_keys: List of primary key column names

        Returns:
            True if schema changes were made (table created, columns added, or indexes created)
        """
        schema_changed = False

        # Check if table exists before creating
        table_existed = self.table_exists(job.target_table)

        # Create table if it doesn't exist
        self.create_table_if_not_exists(job.target_table, columns_def, primary_keys)

        if not table_existed:
            schema_changed = True

        # Check for schema evolution: add missing columns from config
        existing_columns = self.get_existing_columns(job.target_table)
        for col_name, col_type in columns_def.items():
            if col_name.lower() not in existing_columns:
                self.add_column(job.target_table, col_name, col_type)
                schema_changed = True

        # Create indexes that don't already exist
        if job.indexes:
            existing_indexes = self.get_existing_indexes(job.target_table)
            for index in job.indexes:
                if index.name.lower() not in existing_indexes:
                    index_columns = [(col.column, col.order) for col in index.columns]
                    self.create_index(job.target_table, index.name, index_columns)
                    schema_changed = True

        return schema_changed

    def _should_include_row(
        self, row_index: int, total_rows: int, sample_percentage: float | None
    ) -> bool:
        """Determine if a row should be included based on sampling percentage.

        Args:
            row_index: Zero-based index of the current row
            total_rows: Total number of rows in the dataset
            sample_percentage: Optional percentage of rows to sample (0-100)

        Returns:
            True if row should be included, False otherwise
        """
        # If no sampling or 100%, include all rows
        if sample_percentage is None or sample_percentage >= 100:
            return True

        # If 0%, exclude all rows (edge case)
        if sample_percentage <= 0:
            return False

        # Always include first row
        if row_index == 0:
            return True

        # Always include last row
        if row_index == total_rows - 1:
            return True

        # Sample other rows based on percentage
        # For 10%, interval = 10, so include rows 0, 10, 20, 30...
        # For 25%, interval = 4, so include rows 0, 4, 8, 12...
        interval = int(100 / sample_percentage)
        return row_index % interval == 0

    def _process_tabular_rows(
        self,
        reader: Any,
        job: CrumpJob,
        sync_columns: list[Any],
        primary_keys: list[str],
        filename_values: dict[str, str] | None = None,
    ) -> tuple[int, set[tuple]]:
        """Process and upsert tabular file rows into database.

        Args:
            reader: Tabular file reader (DictReader interface)
            job: CrumpJob configuration
            sync_columns: List of ColumnMapping objects
            primary_keys: List of primary key column names
            filename_values: Optional dict of values extracted from filename

        Returns:
            Tuple of (rows_synced, synced_ids) where synced_ids are tuples of ID values
        """
        rows_synced = 0
        synced_ids: set[tuple] = set()

        # For sampling, we need to know total row count first
        if job.sample_percentage is not None and job.sample_percentage < 100:
            # Read all rows into memory to get total count and apply sampling
            all_rows = list(reader)
            total_rows = len(all_rows)

            for row_index, row in enumerate(all_rows):
                # Check if this row should be included
                if not self._should_include_row(row_index, total_rows, job.sample_percentage):
                    continue

                # Apply column transformations
                row_data = apply_row_transformations(
                    row, sync_columns, job.filename_to_column, filename_values
                )

                self.upsert_row(job.target_table, primary_keys, row_data)

                # Track synced IDs as tuples (for compound key support)
                id_values = tuple(row_data[id_col.db_column] for id_col in job.id_mapping)
                synced_ids.add(id_values)
                rows_synced += 1
        else:
            # No sampling - process rows normally without loading into memory
            for row in reader:
                # Apply column transformations
                row_data = apply_row_transformations(
                    row, sync_columns, job.filename_to_column, filename_values
                )

                self.upsert_row(job.target_table, primary_keys, row_data)

                # Track synced IDs as tuples (for compound key support)
                id_values = tuple(row_data[id_col.db_column] for id_col in job.id_mapping)
                synced_ids.add(id_values)
                rows_synced += 1

        return rows_synced, synced_ids

    def _count_and_track_tabular_rows(
        self,
        file_path: Path,
        job: CrumpJob,
        sync_columns: list[Any],
        filename_values: dict[str, str] | None = None,
    ) -> tuple[int, set[tuple]]:
        """Count CSV rows and track synced IDs without database operations.

        This helper method processes the CSV to count rows and collect IDs that would be synced,
        which is shared logic between dry-run and actual sync operations.

        Args:
            file_path: Path to tabular file (CSV or Parquet)
            job: CrumpJob configuration
            sync_columns: List of ColumnMapping objects
            filename_values: Optional dict of values extracted from filename

        Returns:
            Tuple of (row_count, synced_ids) where synced_ids are tuples of ID values
        """
        row_count = 0
        synced_ids: set[tuple] = set()

        file_format = _detect_file_format(file_path)

        with create_reader(file_path, file_format=file_format) as reader:
            # For sampling, we need to know total row count first
            if job.sample_percentage is not None and job.sample_percentage < 100:
                # Read all rows into memory to get total count and apply sampling
                all_rows = list(reader)
                total_rows = len(all_rows)

                for row_index, row in enumerate(all_rows):
                    # Check if this row should be included
                    if not self._should_include_row(row_index, total_rows, job.sample_percentage):
                        continue

                    # Apply column transformations
                    row_data = apply_row_transformations(
                        row, sync_columns, job.filename_to_column, filename_values
                    )

                    # Track synced IDs as tuples (for compound key support)
                    id_values = tuple(row_data[id_col.db_column] for id_col in job.id_mapping)
                    synced_ids.add(id_values)
                    row_count += 1
            else:
                # No sampling - process rows normally
                for row in reader:
                    # Apply column transformations
                    row_data = apply_row_transformations(
                        row, sync_columns, job.filename_to_column, filename_values
                    )

                    # Track synced IDs as tuples (for compound key support)
                    id_values = tuple(row_data[id_col.db_column] for id_col in job.id_mapping)
                    synced_ids.add(id_values)
                    row_count += 1

        return row_count, synced_ids

    def _prepare_sync(
        self, file_path: Path, job: CrumpJob
    ) -> tuple[set[str], list[Any], dict[str, str]]:
        """Prepare for sync by validating CSV and building schema definitions.

        Args:
            file_path: Path to tabular file (CSV or Parquet)
            job: CrumpJob configuration

        Returns:
            Tuple of (csv_columns, sync_columns, columns_def)

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV is invalid or columns don't match
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_format = _detect_file_format(file_path)

        with create_reader(file_path, file_format=file_format) as reader:
            if not reader.fieldnames:
                raise ValueError("File has no columns")
            csv_columns = set(reader.fieldnames)

        # Validate and determine columns to sync
        id_csv_columns = self._validate_id_columns(job, csv_columns)
        sync_columns = self._determine_sync_columns(job, csv_columns, id_csv_columns)

        # Build schema definitions
        columns_def = self._build_column_definitions(sync_columns, job)

        return csv_columns, sync_columns, columns_def

    def sync_tabular_file_dry_run(
        self,
        file_path: Path,
        job: CrumpJob,
        filename_values: dict[str, str] | None = None,
    ) -> DryRunSummary:
        """Simulate syncing a CSV file without making database changes.

        Args:
            file_path: Path to tabular file (CSV or Parquet)
            job: CrumpJob configuration
            filename_values: Optional dict of values extracted from filename

        Returns:
            DryRunSummary with details of what would be changed

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV is invalid or columns don't match
        """
        summary = DryRunSummary()
        summary.table_name = job.target_table

        # Prepare sync (validates CSV and builds schema)
        csv_columns, sync_columns, columns_def = self._prepare_sync(file_path, job)

        # Check what schema changes would be made
        summary.table_exists = self.table_exists(job.target_table)

        if summary.table_exists:
            # Check for new columns
            existing_columns = self.get_existing_columns(job.target_table)
            for col_name, col_type in columns_def.items():
                if col_name.lower() not in existing_columns:
                    summary.new_columns.append((col_name, col_type))

            # Check for new indexes
            if job.indexes:
                existing_indexes = self.get_existing_indexes(job.target_table)
                for index in job.indexes:
                    if index.name.lower() not in existing_indexes:
                        summary.new_indexes.append(index.name)

        # Count rows and track IDs that would be synced
        # NOTE: This counts all CSV rows, even if they match existing data.
        # A more accurate implementation would query existing data and compare,
        # but that would be expensive for large datasets. For now, we report
        # the upper bound of rows that could be updated.
        # If there are new columns, all rows will need updating regardless.
        summary.rows_to_sync, synced_ids = self._count_and_track_tabular_rows(
            file_path, job, sync_columns, filename_values
        )

        # Count stale records that would be deleted
        if job.filename_to_column and filename_values and summary.table_exists:
            delete_key_columns = job.filename_to_column.get_delete_key_columns()
            if delete_key_columns:
                # Build compound key values from filename_values
                delete_key_values = {}
                for col_name, col_mapping in job.filename_to_column.columns.items():
                    if col_mapping.use_to_delete_old_rows and col_name in filename_values:
                        delete_key_values[col_mapping.db_column] = filename_values[col_name]

                id_columns = [id_col.db_column for id_col in job.id_mapping]
                summary.rows_to_delete = self.count_stale_records_compound(
                    job.target_table,
                    id_columns,
                    delete_key_values,
                    synced_ids,
                )

        return summary

    def sync_tabular_file(
        self,
        file_path: Path,
        job: CrumpJob,
        filename_values: dict[str, str] | None = None,
        enable_history: bool = False,
    ) -> int:
        """Sync a CSV file to the database using job configuration.

        Args:
            file_path: Path to tabular file (CSV or Parquet)
            job: CrumpJob configuration
            filename_values: Optional dict of values extracted from filename
            enable_history: Whether to record sync history

        Returns:
            Number of rows synced

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV is invalid or columns don't match
        """
        from crump.history import get_utc_now, record_sync_history

        # Track timing if history is enabled
        start_time = get_utc_now() if enable_history else None
        rows_deleted = 0
        schema_changed = False
        error_message: str | None = None
        success = False

        try:
            # Prepare sync (validates CSV and builds schema)
            csv_columns, sync_columns, columns_def = self._prepare_sync(file_path, job)

            # Build schema and setup table
            primary_keys = [id_col.db_column for id_col in job.id_mapping]
            logger.debug(f"Primary keys for table {job.target_table}: {primary_keys}")
            schema_changed = self._setup_table_schema(job, columns_def, primary_keys)

            # Process rows
            file_format = _detect_file_format(file_path)
            with create_reader(file_path, file_format=file_format) as reader:
                rows_synced, synced_ids = self._process_tabular_rows(
                    reader, job, sync_columns, primary_keys, filename_values
                )

            # Clean up stale records
            if job.filename_to_column and filename_values:
                delete_key_columns = job.filename_to_column.get_delete_key_columns()
                if delete_key_columns:
                    # Build compound key values from filename_values
                    delete_key_values = {}
                    for col_name, col_mapping in job.filename_to_column.columns.items():
                        if col_mapping.use_to_delete_old_rows and col_name in filename_values:
                            delete_key_values[col_mapping.db_column] = filename_values[col_name]

                    id_columns = [id_col.db_column for id_col in job.id_mapping]
                    rows_deleted = self.delete_stale_records_compound(
                        job.target_table,
                        id_columns,
                        delete_key_values,
                        synced_ids,
                    )

            success = True
            return rows_synced

        except Exception as e:
            error_message = str(e)
            raise

        finally:
            # Record history if enabled and we have a backend
            if enable_history and self.backend and start_time:
                end_time = get_utc_now()
                # If sync failed, rows_synced might not be set
                final_rows_synced = rows_synced if success else 0
                try:
                    record_sync_history(
                        backend=self.backend,
                        file_path=file_path,
                        table_name=job.target_table,
                        rows_upserted=final_rows_synced,
                        rows_deleted=rows_deleted,
                        schema_changed=schema_changed,
                        start_time=start_time,
                        end_time=end_time,
                        success=success,
                        error=error_message,
                    )
                except Exception as hist_error:
                    # Don't fail the sync if history recording fails
                    logger.warning(f"Failed to record sync history: {hist_error}")


def sync_file_to_db(
    file_path: Path,
    job: CrumpJob,
    db_connection_string: str,
    filename_values: dict[str, str] | None = None,
    enable_history: bool = False,
) -> int:
    """Sync a tabular file (CSV or Parquet) to database.

    Args:
        file_path: Path to the tabular file (CSV or Parquet)
        job: CrumpJob configuration
        db_connection_string: Database connection string (PostgreSQL or SQLite)
        filename_values: Optional dict of values extracted from filename
        enable_history: Whether to record sync history

    Returns:
        Number of rows synced
    """
    with DatabaseConnection(db_connection_string) as db:
        return db.sync_tabular_file(file_path, job, filename_values, enable_history)


def sync_file_to_db_dry_run(
    file_path: Path,
    job: CrumpJob,
    db_connection_string: str,
    filename_values: dict[str, str] | None = None,
) -> DryRunSummary:
    """Simulate syncing a tabular file without making database changes.

    Args:
        file_path: Path to the tabular file (CSV or Parquet)
        job: CrumpJob configuration
        db_connection_string: Database connection string
        filename_values: Optional dict of values extracted from filename

    Returns:
        DryRunSummary with details of what would be changed
    """
    with DatabaseConnection(db_connection_string) as db:
        return db.sync_tabular_file_dry_run(file_path, job, filename_values)


# Backward compatibility aliases
