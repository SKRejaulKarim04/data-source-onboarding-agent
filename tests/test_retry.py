"""Retry policy tests."""

from __future__ import annotations

import pytest

from dsoa.connectors import retry_on_transient
from dsoa.connectors.exceptions import (
    AuthenticationError,
    TransientConnectionError,
)


def test_succeeds_on_first_attempt() -> None:
    calls = []

    @retry_on_transient(max_attempts=3, backoff_seconds=0.001)
    def works() -> str:
        calls.append(1)
        return "ok"

    assert works() == "ok"
    assert len(calls) == 1


def test_retries_then_succeeds() -> None:
    calls = []

    @retry_on_transient(max_attempts=3, backoff_seconds=0.001)
    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise TransientConnectionError("network blip")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3


def test_gives_up_after_max_attempts() -> None:
    calls = []

    @retry_on_transient(max_attempts=3, backoff_seconds=0.001)
    def always_fails() -> None:
        calls.append(1)
        raise TransientConnectionError("still down", host="db")

    with pytest.raises(TransientConnectionError) as excinfo:
        always_fails()

    assert len(calls) == 3
    assert excinfo.value.context["attempts"] == 3
    assert excinfo.value.context["host"] == "db"


def test_non_transient_errors_are_not_retried() -> None:
    calls = []

    @retry_on_transient(max_attempts=5, backoff_seconds=0.001)
    def bad_credentials() -> None:
        calls.append(1)
        raise AuthenticationError("wrong password")

    with pytest.raises(AuthenticationError):
        bad_credentials()

    assert len(calls) == 1


def test_preserves_function_metadata() -> None:
    @retry_on_transient()
    def documented() -> None:
        """Original docstring."""

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Original docstring."


def test_rejects_invalid_max_attempts() -> None:
    with pytest.raises(ValueError):
        retry_on_transient(max_attempts=0)
