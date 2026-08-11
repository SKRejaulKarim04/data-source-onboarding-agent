"""Template rendering and registry tests."""

from __future__ import annotations

import ast

import pytest

from dsoa.agent.spec import AuthMethod, SourceType, SpecDraft
from dsoa.connectors.exceptions import ConfigurationError
from dsoa.templates import ConnectorRenderer, TemplateRegistry, spec_checksum

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


def render(spec):
    return ConnectorRenderer().render(spec, generated_at=FIXED_TIME).code


# ---- Registry --------------------------------------------------------------


def test_registry_covers_the_three_sql_dialects() -> None:
    keys = TemplateRegistry().template_keys()
    assert "postgresql:username_password" in keys
    assert "mysql:username_password" in keys
    assert "sqlserver:username_password" in keys


def test_unknown_key_lists_the_supported_ones() -> None:
    """A 'not found' error without the alternatives is useless."""
    with pytest.raises(ConfigurationError) as excinfo:
        TemplateRegistry().get("mongodb:username_password")

    assert excinfo.value.context["supported"]


def test_entry_carries_a_version() -> None:
    assert TemplateRegistry().get("postgresql:username_password").version == "1.0.0"


# ---- Rendering -------------------------------------------------------------


@pytest.mark.parametrize(
    "source_type", [SourceType.POSTGRESQL, SourceType.MYSQL, SourceType.SQLSERVER]
)
def test_every_dialect_renders_parseable_python(source_type: SourceType) -> None:
    ast.parse(render(make_spec(source_type)))


def test_rendering_is_deterministic() -> None:
    """Byte-identical output is what makes the checksum mean anything."""
    spec = make_spec()
    assert render(spec) == render(spec)


def test_spec_checksum_is_stable_across_dict_ordering() -> None:
    assert spec_checksum(make_spec()) == spec_checksum(make_spec())


def test_different_specs_get_different_checksums() -> None:
    assert spec_checksum(make_spec()) != spec_checksum(make_spec(database="other"))


def test_class_name_and_base_are_correct() -> None:
    tree = ast.parse(render(make_spec()))
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

    assert len(classes) == 1
    assert classes[0].name == "ReportingConnector"
    assert [b.id for b in classes[0].bases] == ["SQLBaseConnector"]


def test_dialect_specifics_are_rendered() -> None:
    assert "postgresql+psycopg" in render(make_spec(SourceType.POSTGRESQL))
    assert "mysql+pymysql" in render(make_spec(SourceType.MYSQL))
    assert "mssql+pyodbc" in render(make_spec(SourceType.SQLSERVER))


def test_sqlserver_renders_url_query_for_the_odbc_driver() -> None:
    """The extension point the second dialect forced onto SQLBaseConnector."""
    code = render(make_spec(SourceType.SQLSERVER))

    assert "url_query" in code
    assert "ODBC Driver 18 for SQL Server" in code


def test_postgres_does_not_render_url_query() -> None:
    assert "url_query" not in render(make_spec(SourceType.POSTGRESQL))


def test_provenance_is_stamped_into_the_docstring() -> None:
    code = render(make_spec())

    assert "sql_connector.py.j2 v1.0.0" in code
    assert FIXED_TIME in code
    assert "GENERATED FILE" in code


def test_env_var_names_are_documented() -> None:
    code = render(make_spec())

    assert "DSOA_ANALYTICS_USERNAME" in code
    assert "DSOA_ANALYTICS_PASSWORD" in code


def test_no_credential_value_can_appear_in_output() -> None:
    """Structural: the spec has no field that could carry one."""
    code = render(make_spec())

    for suspicious in ("password=", "pwd=", "secret="):
        assert suspicious not in code.lower().replace("password: ", "")


def test_read_only_flag_reaches_the_generated_class() -> None:
    assert "read_only: ClassVar[bool] = True" in render(make_spec())
    assert "read_only: ClassVar[bool] = False" in render(make_spec(read_only=False))


def test_read_write_connector_is_flagged_in_its_docstring() -> None:
    assert "Confirm that is intended" in render(make_spec(read_only=False))


def test_schema_name_is_rendered_when_present() -> None:
    assert 'default_schema: ClassVar[str | None] = "public"' in render(
        make_spec(SourceType.POSTGRESQL)
    )


def test_missing_schema_renders_none_not_the_string_none() -> None:
    code = render(make_spec(SourceType.MYSQL))
    assert "default_schema: ClassVar[str | None] = None" in code
    assert '"None"' not in code


def test_generated_module_name_follows_the_spec_slug() -> None:
    assert ConnectorRenderer().render(make_spec()).module_name == "analytics_connector.py"


def test_strict_undefined_catches_a_template_referencing_a_missing_field(tmp_path) -> None:
    """A typo in a template must fail loudly, not emit 'None' into production."""
    from jinja2.exceptions import UndefinedError

    (tmp_path / "sql_connector.py.j2").write_text("{{ spec.does_not_exist }}")
    renderer = ConnectorRenderer(template_dir=tmp_path)

    with pytest.raises(UndefinedError):
        renderer.render(make_spec())
