"""Shared fixtures.

Two tiers of test, and the split matters:

* **Unit** — run everywhere, no services. A SQLite-backed subclass exercises the
  whole ``SQLBaseConnector`` code path (pooling, safe-read guard, introspection,
  error translation) with zero infrastructure. This is what keeps CI fast and
  what you run on a plane.
* **Integration** — marked ``integration``, need ``docker compose up``. These
  prove the real driver and dialect work.

The SQLite subclass is roughly what the Phase 3 agent will emit for a new
dialect, so it doubles as a check that the extension points are actually usable.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from sqlalchemy import URL, text

from dsoa.connectors import PostgresqlConnector, SqlConnectionConfig
from dsoa.connectors.sql_base import SQLBaseConnector


class SqliteConnector(SQLBaseConnector):
    """In-memory SQLite connector used only by the unit tests."""

    source_type: ClassVar[str] = "sqlite"
    driver: ClassVar[str] = "sqlite"
    default_port: ClassVar[int] = 0
    version_query: ClassVar[str] = "SELECT sqlite_version()"
    default_schema: ClassVar[str | None] = None

    def __init__(self, config: SqlConnectionConfig, db_path: str) -> None:
        super().__init__(config)
        self._db_path = db_path

    def _build_url(self) -> URL:
        return URL.create(drivername="sqlite", database=self._db_path)

    def _connect_args(self) -> dict[str, Any]:
        return {"timeout": self.config.connect_timeout_seconds}


@pytest.fixture
def dummy_config() -> SqlConnectionConfig:
    """A syntactically valid config; the SQLite connector ignores the network parts."""
    return SqlConnectionConfig(
        host="localhost",
        port=5432,
        database="testdb",
        username="tester",
        password="not-a-real-password",
        pool_size=2,
        max_overflow=0,
    )


@pytest.fixture
def sqlite_connector(dummy_config: SqlConnectionConfig, tmp_path: Any) -> Iterator[SqliteConnector]:
    """A connected SQLite connector seeded with two tables."""
    db_file = str(tmp_path / "unit.db")
    connector = SqliteConnector(dummy_config, db_file)
    connector.connect()

    with connector.engine.begin() as conn:
        conn.execute(text("""
                CREATE TABLE customers (
                    customer_id INTEGER PRIMARY KEY,
                    name        TEXT NOT NULL,
                    region      TEXT,
                    tier        TEXT DEFAULT 'standard'
                )
                """))
        conn.execute(text("""
                CREATE TABLE orders (
                    order_id    INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    amount      REAL NOT NULL
                )
                """))
        for row in [
            {"cid": 1, "name": "Northwind", "region": "APAC", "tier": "gold"},
            {"cid": 2, "name": "Contoso", "region": "EMEA", "tier": "standard"},
            {"cid": 3, "name": "Fabrikam", "region": "APAC", "tier": "gold"},
        ]:
            conn.execute(
                text(
                    "INSERT INTO customers (customer_id, name, region, tier) "
                    "VALUES (:cid, :name, :region, :tier)"
                ),
                row,
            )

    yield connector
    connector.close()


@pytest.fixture
def postgres_connector() -> Iterator[PostgresqlConnector]:
    """Live Postgres from docker compose. Skips when unavailable."""
    if os.environ.get("DSOA_PG_HOST") is None:
        pytest.skip("DSOA_PG_* not set — run `make up` first")
    connector = PostgresqlConnector.from_env()
    try:
        yield connector
    finally:
        connector.close()
