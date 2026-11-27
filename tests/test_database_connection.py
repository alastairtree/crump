"""Tests for supported database connection string formats."""

from unittest.mock import patch

import pytest

from crump.database import DatabaseConnection


@pytest.mark.parametrize(
    ("scheme", "expected_scheme"),
    [
        ("postgresql", "postgresql"),
        ("postgres", "postgres"),
        ("postgresql+psycopg", "postgresql"),
        ("postgresql+psycopg2", "postgresql"),
        ("postgresql+asyncpg", "postgresql"),
        ("postgresql+pg8000", "postgresql"),
        ("postgres+psycopg", "postgres"),
    ],
)
def test_postgres_url_preserves_connection_details(scheme: str, expected_scheme: str) -> None:
    """Normalise only the driver suffix, not credentials, hosts or query parameters."""
    details = (
        "user:p%40ss+word@[::1]:5432/my%20db"
        "?sslmode=require&application_name=postgresql+psycopg://crump"
    )
    with (
        patch("crump.database.psycopg.connect") as connect,
        DatabaseConnection(f"{scheme}://{details}"),
    ):
        pass

    connect.assert_called_once_with(f"{expected_scheme}://{details}")


@pytest.mark.parametrize(
    "conninfo",
    [
        "host=localhost port=5432 dbname=mydb user=myuser",
        "service=crump",
        "  host = '/var/run/postgresql' dbname=mydb password='postgresql+psycopg://test word'",
    ],
)
def test_postgres_keyword_conninfo_is_unchanged(conninfo: str) -> None:
    """Pass libpq keyword/value strings through to psycopg without rewriting them."""
    with patch("crump.database.psycopg.connect") as connect, DatabaseConnection(conninfo):
        pass

    connect.assert_called_once_with(conninfo)


def test_unsupported_database_url_is_rejected() -> None:
    """A query parameter must not make an unsupported URL look like keyword conninfo."""
    with (
        pytest.raises(ValueError, match="Unsupported database type"),
        DatabaseConnection("mysql://localhost/mydb?application_name=crump"),
    ):
        pass
