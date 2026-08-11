"""Docs generation, sandbox isolation, and artifact packaging."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest

from dsoa.agent.llm import ScriptedClient
from dsoa.agent.spec import AuthMethod, SourceType, SpecDraft
from dsoa.artifacts import ArtifactPackager
from dsoa.docs_gen import DocsGenerator
from dsoa.generation import ConnectorGenerator
from dsoa.sandbox import ConnectionSandbox

FIXED_TIME = "2026-08-07T00:00:00Z"


@pytest.fixture
def spec():
    return SpecDraft(
        source_type=SourceType.POSTGRESQL,
        connector_name="ReportingConnector",
        host="reporting-db.internal",
        database="analytics",
        auth_method=AuthMethod.USERNAME_PASSWORD,
    ).finalize()


@pytest.fixture
def connector(spec):
    return ConnectorGenerator().generate(spec, generated_at=FIXED_TIME)


# ---- Docs ------------------------------------------------------------------


def test_readme_documents_the_required_env_vars(connector) -> None:
    readme = DocsGenerator().readme(connector)

    for var in connector.spec.auth.secret_env_vars:
        assert var in readme


def test_readme_states_the_access_level(connector) -> None:
    assert "Read-only" in DocsGenerator().readme(connector)


def test_requirements_include_the_driver(connector) -> None:
    requirements = DocsGenerator().requirements(connector)

    assert "psycopg" in requirements
    assert "sqlalchemy" in requirements.lower()


def test_explanation_falls_back_to_a_template_without_a_client(connector) -> None:
    text, source = DocsGenerator().explain(connector)

    assert source == "template"
    assert "ReportingConnector" in text
    assert len(text) > 400


def test_explanation_uses_the_model_when_available(connector) -> None:
    client = ScriptedClient(
        [{"explanation": "It connects to a database.", "review_notes": ["Check grants."]}]
    )
    text, source = DocsGenerator(client).explain(connector)

    assert source == "model"
    assert "Check grants." in text


def test_explanation_falls_back_when_the_model_returns_nothing(connector) -> None:
    _, source = DocsGenerator(ScriptedClient(default={})).explain(connector)
    assert source == "template"


def test_docs_never_contain_a_credential_value(connector) -> None:
    docs = DocsGenerator().generate(connector)
    blob = (docs.readme + docs.requirements + docs.explanation).lower()

    for leak in ("hunter2", "sk-live", "p@ssw0rd"):
        assert leak not in blob


# ---- Artifacts -------------------------------------------------------------


def test_artifact_bundles_all_five_files(connector) -> None:
    artifact = ArtifactPackager().package(connector, DocsGenerator().generate(connector))

    assert set(artifact.files) == {
        connector.module_name,
        "README.md",
        "requirements.txt",
        "EXPLANATION.md",
        "manifest.json",
    }


def test_manifest_records_the_full_provenance_chain(connector) -> None:
    artifact = ArtifactPackager().package(connector, DocsGenerator().generate(connector))
    provenance = artifact.manifest["provenance"]

    assert provenance["template_key"] == "postgresql:username_password"
    assert provenance["template_version"] == "1.0.0"
    assert provenance["spec_checksum"] == connector.spec_checksum
    assert provenance["code_checksum"] == connector.code_checksum


def test_manifest_lists_env_var_names_only(connector) -> None:
    """A manifest carrying values would defeat the whole design."""
    artifact = ArtifactPackager().package(connector, DocsGenerator().generate(connector))
    blob = json.dumps(artifact.manifest)

    assert "DSOA_ANALYTICS_PASSWORD" in blob
    for leak in ("hunter2", "secret_value"):
        assert leak not in blob.lower()


def test_manifest_records_untested_connectivity(connector) -> None:
    artifact = ArtifactPackager().package(connector, DocsGenerator().generate(connector))
    assert artifact.manifest["connectivity"] == {"tested": False}


def test_zip_is_readable_and_contains_the_module(connector) -> None:
    artifact = ArtifactPackager().package(connector, DocsGenerator().generate(connector))

    with zipfile.ZipFile(BytesIO(artifact.to_zip())) as archive:
        names = archive.namelist()
        assert f"{artifact.name}/{connector.module_name}" in names
        assert f"{artifact.name}/manifest.json" in names


def test_packaging_is_reproducible(connector) -> None:
    """Fixed zip timestamps — same reproducibility argument as the checksum."""
    docs = DocsGenerator().generate(connector)
    packager = ArtifactPackager()

    assert packager.package(connector, docs).to_zip() == packager.package(connector, docs).to_zip()


def test_artifact_writes_to_disk(connector, tmp_path) -> None:
    artifact = ArtifactPackager().package(connector, DocsGenerator().generate(connector))
    root = artifact.write_to(tmp_path)

    assert (root / connector.module_name).exists()
    assert (root / "README.md").exists()


# ---- Sandbox ---------------------------------------------------------------


def test_sandbox_reports_failure_rather_than_raising(connector) -> None:
    """The host does not exist; this must be a result, not an exception."""
    result = ConnectionSandbox(timeout_seconds=20).run(connector.code, connector.spec, {})

    assert result.success is False
    assert result.error
    assert result.summary().startswith("FAILED")


def test_sandbox_strips_the_parent_environment(connector, monkeypatch) -> None:
    """A generated connector must not be able to read the app's own secrets."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-parent-secret")
    monkeypatch.setenv("UNRELATED_SECRET", "should-not-leak")

    sandbox = ConnectionSandbox()
    env = sandbox._child_env(connector.spec, {})

    assert "ANTHROPIC_API_KEY" not in env
    assert "UNRELATED_SECRET" not in env


def test_sandbox_passes_only_prefix_matched_credentials(connector) -> None:
    env = ConnectionSandbox()._child_env(
        connector.spec,
        {"DSOA_ANALYTICS_PASSWORD": "correct", "OTHER_APP_PASSWORD": "wrong-prefix"},
    )

    assert env["DSOA_ANALYTICS_PASSWORD"] == "correct"
    assert "OTHER_APP_PASSWORD" not in env


def test_sandbox_times_out_on_a_hanging_module(connector) -> None:
    hanging = "import time\ntime.sleep(120)\n"
    result = ConnectionSandbox(timeout_seconds=2).run(hanging, connector.spec, {})

    assert result.timed_out
    assert "TIMEOUT" in result.summary()


def test_sandbox_survives_a_module_that_raises_on_import(connector) -> None:
    result = ConnectionSandbox(timeout_seconds=10).run(
        'raise RuntimeError("boom on import")\n', connector.spec, {}
    )

    assert not result.success
    assert result.error


def test_sandbox_parses_the_last_json_line_not_the_first() -> None:
    """Drivers write warnings to stdout; the result is the last line."""
    parsed = ConnectionSandbox._parse('{"noise": true}\nsome warning\n{"success": true}')
    assert parsed == {"success": True}
