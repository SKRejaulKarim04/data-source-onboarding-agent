"""Exception hierarchy for the connector framework.

Every connector raises exceptions from this module and nothing else. Raw driver
exceptions (psycopg, pymysql, pyodbc, httpx) are translated at the boundary so
that calling code — and later, the agent's repair loop — has one stable
vocabulary to reason about regardless of source type.

``TransientConnectionError`` is the only class the retry decorator will retry.
"""

from __future__ import annotations

from typing import Any


class ConnectorError(Exception):
    """Base class for every error raised by the connector framework."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        rendered = ", ".join(f"{key}={value!r}" for key, value in self.context.items())
        return f"{self.message} ({rendered})"


class ConfigurationError(ConnectorError):
    """Configuration is missing, malformed, or internally inconsistent."""


class ConnectionFailedError(ConnectorError):
    """The connector could not establish a usable connection."""


class AuthenticationError(ConnectionFailedError):
    """Credentials were rejected by the target system. Never retried."""


class TransientConnectionError(ConnectionFailedError):
    """A failure that may succeed on retry: timeout, refused, pool exhausted."""


class QueryExecutionError(ConnectorError):
    """The target system rejected or failed to execute the query."""


class SchemaFetchError(ConnectorError):
    """Schema introspection failed."""


class UnsafeQueryError(ConnectorError):
    """The query violated the connector's safety policy.

    Raised before anything reaches the database — for multi-statement payloads
    or write operations on a read-only connector.
    """
