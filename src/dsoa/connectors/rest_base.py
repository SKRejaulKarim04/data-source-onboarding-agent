"""REST API base connector."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any, ClassVar

import requests

from .base import BaseConnector
from .config import RestConnectionConfig
from .models import ConnectionTestResult, TableSchema, ColumnSchema


class RestBaseConnector(BaseConnector):
    """Abstract base for REST API connectors."""

    source_type: ClassVar[str] = "rest_api"
    default_path: ClassVar[str] = ""
    env_prefix: ClassVar[str] = ""

    def __init__(
        self,
        config: RestConnectionConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._connection: requests.Session | None = None

    @property
    def config(self) -> RestConnectionConfig:
        return self._config

    def _create_connection(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": self.config.application_name})
        return session

    def _dispose(self, connection: requests.Session) -> None:
        connection.close()

    def describe_target(self) -> str:
        return self.config.base_url

    def test_connection(self) -> ConnectionTestResult:
        if not self.is_connected:
            self.connect()

        started = time.perf_counter()
        try:
            # Try to ping the base URL to check connectivity
            response = self._connection.get(
                self.config.base_url,
                timeout=self.config.timeout_seconds
            )
            response.raise_for_status()
            return ConnectionTestResult(
                success=True,
                source_type=self.source_type,
                target=self.describe_target(),
                latency_ms=(time.perf_counter() - started) * 1000,
                server_version=response.headers.get("server", "unknown")
            )
        except requests.RequestException as exc:
            return ConnectionTestResult(
                success=False,
                source_type=self.source_type,
                target=self.describe_target(),
                latency_ms=(time.perf_counter() - started) * 1000,
                error_type=type(exc).__name__,
                error_message=str(exc)
            )

    def fetch_schema(
        self, schema: str | None = None, *, include_views: bool = False
    ) -> Sequence[TableSchema]:
        """Infer a simple schema by fetching one page of data."""
        if not self.is_connected:
            self.connect()
            
        url = f"{self.config.base_url}{self.default_path}"
        try:
            response = self._connection.get(url, timeout=self.config.timeout_seconds)
            response.raise_for_status()
            data = response.json()
            
            # Simple inference: if it's a list, look at the first dict
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                first_row = data[0]
            elif isinstance(data, dict):
                # Maybe it's paginated like {"data": [...]}
                if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                    first_row = data["data"][0]
                elif "items" in data and isinstance(data["items"], list) and len(data["items"]) > 0:
                    first_row = data["items"][0]
                else:
                    first_row = data
            else:
                first_row = {}
                
            columns = []
            for key, val in first_row.items():
                val_type = type(val).__name__
                columns.append(ColumnSchema(name=key, data_type=val_type, nullable=True))
                
            table_name = self.default_path.strip("/") or "root"
            return [TableSchema(schema_name="public", table_name=table_name, columns=columns)]
            
        except (requests.RequestException, ValueError) as exc:
            self._logger.warning("Failed to infer schema: %s", exc)
            return []

    def read(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a GET request."""
        if not self.is_connected:
            self.connect()
            
        # Treat 'query' as the path appended to base_url
        url = f"{self.config.base_url}{query}"
        response = self._connection.get(url, params=params, timeout=self.config.timeout_seconds)
        response.raise_for_status()
        
        data = response.json()
        if isinstance(data, list):
            return data[:limit] if limit else data
        elif isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                return data["data"][:limit] if limit else data["data"]
            elif "items" in data and isinstance(data["items"], list):
                return data["items"][:limit] if limit else data["items"]
        
        return [data]
