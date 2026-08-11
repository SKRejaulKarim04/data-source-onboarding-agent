"""Static validation.

Order matters:

1. **Parse.** If it does not compile there is nothing else worth saying, so this
   short-circuits.
2. **Standards checks.** The AST checks in :mod:`dsoa.standards.checks` — the
   enterprise rules the brief asks for.
3. **External tools.** ruff, black, bandit. Each runs in a subprocess against a
   temp file and each is optional: a missing tool is recorded in
   ``tools_skipped`` rather than crashing the pipeline, so a grader who did not
   install bandit still gets a working demo.

Nothing here imports or executes the generated module. That happens once, in the
Phase 4 sandbox, and nowhere else.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..standards.checks import run_checks
from ..standards.models import Finding, Severity, ValidationReport

logger = logging.getLogger(__name__)

#: Generous enough for a cold ruff start, short enough that a hung tool does not
#: hold a web request open.
TOOL_TIMEOUT_SECONDS = 30


class StaticValidator:
    """Validates candidate connector source without executing it."""

    def __init__(
        self,
        *,
        run_ruff: bool = True,
        run_black: bool = True,
        run_bandit: bool = True,
        line_length: int = 100,
    ) -> None:
        self._run_ruff = run_ruff
        self._run_black = run_black
        self._run_bandit = run_bandit
        self._line_length = line_length

    def validate(self, source: str) -> ValidationReport:
        """Validate ``source`` and return a structured report."""
        findings: list[Finding] = []

        try:
            standards_findings, checks_run, checks_passed = run_checks(source)
        except SyntaxError as exc:
            return ValidationReport(
                syntax_ok=False,
                checks_run=1,
                checks_passed=0,
                findings=(
                    Finding(
                        check="syntax",
                        severity=Severity.ERROR,
                        message=f"{exc.msg}",
                        line=exc.lineno,
                        tool="ast",
                        remedy="Fix the syntax error; no other checks can run until it parses",
                    ),
                ),
            )

        findings.extend(standards_findings)

        tools_run: list[str] = ["ast"]
        tools_skipped: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "candidate.py"
            path.write_text(source)

            for enabled, name, runner in (
                (self._run_ruff, "ruff", self._ruff),
                (self._run_black, "black", self._black),
                (self._run_bandit, "bandit", self._bandit),
            ):
                if not enabled:
                    continue
                executable = shutil.which(name)
                if executable is None:
                    tools_skipped.append(name)
                    logger.info("%s not installed; skipping", name)
                    continue
                try:
                    # Pass the absolute path which() resolved rather than the
                    # bare name: it is one fewer PATH lookup, and it means the
                    # tool that gets checked is provably the one that was found.
                    findings.extend(runner(executable, path))
                    tools_run.append(name)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    tools_skipped.append(name)
                    logger.warning("%s failed to run: %s", name, exc)

        return ValidationReport(
            findings=tuple(findings),
            checks_run=checks_run,
            checks_passed=checks_passed,
            tools_run=tuple(tools_run),
            tools_skipped=tuple(tools_skipped),
            syntax_ok=True,
        )

    # ---- External tools ----------------------------------------------------

    def _ruff(self, executable: str, path: Path) -> list[Finding]:
        result = subprocess.run(  # noqa: S603 - absolute path, fixed argv, no shell
            [
                executable,
                "check",
                "--output-format",
                "json",
                "--line-length",
                str(self._line_length),
                "--isolated",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        if not result.stdout.strip():
            return []
        try:
            entries = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return [
            Finding(
                check=f"ruff:{entry.get('code') or 'unknown'}",
                # Lint style is advisory; the AST checks carry the blocking rules.
                # Promoting every ruff nit to an error would send the repair loop
                # chasing whitespace instead of fixing what matters.
                severity=Severity.WARNING,
                message=entry.get("message", ""),
                line=(entry.get("location") or {}).get("row"),
                tool="ruff",
                remedy=(entry.get("fix") or {}).get("message") if entry.get("fix") else None,
            )
            for entry in entries
        ]

    def _black(self, executable: str, path: Path) -> list[Finding]:
        result = subprocess.run(  # noqa: S603
            [
                executable,
                "--check",
                "--quiet",
                "--line-length",
                str(self._line_length),
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            return []
        return [
            Finding(
                check="black:format",
                severity=Severity.WARNING,
                message="Source is not black-formatted",
                tool="black",
                remedy="Run black on the generated file, or fix the template's spacing",
            )
        ]

    def _bandit(self, executable: str, path: Path) -> list[Finding]:
        result = subprocess.run(  # noqa: S603
            [executable, "-f", "json", "-q", str(path)],
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        if not result.stdout.strip():
            return []
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        severity_map = {
            "HIGH": Severity.ERROR,
            "MEDIUM": Severity.ERROR,
            "LOW": Severity.WARNING,
        }
        return [
            Finding(
                check=f"bandit:{item.get('test_id', '?')}",
                severity=severity_map.get(item.get("issue_severity", "LOW"), Severity.WARNING),
                message=item.get("issue_text", ""),
                line=item.get("line_number"),
                tool="bandit",
                remedy=item.get("more_info"),
            )
            for item in payload.get("results", [])
        ]
