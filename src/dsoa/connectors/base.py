"""The connector contract.

Every connector in this framework — hand-written or agent-generated — subclasses
:class:`BaseConnector`. The Phase 3 static validator asserts this by walking the
generated module's AST, so the ABC is not a suggestion: a connector that does not
implement all five abstract methods is rejected before it is ever executed.

Lifecycle::

    with PostgresqlConnector(config) as conn:
        result = conn.test_connection()
        tables = conn.fetch_schema()
        rows = conn.read("SELECT * FROM customers WHERE region = :region",
                         {"region": "APAC"})
    # connection is closed here, even if the block raised
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from types import TracebackType
from typing import Any, ClassVar

from .config import SqlConnectionConfig
from .models import ConnectionTestResult, TableSchema


class BaseConnector(ABC):
    """Abstract base for all data source connectors."""

    #: Stable identifier used by the template registry and the UI.
    source_type: ClassVar[str] = "unknown"

    def __init__(
        self,
        config: SqlConnectionConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._connection: Any | None = None

    @property
    def config(self) -> SqlConnectionConfig:
        """The immutable configuration this connector was built from."""
        return self._config

    @property
    def is_connected(self) -> bool:
        """Whether an underlying connection or engine currently exists."""
        return self._connection is not None

    def connect(self) -> None:
        """Establish the connection. Idempotent — safe to call repeatedly."""
        if self._connection is not None:
            self._logger.debug("connect() called on an already-open connector")
            return
        self._logger.info("Connecting to %s", self.describe_target())
        self._connection = self._create_connection()

    def close(self) -> None:
        """Release the connection. Idempotent and never raises."""
        if self._connection is None:
            return
        try:
            self._dispose(self._connection)
        except Exception:  # pragma: no cover - defensive
            self._logger.exception("Error while closing connector; continuing")
        finally:
            self._connection = None
            self._logger.info("Closed connection to %s", self.describe_target())

    def __enter__(self) -> BaseConnector:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ---- Subclass contract -------------------------------------------------

    @abstractmethod
    def _create_connection(self) -> Any:
        """Build and return the underlying connection or engine object."""

    @abstractmethod
    def _dispose(self, connection: Any) -> None:
        """Tear down the object returned by :meth:`_create_connection`."""

    @abstractmethod
    def describe_target(self) -> str:
        """A human-readable, credential-free description of the target."""

    @abstractmethod
    def test_connection(self) -> ConnectionTestResult:
        """Verify connectivity and return a structured result.

        Must not raise on connection failure — a failed check is a result the
        agent needs to read. Reserve exceptions for programmer error.
        """

    @abstractmethod
    def fetch_schema(
        self, schema: str | None = None, *, include_views: bool = False
    ) -> Sequence[TableSchema]:
        """Introspect the target and return its tables."""

    @abstractmethod
    def read(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a read query with bound parameters and return rows as dicts.

        Implementations must use the driver's parameter binding. String
        interpolation of ``params`` into ``query`` is a standards violation and
        the validator will reject it.
        """
