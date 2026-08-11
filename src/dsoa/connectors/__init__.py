"""Reusable connector framework.

Public surface. Generated connectors import from here and nowhere deeper, which
keeps the internal module layout free to change without breaking artifacts that
were already published.
"""

from .base import BaseConnector
from .config import SqlConnectionConfig
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    ConnectionFailedError,
    ConnectorError,
    QueryExecutionError,
    SchemaFetchError,
    TransientConnectionError,
    UnsafeQueryError,
)
from .models import ColumnSchema, ConnectionTestResult, TableSchema
from .postgresql import PostgresqlConnector
from .retry import retry_on_transient
from .sql_base import SQLBaseConnector

__all__ = [
    "AuthenticationError",
    "BaseConnector",
    "ColumnSchema",
    "ConfigurationError",
    "ConnectionFailedError",
    "ConnectionTestResult",
    "ConnectorError",
    "PostgresqlConnector",
    "QueryExecutionError",
    "SQLBaseConnector",
    "SchemaFetchError",
    "SqlConnectionConfig",
    "TableSchema",
    "TransientConnectionError",
    "UnsafeQueryError",
    "retry_on_transient",
]
