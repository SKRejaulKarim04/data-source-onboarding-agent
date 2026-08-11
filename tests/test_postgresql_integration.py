"""Live PostgreSQL tests.

Run with::

    make up && make test-integration

Skipped automatically when DSOA_PG_HOST is unset, so `pytest` stays green on a
laptop with nothing running.
"""

from __future__ import annotations

import os

import pytest

# Module-level skip rather than fixture-level: one test below builds its own
# config to exercise the wrong-password path, so it never touches the fixture
# and would otherwise blow up with a KeyError instead of skipping cleanly.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("DSOA_PG_HOST") is None,
        reason="DSOA_PG_* not set — run `make up` and source .env",
    ),
]


def test_connects_to_live_postgres(postgres_connector) -> None:
    result = postgres_connector.test_connection()

    assert result.success is True, result.error_message
    assert "PostgreSQL" in (result.server_version or "")
    assert result.latency_ms is not None


def test_introspects_the_seeded_schema(postgres_connector) -> None:
    tables = {t.table_name for t in postgres_connector.fetch_schema()}

    assert {"customers", "orders", "products"} <= tables


def test_reads_seeded_rows_with_bound_parameters(postgres_connector) -> None:
    rows = postgres_connector.read(
        "SELECT name FROM customers WHERE region = :region ORDER BY name",
        {"region": "APAC"},
    )

    assert len(rows) >= 1
    assert all("name" in row for row in rows)


def test_write_is_blocked_against_the_real_server(postgres_connector) -> None:
    from dsoa.connectors import UnsafeQueryError

    with pytest.raises(UnsafeQueryError):
        postgres_connector.read("DELETE FROM customers")


def test_wrong_password_is_reported_as_authentication_failure() -> None:

    from dsoa.connectors import PostgresqlConnector, SqlConnectionConfig

    config = SqlConnectionConfig(
        host=os.environ["DSOA_PG_HOST"],
        port=int(os.environ.get("DSOA_PG_PORT", 5432)),
        database=os.environ["DSOA_PG_DATABASE"],
        username=os.environ["DSOA_PG_USERNAME"],
        password="definitely-the-wrong-password",
        max_retries=1,
    )
    result = PostgresqlConnector(config).test_connection()

    assert result.success is False
    assert result.error_type == "AuthenticationError"
