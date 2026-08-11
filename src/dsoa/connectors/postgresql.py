"""PostgreSQL connector.

This is the reference implementation. In Phase 3 the Jinja2 template for
``source_type="postgresql"`` renders a module that looks almost exactly like
this file — which is precisely why it is written by hand first. You cannot judge
generated code against a standard that does not yet exist in concrete form.

Note how little is here: four class attributes and one hook. That thinness is
the deliverable.

Usage::

    from dsoa.connectors import PostgresqlConnector, SqlConnectionConfig

    config = SqlConnectionConfig.from_env("DSOA_PG_", default_port=5432)
    with PostgresqlConnector(config) as conn:
        print(conn.test_connection().summary())
"""

from __future__ import annotations

from typing import Any, ClassVar

from .sql_base import SQLBaseConnector


class PostgresqlConnector(SQLBaseConnector):
    """Read connector for PostgreSQL, backed by psycopg 3."""

    source_type: ClassVar[str] = "postgresql"
    driver: ClassVar[str] = "postgresql+psycopg"
    default_port: ClassVar[int] = 5432
    version_query: ClassVar[str] = "SELECT version()"
    default_schema: ClassVar[str | None] = "public"
    env_prefix: ClassVar[str] = "DSOA_PG_"

    def _connect_args(self) -> dict[str, Any]:
        """psycopg 3 connection keywords.

        ``application_name`` matters more than it looks: it is what makes a
        generated connector identifiable in ``pg_stat_activity`` when a DBA asks
        who opened forty connections.
        """
        return {
            "connect_timeout": self.config.connect_timeout_seconds,
            "sslmode": self.config.ssl_mode,
            "application_name": self.config.application_name,
            "options": f"-c statement_timeout={self.config.query_timeout_seconds * 1000}",
        }

    @classmethod
    def from_env(cls, prefix: str | None = None) -> PostgresqlConnector:
        """Build a connector straight from environment variables."""
        from .config import SqlConnectionConfig

        config = SqlConnectionConfig.from_env(
            prefix or cls.env_prefix, default_port=cls.default_port
        )
        return cls(config)
