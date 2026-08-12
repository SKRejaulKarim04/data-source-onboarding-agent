"""Running generated code, carefully.

This is the only place in the project that executes a generated connector. Every
other stage reads the AST.

**What this gives you:** a separate process with a wall-clock timeout, a memory
cap, no shell, a scrubbed environment containing only the variables this
connector is supposed to see, and a working directory that is deleted afterwards.
The parent process cannot be hung, OOMed, or polluted by the child.

**What this does not give you:** kernel-level isolation. A determined payload can
still open a socket to somewhere it should not, or read a file the user can read.
For production you run this same runner *inside* the container described in the
plan — non-root, read-only filesystem, egress allowlisted to the target host.
The interface does not change; only the wrapper does.

**What you get on Windows:** less. There is no ``preexec_fn`` and no ``rlimit``,
so the memory and CPU caps do not apply — the wall-clock timeout and the
scrubbed environment are the whole of it. The child still runs in its own
process group, so a timeout takes its descendants with it. Everything else about
the interface is identical, which is the point: the same code path runs
everywhere, and only the strength of the box changes.

Being clear about that boundary matters more than pretending it is airtight.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..agent.spec import SourceSpec

try:  # POSIX only. Windows has no rlimits, and importing this fails there.
    import resource
except ImportError:  # pragma: no cover - exercised on Windows, not in CI
    resource = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MEMORY_MB = 512

#: Variables the child is allowed to inherit. Everything else is stripped, so a
#: generated connector cannot read ANTHROPIC_API_KEY or the app's own database
#: password even if it tries.
_ALLOWED_BASE_ENV = ("PATH", "LANG", "LC_ALL", "PYTHONPATH", "HOME")

#: Windows needs a few more before a child interpreter will even start. Without
#: SYSTEMROOT the socket and SSL layers fail to initialise, which surfaces as an
#: import error from inside the sandbox rather than as a connection failure —
#: an unhelpful way to learn that your environment was too clean.
_ALLOWED_WINDOWS_ENV = (
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "TEMP",
    "TMP",
    "PATHEXT",
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)


def _allowed_base_env() -> tuple[str, ...]:
    """The platform's minimum viable environment for a child interpreter."""
    if IS_WINDOWS:
        return _ALLOWED_BASE_ENV + _ALLOWED_WINDOWS_ENV
    return _ALLOWED_BASE_ENV


#: Executed inside the sandbox. Imports the candidate module, finds the
#: connector class, runs the checks, and prints one JSON line.
_RUNNER = """
import importlib.util, json, sys, traceback

def main() -> int:
    module_path, class_name = sys.argv[1], sys.argv[2]
    out = {"success": False, "stage": "import"}
    try:
        spec = importlib.util.spec_from_file_location("candidate", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        out["stage"] = "resolve"
        connector_cls = getattr(module, class_name)

        out["stage"] = "construct"
        connector = connector_cls.from_env()

        out["stage"] = "connect"
        result = connector.test_connection()
        out["connection"] = json.loads(result.model_dump_json())

        if result.success:
            out["stage"] = "schema"
            tables = connector.fetch_schema()
            out["tables"] = [
                {
                    "schema": t.schema_name,
                    "name": t.table_name,
                    "columns": [
                        {"name": c.name, "type": c.data_type,
                         "nullable": c.nullable, "primary_key": c.primary_key}
                        for c in t.columns
                    ],
                }
                for t in tables
            ]
            out["success"] = True
        else:
            out["error_type"] = (
                getattr(result, "error_type", None) or "ConnectionError"
            )
            # ConnectionTestResult calls this error_message; `error` is kept as a
            # fallback for any result object that names it differently. Reading
            # only `error` silently reported "Connection failed" for every
            # failure, which told neither the user nor the repair loop anything.
            out["error"] = (
                getattr(result, "error_message", None)
                or getattr(result, "error", None)
                or "Connection failed"
            )

        connector.close()
    except Exception as exc:
        out["error_type"] = type(exc).__name__
        out["error"] = str(exc)[:2000]
        out["traceback"] = traceback.format_exc()[-2000:]

    print(json.dumps(out))
    return 0

sys.exit(main())
"""


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of running a connector against its real target."""

    success: bool
    stage: str
    connection: dict | None = None
    tables: list[dict] | None = None
    error_type: str | None = None
    error: str | None = None
    traceback: str | None = None
    duration_ms: float = 0.0
    timed_out: bool = False

    @property
    def table_count(self) -> int:
        return len(self.tables or [])

    def summary(self) -> str:
        if self.timed_out:
            return f"TIMEOUT · exceeded the limit during '{self.stage}'"
        if self.success:
            version = (self.connection or {}).get("server_version") or "unknown"
            latency = (self.connection or {}).get("latency_ms")
            timing = f"{latency:.0f}ms" if latency else "n/a"
            return f"OK · {self.table_count} tables · {timing} · {version[:60]}"
        return f"FAILED at '{self.stage}' · {self.error_type}: {self.error}"


class ConnectionSandbox:
    """Executes a generated connector in an isolated subprocess."""

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        memory_mb: int = DEFAULT_MEMORY_MB,
    ) -> None:
        self._timeout = timeout_seconds
        self._memory_mb = memory_mb

    def run(
        self,
        code: str,
        spec: SourceSpec,
        credentials: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Connect, introspect, and report.

        Args:
            code: Generated connector source.
            spec: The spec it was generated from; supplies the class name and
                the set of environment variables the child may see.
            credentials: Secret values, passed transiently. Never persisted,
                never logged, and dropped when this call returns.

        Returns:
            A :class:`SandboxResult`. Failure is always a result, never an
            exception — the repair loop and the UI both need to read it.
        """
        import time

        started = time.perf_counter()

        # ignore_cleanup_errors: on Windows a file the child still holds open
        # cannot be deleted, and losing a temp directory is not worth failing a
        # connection test over.
        with tempfile.TemporaryDirectory(
            prefix="dsoa-sandbox-", ignore_cleanup_errors=True
        ) as tmpdir:
            module_path = Path(tmpdir) / "candidate.py"
            module_path.write_text(code, encoding="utf-8")
            runner_path = Path(tmpdir) / "_runner.py"
            runner_path.write_text(_RUNNER, encoding="utf-8")

            try:
                completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    [sys.executable, str(runner_path), str(module_path), spec.connector_name],
                    capture_output=True,
                    text=True,
                    # Decode the child explicitly. Without this the parent uses
                    # the locale encoding, which on Windows is cp1252 and turns
                    # any non-ASCII character in a driver's error message into a
                    # UnicodeDecodeError instead of a readable failure.
                    encoding="utf-8",
                    errors="replace",
                    timeout=self._timeout,
                    cwd=tmpdir,
                    env=self._child_env(spec, credentials or {}),
                    **self._isolation_kwargs(),
                )
            except subprocess.TimeoutExpired:
                return SandboxResult(
                    success=False,
                    stage="timeout",
                    error_type="TimeoutError",
                    error=f"Exceeded {self._timeout}s",
                    timed_out=True,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
            except OSError as exc:
                return SandboxResult(
                    success=False,
                    stage="spawn",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    duration_ms=(time.perf_counter() - started) * 1000,
                )

        duration_ms = (time.perf_counter() - started) * 1000
        payload = self._parse(completed.stdout)

        if payload is None:
            return SandboxResult(
                success=False,
                stage="runner",
                error_type="SandboxError",
                # stderr can carry a driver-level message worth showing.
                error=(completed.stderr or "Sandbox produced no output")[-2000:],
                duration_ms=duration_ms,
            )

        return SandboxResult(
            success=bool(payload.get("success")),
            stage=str(payload.get("stage", "unknown")),
            connection=payload.get("connection"),
            tables=payload.get("tables"),
            error_type=payload.get("error_type"),
            error=payload.get("error"),
            traceback=payload.get("traceback"),
            duration_ms=duration_ms,
        )

    # ---- Internals ---------------------------------------------------------

    def _child_env(self, spec: SourceSpec, credentials: dict[str, str]) -> dict[str, str]:
        """Build a minimal environment for the child process.

        Allowlisted, not denylisted. A denylist means every new secret added to
        the parent's environment is exposed until someone remembers to add it —
        which is exactly the kind of thing nobody remembers.
        """
        env = {key: os.environ[key] for key in _allowed_base_env() if key in os.environ}

        prefix = spec.auth.env_prefix
        for key, value in os.environ.items():
            if key.startswith(prefix):
                env[key] = value

        for key, value in credentials.items():
            if not key.startswith(prefix):
                logger.warning("Ignoring credential %r: wrong prefix for this spec", key)
                continue
            env[key] = value

        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        env.setdefault("PYTHONUNBUFFERED", "1")
        return env

    def _isolation_kwargs(self) -> dict[str, object]:
        """Platform-specific arguments that put the child in its own group.

        A new session (POSIX) or process group (Windows) means a timeout kills
        the connector's descendants too, rather than orphaning whatever a driver
        spawned. ``preexec_fn`` does not exist on Windows, so the rlimits go with
        it — there, the wall-clock timeout is the only bound, which is stated in
        the module docstring rather than quietly assumed.
        """
        if IS_WINDOWS:
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {
            "start_new_session": True,
            "preexec_fn": self._apply_limits,  # noqa: PLW1509
        }

    def _apply_limits(self) -> None:  # pragma: no cover - runs in the child
        """Apply resource limits before exec. Called in the forked child."""
        if resource is None:  # pragma: no cover - Windows never gets here
            return

        limit_bytes = self._memory_mb * 1024 * 1024

        def safe_setrlimit(res: int, limits: tuple[int, int]) -> None:
            # AttributeError: not every POSIX platform defines every limit.
            with contextlib.suppress(ValueError, OSError, AttributeError):
                resource.setrlimit(res, limits)

        # RLIMIT_AS on macOS counts reserved address space, not resident memory,
        # so a normal driver import trips it. Skipped there rather than tuned to
        # a number that means nothing.
        if sys.platform != "darwin":
            safe_setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

        safe_setrlimit(resource.RLIMIT_CPU, (self._timeout, self._timeout))
        safe_setrlimit(resource.RLIMIT_NPROC, (64, 64))
        safe_setrlimit(resource.RLIMIT_CORE, (0, 0))

    @staticmethod
    def _parse(stdout: str) -> dict | None:
        """Read the last JSON line the runner printed.

        Last line, not first: a driver may write warnings to stdout before the
        result, and parsing the first line would pick up the noise.
        """
        for line in reversed(stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None
