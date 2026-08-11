"""End-to-end generation: spec in, validated artifact out."""

from __future__ import annotations

import ast

import pytest

from dsoa.agent.llm import ScriptedClient
from dsoa.agent.spec import AuthMethod, SourceType, SpecDraft
from dsoa.generation import ConnectorGenerator

FIXED_TIME = "2026-08-07T00:00:00Z"


def make_spec(source_type=SourceType.POSTGRESQL, **overrides):
    fields = {
        "source_type": source_type,
        "connector_name": "ReportingConnector",
        "host": "reporting-db.internal",
        "database": "analytics",
        "auth_method": AuthMethod.USERNAME_PASSWORD,
    }
    fields.update(overrides)
    return SpecDraft(**fields).finalize()


@pytest.mark.parametrize(
    "source_type", [SourceType.POSTGRESQL, SourceType.MYSQL, SourceType.SQLSERVER]
)
def test_every_dialect_generates_an_accepted_artifact(source_type: SourceType) -> None:
    """The headline claim: templates produce conforming code every time."""
    result = ConnectorGenerator().generate(make_spec(source_type), generated_at=FIXED_TIME)

    assert result.accepted, result.report.summary()
    assert result.report.conformance_pct == 100.0
    assert not result.repair_attempts  # deterministic output needs no repair
    ast.parse(result.code)


def test_artifact_carries_full_provenance() -> None:
    result = ConnectorGenerator().generate(make_spec(), generated_at=FIXED_TIME)

    assert result.template_key == "postgresql:username_password"
    assert result.template_version == "1.0.0"
    assert len(result.spec_checksum) == 12
    assert len(result.code_checksum) == 12
    assert result.generated_at == FIXED_TIME


def test_generation_is_reproducible() -> None:
    a = ConnectorGenerator().generate(make_spec(), generated_at=FIXED_TIME)
    b = ConnectorGenerator().generate(make_spec(), generated_at=FIXED_TIME)

    assert a.code_checksum == b.code_checksum


def test_semver_encodes_template_version_and_repair_count() -> None:
    result = ConnectorGenerator().generate(make_spec(), generated_at=FIXED_TIME)
    assert result.semver == "1.0.0"


def test_generated_code_contains_no_credentials() -> None:
    result = ConnectorGenerator().generate(make_spec(), generated_at=FIXED_TIME)

    lowered = result.code.lower()
    for leak in ("hunter2", "sk-live", "secret=", "pwd="):
        assert leak not in lowered


def test_env_var_names_are_documented_in_the_artifact() -> None:
    result = ConnectorGenerator().generate(make_spec(), generated_at=FIXED_TIME)

    for var in result.spec.auth.secret_env_vars:
        assert var in result.code


def test_unsupported_template_key_raises() -> None:
    from dsoa.connectors.exceptions import ConfigurationError
    from dsoa.templates.registry import TemplateRegistry

    empty = TemplateRegistry(entries=[])
    with pytest.raises(ConfigurationError):
        ConnectorGenerator(registry=empty).generate(make_spec())


def test_missing_tools_are_surfaced_as_warnings() -> None:
    from dsoa.validation import StaticValidator

    generator = ConnectorGenerator(
        validator=StaticValidator(run_ruff=True, run_black=True, run_bandit=True)
    )
    result = generator.generate(make_spec(), generated_at=FIXED_TIME)

    if result.report.tools_skipped:
        assert any("did not run" in w for w in result.warnings)


def test_repair_client_is_optional() -> None:
    """Deterministic templates mean the common path never needs a model."""
    result = ConnectorGenerator(repair_client=None).generate(make_spec(), generated_at=FIXED_TIME)
    assert result.accepted


def test_repair_engages_when_a_template_regresses(tmp_path) -> None:
    """Simulates the case the repair loop actually exists for."""
    from dsoa.templates.renderer import ConnectorRenderer

    bad_template = '''\
"""Broken template output."""

from dsoa.connectors.sql_base import SQLBaseConnector


class {{ spec.connector_name }}(SQLBaseConnector):
    """A connector."""

    source_type = "{{ spec.source_type.value }}"
    password = "hunter2"

    def load(self):
        print("loading")
'''
    (tmp_path / "sql_connector.py.j2").write_text(bad_template)

    good = ConnectorGenerator().generate(make_spec(), generated_at=FIXED_TIME).code
    generator = ConnectorGenerator(
        renderer=ConnectorRenderer(template_dir=tmp_path),
        repair_client=ScriptedClient([{"code": good}]),
    )
    result = generator.generate(make_spec(), generated_at=FIXED_TIME)

    assert result.repair_attempts
    assert result.accepted
    assert result.semver == "1.0.1"  # patch bumped by the repair pass


def test_failed_artifact_is_still_returned_for_review(tmp_path) -> None:
    """A rejected artifact must be inspectable, not swallowed."""
    from dsoa.templates.renderer import ConnectorRenderer

    (tmp_path / "sql_connector.py.j2").write_text(
        'password = "hunter2"\nprint("{{ spec.connector_name }}")\n'
    )
    generator = ConnectorGenerator(renderer=ConnectorRenderer(template_dir=tmp_path))
    result = generator.generate(make_spec(), generated_at=FIXED_TIME)

    assert not result.accepted
    assert result.code
    assert result.report.errors
    assert any("no repair client" in w for w in result.warnings)
