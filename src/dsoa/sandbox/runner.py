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

Being clear about that boundary matters more than pretending it is airtight.
"""

from __future__ import annotations

import json
import logging
import os
import resource
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..agent.spec import SourceSpec

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MEMORY_MB = 512

#: Variables the child is allowed to inherit. Everything else is stripped, so a
#: generated connector cannot read ANTHROPIC_API_KEY or the app's own database
#: password even if it tries.
_ALLOWED_BASE_ENV = ("PATH", "LANG", "LC_ALL", "PYTHONPATH", "HOME")

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
            out["error_type"] = getattr(result, "error_type", "ConnectionError") or "ConnectionError"
            out["error"] = getattr(result, "error", "Connection failed") or "Connection failed"
            
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

        with tempfile.TemporaryDirectory(prefix="dsoa-sandbox-") as tmpdir:
            module_path = Path(tmpdir) / "candidate.py"
            module_path.write_text(code)
            runner_path = Path(tmpdir) / "_runner.py"
            runner_path.write_text(_RUNNER)

            try:
                completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    [sys.executable, str(runner_path), str(module_path), spec.connector_name],
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    cwd=tmpdir,
                    env=self._child_env(spec, credentials or {}),
                    preexec_fn=self._apply_limits,  # noqa: PLW1509
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
        env = {key: os.environ[key] for key in _ALLOWED_BASE_ENV if key in os.environ}

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

    def _apply_limits(self) -> None:  # pragma: no cover - runs in the child
        """Apply resource limits before exec. Called in the forked child."""
        limit_bytes = self._memory_mb * 1024 * 1024
        
        def safe_setrlimit(res: int, limits: tuple[int, int]) -> None:
            try:
                resource.setrlimit(res, limits)
            except (ValueError, OSError):
                pass
                
        if sys.platform != "darwin":
            safe_setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
            
        safe_setrlimit(resource.RLIMIT_CPU, (self._timeout, self._timeout))
        safe_setrlimit(resource.RLIMIT_NPROC, (64, 64))
        safe_setrlimit(resource.RLIMIT_CORE, (0, 0))
        
        try:
            os.setsid()
        except OSError:
            pass

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
