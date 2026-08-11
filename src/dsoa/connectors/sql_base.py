"""Shared implementation for every SQL source type.

Postgres, MySQL, and SQL Server differ in about forty lines: the driver string,
the default port, the version query, and the ``connect_args`` dict. Everything
else — pooling, retry, parameter binding, schema introspection, error
translation — lives here.

That ratio is the point. When the Phase 3 agent generates a new SQL connector it
is filling in four small hooks against a base class that has already been
reviewed, not writing database code from scratch.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import (
    DBAPIError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.exc import (
    TimeoutError as SATimeoutError,
)

from .base import BaseConnector
from .exceptions import (
    AuthenticationError,
    ConnectionFailedError,
    QueryExecutionError,
    SchemaFetchError,
    TransientConnectionError,
    UnsafeQueryError,
)
from .models import ColumnSchema, ConnectionTestResult, TableSchema
from .retry import retry_on_transient

#: Substrings that indicate rejected credentials rather than a flaky network.
_AUTH_MARKERS = (
    "password authentication failed",
    "authentication failed",
    "access denied",
    "login failed",
    "role does not exist",
    "no password supplied",
    "permission denied for database",
)

#: Substrings that indicate a failure worth retrying.
_TRANSIENT_MARKERS = (
    "could not connect",
    "connection refused",
    "connection reset",
    "timeout expired",
    "timed out",
    "temporarily unavailable",
    "too many connections",
    "server closed the connection",
    "is starting up",
    "name or service not known",
)

_READ_PREFIXES = ("select", "with", "show", "explain", "describe")
_COMMENT_PATTERN = re.compile(r"(--[^\n]*)|(/\*.*?\*/)", re.DOTALL)


class SQLBaseConnector(BaseConnector):
    """Base class for SQLAlchemy-backed connectors."""

    #: SQLAlchemy dialect+driver, e.g. ``postgresql+psycopg``.
    driver: ClassVar[str] = ""
    #: Port used when the config omits one.
    default_port: ClassVar[int] = 0
    #: Dialect-specific statement returning the server version string.
    version_query: ClassVar[str] = "SELECT 1"
    #: Schema introspected when the caller does not name one.
    default_schema: ClassVar[str | None] = None
    #: When True, :meth:`read` rejects anything that is not a read statement.
    read_only: ClassVar[bool] = True
    #: Query-string parameters appended to the connection URL. Needed by
    #: dialects that select their driver there rather than in connect_args —
    #: SQL Server's ``?driver=ODBC+Driver+18+for+SQL+Server`` being the case
    #: that forced this hook to exist.
    url_query: ClassVar[dict[str, str]] = {}

    # ---- Dialect hooks -----------------------------------------------------

    def _connect_args(self) -> dict[str, Any]:
        """Driver-level keyword arguments. Override per dialect."""
        return {}

    def _build_url(self) -> URL:
        """Assemble the connection URL.

        Uses ``URL.create`` rather than an f-string so that passwords containing
        ``@``, ``/``, or ``:`` are escaped correctly — a bug class that shows up
        constantly in hand-written and LLM-written connection strings alike.
        """
        cfg = self.config
        return URL.create(
            drivername=self.driver,
            username=cfg.username,
            password=cfg.password.get_secret_value(),
            host=cfg.host,
            port=cfg.port or self.default_port,
            database=cfg.database,
            query=dict(self.url_query),
        )

    # ---- BaseConnector implementation --------------------------------------

    def describe_target(self) -> str:
        return self.config.masked_dsn(self.driver)

    def _create_connection(self) -> Engine:
        cfg = self.config
        try:
            engine = create_engine(
                self._build_url(),
                pool_size=cfg.pool_size,
                max_overflow=cfg.max_overflow,
                pool_recycle=cfg.pool_recycle_seconds,
                pool_pre_ping=cfg.pool_pre_ping,
                pool_timeout=cfg.connect_timeout_seconds,
                connect_args=self._connect_args(),
                future=True,
            )
        except SQLAlchemyError as exc:
            raise ConnectionFailedError(
                f"Could not build engine: {exc}", target=self.describe_target()
            ) from exc

        # Fail fast: create_engine is lazy, so force one real round trip here
        # rather than surfacing a config error later inside a query.
        self._verify_engine(engine)
        return engine

    @retry_on_transient(max_attempts=3, backoff_seconds=0.5)
    def _verify_engine(self, engine: Engine) -> None:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise self._translate_error(exc) from exc

    def _dispose(self, connection: Any) -> None:
        connection.dispose()

    @property
    def engine(self) -> Engine:
        """The live engine, connecting on first access."""
        if self._connection is None:
            self.connect()
        return self._connection  # type: ignore[return-value]

    def test_connection(self) -> ConnectionTestResult:
        """Connect, time one round trip, and read the server version."""
        started = time.perf_counter()
        try:
            with self.engine.connect() as conn:
                version = conn.execute(text(self.version_query)).scalar()
            latency_ms = (time.perf_counter() - started) * 1000
            return ConnectionTestResult(
                success=True,
                source_type=self.source_type,
                target=self.describe_target(),
                latency_ms=latency_ms,
                server_version=str(version) if version is not None else None,
                details={"pool_size": self.config.pool_size},
            )
        except Exception as exc:
            translated = (
                exc if isinstance(exc, ConnectionFailedError) else self._translate_error(exc)
            )
            self._logger.warning("Connection test failed: %s", translated)
            return ConnectionTestResult(
                success=False,
                source_type=self.source_type,
                target=self.describe_target(),
                latency_ms=(time.perf_counter() - started) * 1000,
                error_type=type(translated).__name__,
                error_message=str(translated),
            )

    def fetch_schema(
        self, schema: str | None = None, *, include_views: bool = False
    ) -> Sequence[TableSchema]:
        """Introspect tables (and optionally views) in ``schema``."""
        target_schema = schema or self.default_schema
        try:
            inspector = inspect(self.engine)
            resolved = target_schema or inspector.default_schema_name or ""
            names = list(inspector.get_table_names(schema=target_schema))
            if include_views:
                names.extend(inspector.get_view_names(schema=target_schema))

            tables: list[TableSchema] = []
            for name in sorted(set(names)):
                pk = set(
                    inspector.get_pk_constraint(name, schema=target_schema).get(
                        "constrained_columns"
                    )
                    or []
                )
                columns = tuple(
                    ColumnSchema(
                        name=col["name"],
                        data_type=str(col["type"]),
                        nullable=bool(col.get("nullable", True)),
                        primary_key=col["name"] in pk,
                        default=(str(col["default"]) if col.get("default") is not None else None),
                    )
                    for col in inspector.get_columns(name, schema=target_schema)
                )
                tables.append(TableSchema(schema_name=resolved, table_name=name, columns=columns))
            self._logger.info("Introspected %d tables from %s", len(tables), self.describe_target())
            return tables
        except SQLAlchemyError as exc:
            raise SchemaFetchError(
                f"Schema introspection failed: {exc}", schema=target_schema
            ) from exc

    def read(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a parameterized read query.

        Args:
            query: SQL using ``:name`` placeholders. Never interpolate values.
            params: Values bound to those placeholders.
            limit: Optional cap applied client-side after fetch.

        Raises:
            UnsafeQueryError: multi-statement payload, or a write on a
                read-only connector.
            QueryExecutionError: the server rejected the statement.
        """
        self._assert_query_is_safe(query)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                rows = [dict(row) for row in result.mappings()]
        except SQLAlchemyError as exc:
            raise QueryExecutionError(
                f"Query failed: {exc}", target=self.describe_target()
            ) from exc

        if limit is not None:
            rows = rows[:limit]
        self._logger.debug("Query returned %d rows", len(rows))
        return rows

    # ---- Internals ---------------------------------------------------------

    def _assert_query_is_safe(self, query: str) -> None:
        stripped = _COMMENT_PATTERN.sub(" ", query).strip()
        if not stripped:
            raise UnsafeQueryError("Query is empty")

        if stripped.rstrip(";").count(";"):
            raise UnsafeQueryError("Multiple statements are not permitted in a single read() call")

        if self.read_only:
            first = stripped.split(None, 1)[0].lower()
            if first not in _READ_PREFIXES:
                raise UnsafeQueryError("This connector is read-only", statement=first.upper())

    def _translate_error(self, exc: Exception) -> ConnectionFailedError:
        """Map a driver exception onto the framework's vocabulary."""
        message = str(exc).lower()

        if isinstance(exc, SATimeoutError):
            return TransientConnectionError(
                "Connection pool timed out", target=self.describe_target()
            )

        if any(marker in message for marker in _AUTH_MARKERS):
            return AuthenticationError(
                "Credentials rejected by the server",
                target=self.describe_target(),
                username=self.config.username,
            )

        if any(marker in message for marker in _TRANSIENT_MARKERS):
            return TransientConnectionError(
                f"Transient connection failure: {exc}", target=self.describe_target()
            )

        if isinstance(exc, (OperationalError, DBAPIError)):
            return ConnectionFailedError(f"Connection failed: {exc}", target=self.describe_target())

        return ConnectionFailedError(
            f"Unexpected connection error: {exc}", target=self.describe_target()
        )
