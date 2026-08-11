"""Connection configuration.

Enterprise standard enforced here: **credentials are never accepted as literals
in generated code**. A connector is constructed from a config object, and the
config object's canonical constructor is :meth:`SqlConnectionConfig.from_env`.
Every template renders code that calls ``from_env`` — so a generated connector
physically cannot contain a hardcoded password.

``password`` is a ``SecretStr``: it will not appear in reprs, logs, tracebacks,
or JSON dumps unless something explicitly calls ``get_secret_value()``, which
happens in exactly one place (URL construction).
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .exceptions import ConfigurationError


class SqlConnectionConfig(BaseModel):
    """Connection parameters shared by every SQL source type."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: SecretStr

    # Dialect-neutral tuning. Templates expose these; the agent fills them from
    # the parsed SourceSpec in Phase 2.
    ssl_mode: str = "prefer"
    connect_timeout_seconds: int = Field(default=10, ge=1, le=300)
    query_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=5, ge=0, le=100)
    pool_recycle_seconds: int = Field(default=1800, ge=-1)
    pool_pre_ping: bool = True
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=0.5, gt=0, le=30)
    application_name: str = "dsoa-connector"

    @field_validator("host")
    @classmethod
    def _strip_scheme(cls, value: str) -> str:
        """Reject a URL where a hostname belongs — a common LLM mistake."""
        if "://" in value:
            raise ValueError("host must be a hostname, not a URL")
        return value.strip()

    @classmethod
    def from_env(
        cls,
        prefix: str,
        *,
        default_port: int | None = None,
        **overrides: Any,
    ) -> SqlConnectionConfig:
        """Build a config from environment variables.

        Reads ``{prefix}HOST``, ``{prefix}PORT``, ``{prefix}DATABASE``,
        ``{prefix}USERNAME``, ``{prefix}PASSWORD`` plus any optional tuning
        variable named after a field. Explicit ``overrides`` win over the
        environment, which keeps tests readable.

        Raises:
            ConfigurationError: if any required variable is absent, listing all
                of them at once rather than failing on the first.
        """
        required = ("host", "port", "database", "username", "password")
        values: dict[str, Any] = {}
        missing: list[str] = []

        for field in required:
            if field in overrides:
                continue
            env_key = f"{prefix}{field.upper()}"
            raw = os.environ.get(env_key)
            if raw is None or raw == "":
                if field == "port" and default_port is not None:
                    values["port"] = default_port
                    continue
                missing.append(env_key)
            else:
                values[field] = raw

        if missing:
            raise ConfigurationError(
                "Missing required environment variables", variables=sorted(missing)
            )

        optional = {name for name in cls.model_fields if name not in required}
        for field in optional:
            env_key = f"{prefix}{field.upper()}"
            raw = os.environ.get(env_key)
            if raw is not None and raw != "":
                values[field] = raw

        values.update(overrides)

        try:
            return cls(**values)
        except Exception as exc:  # pydantic ValidationError
            raise ConfigurationError(
                f"Invalid connection configuration: {exc}", prefix=prefix
            ) from exc

    def masked_dsn(self, driver: str) -> str:
        """A DSN safe to log, show in the UI, and paste into a bug report."""
        return f"{driver}://{self.username}:***@{self.host}:{self.port}/{self.database}"


class RestConnectionConfig(BaseModel):
    """Connection parameters shared by REST API sources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = Field(..., min_length=1)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=0.5, gt=0, le=30)
    application_name: str = "dsoa-connector"

    @field_validator("base_url")
    @classmethod
    def _require_scheme(cls, value: str) -> str:
        """Require a URL scheme."""
        if not value.startswith("http://") and not value.startswith("https://"):
            raise ValueError("base_url must start with http:// or https://")
        return value.rstrip("/")

    @classmethod
    def from_env(
        cls,
        prefix: str,
        **overrides: Any,
    ) -> RestConnectionConfig:
        """Build a config from environment variables.

        Reads ``{prefix}BASE_URL`` plus any optional tuning variable named after a field.
        """
        required = ("base_url",)
        values: dict[str, Any] = {}
        missing: list[str] = []

        for field in required:
            if field in overrides:
                continue
            env_key = f"{prefix}{field.upper()}"
            raw = os.environ.get(env_key)
            if raw is None or raw == "":
                missing.append(env_key)
            else:
                values[field] = raw

        if missing:
            raise ConfigurationError(
                "Missing required environment variables", variables=sorted(missing)
            )

        optional = {name for name in cls.model_fields if name not in required}
        for field in optional:
            env_key = f"{prefix}{field.upper()}"
            raw = os.environ.get(env_key)
            if raw is not None and raw != "":
                values[field] = raw

        values.update(overrides)

        try:
            return cls(**values)
        except Exception as exc:  # pydantic ValidationError
            raise ConfigurationError(
                f"Invalid connection configuration: {exc}", prefix=prefix
            ) from exc
