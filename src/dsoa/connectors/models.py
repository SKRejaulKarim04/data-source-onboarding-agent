"""Return types shared by every connector.

These are the contract the API layer and the frontend code against. Keeping them
source-type-neutral is what lets one React component render a validation result
for Postgres, MySQL, SQL Server, or a REST API without branching.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ColumnSchema(BaseModel):
    """One column of an introspected table."""

    model_config = ConfigDict(frozen=True)

    name: str
    data_type: str
    nullable: bool
    primary_key: bool = False
    default: str | None = None


class TableSchema(BaseModel):
    """One introspected table or view."""

    model_config = ConfigDict(frozen=True)

    schema_name: str
    table_name: str
    columns: tuple[ColumnSchema, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"


class ConnectionTestResult(BaseModel):
    """Outcome of a connectivity check.

    This is the object the Phase 4 sandbox returns to the API, and it is what
    populates the validation screen. A failed test is a *result*, not an
    exception — the agent needs to reason about the failure text.
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    source_type: str
    target: str = Field(description="Masked DSN or base URL — safe to display")
    latency_ms: float | None = None
    server_version: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    tested_at: datetime = Field(default_factory=_utcnow)

    def summary(self) -> str:
        if self.success:
            latency = f"{self.latency_ms:.0f}ms" if self.latency_ms else "n/a"
            version = self.server_version or "unknown version"
            return f"OK · {self.source_type} · {latency} · {version}"
        return f"FAILED · {self.source_type} · {self.error_type}: {self.error_message}"
