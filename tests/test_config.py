"""Configuration and secret-handling tests.

The masking tests are not ceremony. Phase 4 runs generated code in a sandbox and
streams its logs to the browser; a password reaching a log line is a real
incident, so it gets a real test.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dsoa.connectors import ConfigurationError, SqlConnectionConfig


def test_from_env_reads_required_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_HOST", "db.internal")
    monkeypatch.setenv("TEST_PORT", "5432")
    monkeypatch.setenv("TEST_DATABASE", "analytics")
    monkeypatch.setenv("TEST_USERNAME", "svc_reader")
    monkeypatch.setenv("TEST_PASSWORD", "s3cr3t")

    config = SqlConnectionConfig.from_env("TEST_")

    assert config.host == "db.internal"
    assert config.port == 5432
    assert config.password.get_secret_value() == "s3cr3t"


def test_from_env_reports_every_missing_variable_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("TEST_HOST", "TEST_PORT", "TEST_DATABASE", "TEST_USERNAME", "TEST_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigurationError) as excinfo:
        SqlConnectionConfig.from_env("TEST_")

    missing = excinfo.value.context["variables"]
    assert "TEST_HOST" in missing
    assert "TEST_PASSWORD" in missing
    assert len(missing) == 5


def test_default_port_fills_in_when_env_omits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_HOST", "db.internal")
    monkeypatch.delenv("TEST_PORT", raising=False)
    monkeypatch.setenv("TEST_DATABASE", "analytics")
    monkeypatch.setenv("TEST_USERNAME", "svc_reader")
    monkeypatch.setenv("TEST_PASSWORD", "s3cr3t")

    config = SqlConnectionConfig.from_env("TEST_", default_port=5432)

    assert config.port == 5432


def test_optional_tuning_is_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "TEST_HOST": "db.internal",
        "TEST_PORT": "5432",
        "TEST_DATABASE": "analytics",
        "TEST_USERNAME": "svc_reader",
        "TEST_PASSWORD": "s3cr3t",
        "TEST_POOL_SIZE": "17",
        "TEST_SSL_MODE": "require",
    }.items():
        monkeypatch.setenv(key, value)

    config = SqlConnectionConfig.from_env("TEST_")

    assert config.pool_size == 17
    assert config.ssl_mode == "require"


def test_password_never_appears_in_repr_or_dump(
    dummy_config: SqlConnectionConfig,
) -> None:
    assert "not-a-real-password" not in repr(dummy_config)
    assert "not-a-real-password" not in str(dummy_config)
    assert "not-a-real-password" not in str(dummy_config.model_dump())


def test_masked_dsn_hides_the_password(dummy_config: SqlConnectionConfig) -> None:
    dsn = dummy_config.masked_dsn("postgresql+psycopg")

    assert dsn == "postgresql+psycopg://tester:***@localhost:5432/testdb"
    assert "not-a-real-password" not in dsn


def test_host_rejects_a_url() -> None:
    with pytest.raises(ValidationError):
        SqlConnectionConfig(
            host="postgresql://db.internal",
            port=5432,
            database="analytics",
            username="svc",
            password="pw",
        )


def test_config_is_immutable(dummy_config: SqlConnectionConfig) -> None:
    with pytest.raises(ValidationError):
        dummy_config.host = "somewhere-else"  # type: ignore[misc]


@pytest.mark.parametrize("port", [0, -1, 70000])
def test_invalid_ports_are_rejected(port: int) -> None:
    with pytest.raises(ValidationError):
        SqlConnectionConfig(
            host="db",
            port=port,
            database="analytics",
            username="svc",
            password="pw",
        )
