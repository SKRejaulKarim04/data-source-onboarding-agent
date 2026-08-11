"""Standards checks, verified by fault injection.

A validator that has only ever seen clean code is untested. Each check here gets
a deliberately broken input and must catch it — the software equivalent of
injecting a fault to confirm the checker fires, rather than trusting a green run.

`GOOD` is a minimal conforming module; every test mutates it in one specific way.
"""

from __future__ import annotations

import pytest

from dsoa.standards import Severity, run_checks

GOOD = '''\
"""A conforming connector module."""

from __future__ import annotations

import os
from typing import Any, ClassVar

from dsoa.connectors.sql_base import SQLBaseConnector


class SalesConnector(SQLBaseConnector):
    """Connector for the sales source."""

    source_type: ClassVar[str] = "postgresql"
    driver: ClassVar[str] = "postgresql+psycopg"

    def _connect_args(self) -> dict[str, Any]:
        """Driver keyword arguments."""
        return {"connect_timeout": self.config.connect_timeout_seconds}

    def load(self, region: str) -> list[dict[str, Any]]:
        """Read rows for one region."""
        prefix = os.environ.get("DSOA_SALES_PREFIX", "")
        return self.read("SELECT * FROM sales WHERE region = :region", {"region": region})
'''


def checks_for(source: str, name: str) -> list:
    findings, _, _ = run_checks(source)
    return [f for f in findings if f.check == name or f.check.startswith(f"{name}:")]


def errors(source: str) -> list:
    findings, _, _ = run_checks(source)
    return [f for f in findings if f.severity is Severity.ERROR]


# ---- Baseline --------------------------------------------------------------


def test_conforming_module_produces_no_errors() -> None:
    assert errors(GOOD) == []


def test_all_checks_pass_on_the_baseline() -> None:
    _, run, passed = run_checks(GOOD)
    assert passed == run


# ---- Fault injection: credentials ------------------------------------------


@pytest.mark.parametrize(
    "injected",
    [
        '    password = "hunter2"',
        '    api_key: str = "sk-live-abc123"',
        '    self.client_secret = "s3cr3t"',
    ],
)
def test_hardcoded_credential_assignment_is_caught(injected: str) -> None:
    broken = GOOD.replace(
        '    driver: ClassVar[str] = "postgresql+psycopg"',
        '    driver: ClassVar[str] = "postgresql+psycopg"\n' + injected,
    )
    assert checks_for(broken, "no-hardcoded-credentials")


def test_credential_passed_as_a_keyword_argument_is_caught() -> None:
    broken = GOOD.replace(
        'return {"connect_timeout": self.config.connect_timeout_seconds}',
        'return dict(connect_timeout=1, password="hunter2")',
    )
    assert checks_for(broken, "no-hardcoded-credentials")


def test_credential_inside_a_dict_literal_is_caught() -> None:
    broken = GOOD.replace(
        'return {"connect_timeout": self.config.connect_timeout_seconds}',
        'return {"password": "hunter2"}',
    )
    assert checks_for(broken, "no-hardcoded-credentials")


def test_empty_string_is_not_flagged_as_a_credential() -> None:
    """A placeholder is not a leak; flagging it trains people to ignore the check."""
    broken = GOOD.replace(
        '    driver: ClassVar[str] = "postgresql+psycopg"',
        '    driver: ClassVar[str] = "postgresql+psycopg"\n    password = ""',
    )
    assert not checks_for(broken, "no-hardcoded-credentials")


def test_module_with_no_env_lookup_is_caught() -> None:
    broken = GOOD.replace('        prefix = os.environ.get("DSOA_SALES_PREFIX", "")\n', "")
    broken = broken.replace("import os\n", "")
    assert checks_for(broken, "env-for-secrets")


# ---- Fault injection: SQL --------------------------------------------------


@pytest.mark.parametrize(
    "injected",
    [
        'return self.read(f"SELECT * FROM sales WHERE region = {region}")',
        'return self.read("SELECT * FROM sales WHERE region = " + region)',
        'return self.read("SELECT * FROM sales WHERE region = %s" % region)',
        'return self.read("SELECT * FROM sales WHERE region = {}".format(region))',
    ],
)
def test_dynamic_sql_is_caught(injected: str) -> None:
    broken = GOOD.replace(
        'return self.read("SELECT * FROM sales WHERE region = :region", {"region": region})',
        injected,
    )
    assert checks_for(broken, "no-dynamic-sql")


def test_bound_parameters_are_not_flagged() -> None:
    assert not checks_for(GOOD, "no-dynamic-sql")


# ---- Fault injection: dangerous calls --------------------------------------


@pytest.mark.parametrize(
    "injected",
    [
        "        eval(region)",
        "        exec(region)",
        "        os.system(region)",
        "        subprocess.run([region])",
        "        pickle.loads(region.encode())",
    ],
)
def test_dangerous_calls_are_caught(injected: str) -> None:
    broken = GOOD.replace(
        '        prefix = os.environ.get("DSOA_SALES_PREFIX", "")',
        '        prefix = os.environ.get("DSOA_SALES_PREFIX", "")\n' + injected,
    )
    assert checks_for(broken, "no-dangerous-calls")


# ---- Fault injection: structure --------------------------------------------


def test_class_not_extending_the_base_is_caught() -> None:
    broken = GOOD.replace("class SalesConnector(SQLBaseConnector):", "class SalesConnector:")
    assert checks_for(broken, "subclasses-base-connector")


def test_bad_class_name_is_caught() -> None:
    broken = GOOD.replace(
        "class SalesConnector(SQLBaseConnector):", "class sales_thing(SQLBaseConnector):"
    )
    assert checks_for(broken, "class-naming")


def test_missing_source_type_is_caught() -> None:
    broken = GOOD.replace('    source_type: ClassVar[str] = "postgresql"\n', "")
    assert checks_for(broken, "declares-source-type")


def test_print_is_caught() -> None:
    broken = GOOD.replace(
        '        prefix = os.environ.get("DSOA_SALES_PREFIX", "")', '        print("loading")'
    )
    assert checks_for(broken, "no-print")


def test_bare_except_is_an_error() -> None:
    broken = GOOD.replace(
        '        prefix = os.environ.get("DSOA_SALES_PREFIX", "")',
        "        try:\n            pass\n        except:\n            pass",
    )
    findings = checks_for(broken, "no-bare-except")
    assert findings and findings[0].severity is Severity.ERROR


def test_broad_except_is_only_a_warning() -> None:
    broken = GOOD.replace(
        '        prefix = os.environ.get("DSOA_SALES_PREFIX", "")',
        "        try:\n            pass\n        except Exception:\n            pass",
    )
    findings = checks_for(broken, "no-bare-except")
    assert findings and findings[0].severity is Severity.WARNING


def test_wildcard_import_is_caught() -> None:
    broken = GOOD.replace("import os", "from os import *")
    assert checks_for(broken, "no-wildcard-imports")


def test_missing_return_annotation_is_caught() -> None:
    broken = GOOD.replace(
        "def load(self, region: str) -> list[dict[str, Any]]:", "def load(self, region: str):"
    )
    assert checks_for(broken, "type-hints")


def test_missing_parameter_annotation_is_caught() -> None:
    broken = GOOD.replace(
        "def load(self, region: str) -> list[dict[str, Any]]:",
        "def load(self, region) -> list[dict[str, Any]]:",
    )
    assert checks_for(broken, "type-hints")


def test_missing_docstrings_are_caught() -> None:
    broken = GOOD.replace('    """Connector for the sales source."""\n\n', "")
    assert checks_for(broken, "docstrings")


def test_missing_module_docstring_is_caught() -> None:
    broken = GOOD.replace('"""A conforming connector module."""\n\n', "")
    assert checks_for(broken, "docstrings")


def test_todo_marker_is_a_warning_not_a_blocker() -> None:
    broken = GOOD.replace(
        '"""A conforming connector module."""', '"""A conforming connector module. TODO: finish."""'
    )
    findings = checks_for(broken, "no-todo-markers")
    assert findings and findings[0].severity is Severity.WARNING
    assert not errors(broken)


# ---- Findings quality ------------------------------------------------------


def test_every_error_carries_an_actionable_remedy() -> None:
    """The repair loop consumes these. A finding without a remedy is dead weight."""
    broken = GOOD.replace(
        '    driver: ClassVar[str] = "postgresql+psycopg"', '    password = "hunter2"'
    )
    for finding in errors(broken):
        assert finding.remedy, f"{finding.check} has no remedy"


def test_findings_report_line_numbers() -> None:
    broken = GOOD.replace(
        '        prefix = os.environ.get("DSOA_SALES_PREFIX", "")', '        print("x")'
    )
    assert all(f.line for f in checks_for(broken, "no-print"))


def test_syntax_error_propagates() -> None:
    with pytest.raises(SyntaxError):
        run_checks("def broken(:\n    pass")
