"""Base-class behaviour, verified against a real (SQLite) database.

No mocks for the query path. Mocked database tests mostly assert that the mock
was configured the way the test author expected, which is not the same thing as
the connector working.
"""

from __future__ import annotations

import pytest

from dsoa.connectors import (
    ConnectionTestResult,
    QueryExecutionError,
    UnsafeQueryError,
)
from dsoa.connectors.exceptions import (
    AuthenticationError,
    TransientConnectionError,
)

# ---- Lifecycle -------------------------------------------------------------


def test_connect_is_idempotent(sqlite_connector) -> None:
    assert sqlite_connector.is_connected
    first = sqlite_connector.engine
    sqlite_connector.connect()
    assert sqlite_connector.engine is first


def test_close_is_idempotent_and_resets_state(sqlite_connector) -> None:
    sqlite_connector.close()
    assert not sqlite_connector.is_connected
    sqlite_connector.close()  # must not raise


def test_context_manager_closes_on_exception(dummy_config, tmp_path) -> None:
    from tests.conftest import SqliteConnector

    connector = SqliteConnector(dummy_config, str(tmp_path / "ctx.db"))
    with pytest.raises(RuntimeError), connector:
        assert connector.is_connected
        raise RuntimeError("boom")

    assert not connector.is_connected


# ---- Connectivity ----------------------------------------------------------


def test_test_connection_succeeds_and_reports_version(sqlite_connector) -> None:
    result = sqlite_connector.test_connection()

    assert isinstance(result, ConnectionTestResult)
    assert result.success is True
    assert result.server_version is not None
    assert result.latency_ms is not None and result.latency_ms >= 0
    assert result.summary().startswith("OK")


def test_failed_connection_returns_a_result_rather_than_raising(
    dummy_config,
) -> None:
    """A failure is data the agent reads, not an exception it must catch."""
    from tests.conftest import SqliteConnector

    # A directory that cannot exist forces SQLite to fail to open the file.
    connector = SqliteConnector(dummy_config, "/nonexistent-dir/nope.db")
    result = connector.test_connection()

    assert result.success is False
    assert result.error_type is not None
    assert result.error_message
    assert result.summary().startswith("FAILED")


# ---- Reads -----------------------------------------------------------------


def test_read_returns_dicts(sqlite_connector) -> None:
    rows = sqlite_connector.read("SELECT customer_id, name FROM customers ORDER BY customer_id")

    assert len(rows) == 3
    assert rows[0] == {"customer_id": 1, "name": "Northwind"}


def test_read_binds_parameters(sqlite_connector) -> None:
    rows = sqlite_connector.read(
        "SELECT name FROM customers WHERE region = :region ORDER BY name",
        {"region": "APAC"},
    )

    assert [row["name"] for row in rows] == ["Fabrikam", "Northwind"]


def test_read_applies_limit(sqlite_connector) -> None:
    rows = sqlite_connector.read("SELECT * FROM customers", limit=2)
    assert len(rows) == 2


def test_parameter_binding_neutralises_injection(sqlite_connector) -> None:
    """The classic payload must be treated as a value, not as SQL."""
    rows = sqlite_connector.read(
        "SELECT * FROM customers WHERE region = :region",
        {"region": "APAC'; DROP TABLE customers; --"},
    )

    assert rows == []
    # Table survived.
    assert len(sqlite_connector.read("SELECT * FROM customers")) == 3


def test_bad_sql_raises_query_execution_error(sqlite_connector) -> None:
    with pytest.raises(QueryExecutionError):
        sqlite_connector.read("SELECT * FROM table_that_does_not_exist")


# ---- Safety guard ----------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM customers",
        "UPDATE customers SET tier = 'gold'",
        "DROP TABLE customers",
        "INSERT INTO customers (name) VALUES ('x')",
    ],
)
def test_write_statements_are_rejected_on_a_read_only_connector(
    sqlite_connector, query: str
) -> None:
    with pytest.raises(UnsafeQueryError):
        sqlite_connector.read(query)


def test_multi_statement_payload_is_rejected(sqlite_connector) -> None:
    with pytest.raises(UnsafeQueryError):
        sqlite_connector.read("SELECT 1; DROP TABLE customers")


def test_trailing_semicolon_is_allowed(sqlite_connector) -> None:
    rows = sqlite_connector.read("SELECT 1 AS one;")
    assert rows == [{"one": 1}]


def test_comment_smuggling_is_rejected(sqlite_connector) -> None:
    """A write hidden behind a comment prefix must not slip past the guard."""
    with pytest.raises(UnsafeQueryError):
        sqlite_connector.read("-- harmless\n DELETE FROM customers")


def test_empty_query_is_rejected(sqlite_connector) -> None:
    with pytest.raises(UnsafeQueryError):
        sqlite_connector.read("   ")


# ---- Introspection ---------------------------------------------------------


def test_fetch_schema_lists_tables_and_columns(sqlite_connector) -> None:
    tables = {table.table_name: table for table in sqlite_connector.fetch_schema()}

    assert set(tables) == {"customers", "orders"}

    customers = tables["customers"]
    columns = {col.name: col for col in customers.columns}
    assert set(columns) == {"customer_id", "name", "region", "tier"}
    assert columns["customer_id"].primary_key is True
    assert columns["name"].nullable is False
    assert columns["region"].nullable is True


# ---- Error translation -----------------------------------------------------


def test_auth_failure_is_classified_as_authentication_error(sqlite_connector) -> None:
    translated = sqlite_connector._translate_error(
        Exception("FATAL: password authentication failed for user 'svc'")
    )
    assert isinstance(translated, AuthenticationError)


@pytest.mark.parametrize(
    "message",
    [
        "could not connect to server",
        "connection refused",
        "timeout expired",
        "too many connections for role",
    ],
)
def test_network_failures_are_classified_as_transient(sqlite_connector, message: str) -> None:
    translated = sqlite_connector._translate_error(Exception(message))
    assert isinstance(translated, TransientConnectionError)


def test_auth_errors_are_not_retried(sqlite_connector) -> None:
    """Retrying a rejected password locks accounts. It must not happen."""
    translated = sqlite_connector._translate_error(Exception("access denied"))
    assert not isinstance(translated, TransientConnectionError)
