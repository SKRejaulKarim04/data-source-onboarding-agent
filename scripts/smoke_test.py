#!/usr/bin/env python3
"""End-to-end smoke test against the running Postgres container.

This is your Phase 1 exit criterion. When this prints all green, the framework
is real and you can start pointing an LLM at it.

Run::

    make up
    set -a && . ./.env && set +a
    python scripts/smoke_test.py
"""

from __future__ import annotations

import sys

from dsoa.connectors import ConfigurationError, PostgresqlConnector
from dsoa.logging_config import configure_logging

GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def _ok(label: str, detail: str = "") -> None:
    print(f"  {GREEN}PASS{RESET}  {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))


def _fail(label: str, detail: str = "") -> None:
    print(f"  {RED}FAIL{RESET}  {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))


def main() -> int:
    configure_logging(level="WARNING")
    print("\nData Source Onboarding Agent — Phase 1 smoke test\n")

    try:
        connector = PostgresqlConnector.from_env()
    except ConfigurationError as exc:
        _fail("Load configuration from environment", str(exc))
        print("\nDid you run:  set -a && . ./.env && set +a\n")
        return 1

    _ok("Load configuration from environment", connector.describe_target())

    failures = 0

    with connector:
        result = connector.test_connection()
        if result.success:
            _ok("Connectivity", result.summary())
        else:
            _fail("Connectivity", result.summary())
            return 1

        try:
            tables = connector.fetch_schema()
            names = ", ".join(t.table_name for t in tables)
            _ok(f"Schema introspection ({len(tables)} tables)", names)
        except Exception as exc:
            _fail("Schema introspection", str(exc))
            failures += 1

        try:
            rows = connector.read(
                "SELECT name, tier FROM customers WHERE region = :region ORDER BY name",
                {"region": "APAC"},
            )
            _ok(
                f"Parameterized read ({len(rows)} rows)",
                ", ".join(r["name"] for r in rows),
            )
        except Exception as exc:
            _fail("Parameterized read", str(exc))
            failures += 1

        try:
            connector.read("DELETE FROM customers")
            _fail("Read-only guard", "a DELETE was allowed through")
            failures += 1
        except Exception as exc:
            _ok("Read-only guard", type(exc).__name__)

        try:
            connector.read("SELECT 1; DROP TABLE customers")
            _fail("Multi-statement guard", "payload was allowed through")
            failures += 1
        except Exception as exc:
            _ok("Multi-statement guard", type(exc).__name__)

    if not connector.is_connected:
        _ok("Connection closed by context manager")
    else:
        _fail("Connection closed by context manager")
        failures += 1

    print()
    if failures:
        print(f"{RED}{failures} check(s) failed.{RESET}\n")
        return 1
    print(f"{GREEN}Phase 1 complete.{RESET} The framework works. Start Phase 2.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
