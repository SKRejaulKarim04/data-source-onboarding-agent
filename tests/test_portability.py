"""Cross-platform invariants.

These are the things that only break on a machine nobody in CI is using: an
import that does not exist on Windows, a locale that is not UTF-8, a subprocess
argument the platform does not accept. Each test here stands for a failure that
was real rather than theoretical.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from dsoa.sandbox import runner
from dsoa.sandbox.runner import ConnectionSandbox

SRC = Path(__file__).resolve().parents[1] / "src" / "dsoa"
PROJECT = Path(__file__).resolve().parents[1]


# --- The sandbox ------------------------------------------------------------


def _probe_spec():  # noqa: ANN202 - the spec type is imported lazily below
    from dsoa.agent.spec import AuthMethod, AuthSpec, SourceSpec, SourceType, SqlTarget

    return SourceSpec(
        source_type=SourceType.POSTGRESQL,
        connector_name="EnvProbeConnector",
        slug="probe",
        sql_target=SqlTarget(host="localhost", port=5432, database="probe"),
        auth=AuthSpec(method=AuthMethod.USERNAME_PASSWORD, env_prefix="DSOA_PROBE_"),
    )


def test_resource_module_is_optional() -> None:
    """`import resource` raises ImportError on Windows, so it must be guarded."""
    source = (SRC / "sandbox" / "runner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for child in ast.walk(node)
        if isinstance(child, ast.Import) and any(alias.name == "resource" for alias in child.names)
    ]
    assert guarded, "import resource must sit inside a try/except ImportError"


def test_isolation_kwargs_match_the_platform() -> None:
    """preexec_fn does not exist on Windows; creationflags does not on POSIX."""
    kwargs = ConnectionSandbox()._isolation_kwargs()

    if runner.IS_WINDOWS:
        assert "preexec_fn" not in kwargs
        assert "creationflags" in kwargs
    else:
        assert kwargs["start_new_session"] is True
        assert callable(kwargs["preexec_fn"])


def test_isolation_kwargs_are_accepted_by_subprocess() -> None:
    """The strongest version of the test above: actually pass them to Popen."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", "print('ok')"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        **ConnectionSandbox()._isolation_kwargs(),
    )
    assert completed.stdout.strip() == "ok"


def test_child_env_carries_what_the_platform_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows a child interpreter will not start without SYSTEMROOT."""
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = ConnectionSandbox()._child_env(_probe_spec(), {})

    assert "PATH" in env
    if runner.IS_WINDOWS:
        assert "SYSTEMROOT" in env, "Windows children need SYSTEMROOT to import sockets"


def test_child_env_still_excludes_unrelated_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Widening the allowlist for Windows must not widen it to secrets."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-be-inherited")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-never-be-inherited")
    env = ConnectionSandbox()._child_env(_probe_spec(), {})

    assert "ANTHROPIC_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env


# --- Encoding ---------------------------------------------------------------

#: Modules that write or read files whose content is not guaranteed ASCII.
_TEXT_IO_MODULES = (
    "sandbox/runner.py",
    "validation/static.py",
    "artifacts/packager.py",
    "agent/spec.py",
    "templates/registry.py",
)


@pytest.mark.parametrize("relative", _TEXT_IO_MODULES)
def test_text_io_declares_utf8(relative: str) -> None:
    """No implicit locale encoding.

    Python uses the locale encoding for text files, which is cp1252 on a default
    Windows install. Generated connectors contain em dashes, so an unqualified
    ``write_text`` raises UnicodeEncodeError there and nowhere else.
    """
    tree = ast.parse((SRC / relative).read_text(encoding="utf-8"))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        )
        if name not in {"write_text", "read_text", "open"}:
            continue
        if not any(kw.arg == "encoding" for kw in node.keywords):
            offenders.append(f"{relative}:{node.lineno} {name}()")

    assert not offenders, "text I/O without an explicit encoding: " + ", ".join(offenders)


def test_generated_code_survives_a_round_trip_as_utf8(tmp_path: Path) -> None:
    """The characters that actually appear in generated output."""
    sample = '"""Connector — read-only · façade.\n\nGenerated ✓\n"""\n'
    target = tmp_path / "candidate.py"

    target.write_text(sample, encoding="utf-8")

    assert target.read_text(encoding="utf-8") == sample


# --- Paths and scripts ------------------------------------------------------


def test_no_hardcoded_posix_paths_in_shipped_code() -> None:
    """`/tmp` and friends do not exist on Windows; tempfile knows where to go."""
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in stripped:
                continue
            for needle in ('"/tmp/', "'/tmp/", '"/var/', "'/var/"):
                if needle in line:
                    offenders.append(f"{path.relative_to(SRC)}:{number}")
    assert not offenders, "hardcoded POSIX paths: " + ", ".join(offenders)


def test_embedded_postgres_import_handles_both_module_shapes() -> None:
    """The package is ESM with a CJS shim; `require` returns one of two shapes."""
    source = (PROJECT / "bin" / "pg-daemon.js").read_text(encoding="utf-8")
    assert ".default || " in source, (
        "pg-daemon.js must accept both `module.exports = Class` and "
        "`{ default: Class }` — the shape differs by package version"
    )


def test_postgres_log_lives_outside_the_data_directory() -> None:
    """initdb refuses a non-empty data directory, and the daemon logs first."""
    source = (PROJECT / "bin" / "pg-config.js").read_text(encoding="utf-8")
    log_line = next(line for line in source.splitlines() if "LOG_FILE:" in line)
    assert "DATA_DIR" not in log_line, (
        "the log file must not live in DATA_DIR: writing it before initdb runs "
        "makes the cluster directory non-empty and the first run fails"
    )
