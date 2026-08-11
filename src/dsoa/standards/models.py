"""Result types for validation.

One vocabulary for AST checks, ruff, black, and bandit alike, so the UI renders
a single findings table and the repair loop reads a single format regardless of
which tool objected.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """How much a finding matters."""

    ERROR = "error"  # blocks the artifact
    WARNING = "warning"  # surfaced for review, does not block
    INFO = "info"

    @property
    def blocking(self) -> bool:
        return self is Severity.ERROR


class Finding(BaseModel):
    """One problem with a piece of generated code."""

    model_config = ConfigDict(frozen=True)

    check: str = Field(description="Stable check identifier, e.g. 'no-hardcoded-credentials'")
    severity: Severity
    message: str
    line: int | None = None
    tool: str = "standards"
    remedy: str | None = Field(
        default=None,
        description="What to change. Fed to the repair loop, so it must be actionable.",
    )

    def __str__(self) -> str:
        where = f":{self.line}" if self.line else ""
        return f"[{self.severity}] {self.check}{where} — {self.message}"


class ValidationReport(BaseModel):
    """Everything known about one candidate connector."""

    model_config = ConfigDict(frozen=True)

    findings: tuple[Finding, ...] = ()
    checks_run: int = 0
    checks_passed: int = 0
    tools_run: tuple[str, ...] = ()
    tools_skipped: tuple[str, ...] = ()
    syntax_ok: bool = True

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)

    @property
    def passed(self) -> bool:
        """No blocking findings. Warnings are allowed through."""
        return self.syntax_ok and not self.errors

    @property
    def conformance_pct(self) -> float:
        if not self.checks_run:
            return 100.0
        return self.checks_passed / self.checks_run * 100

    def summary(self) -> str:
        if not self.syntax_ok:
            return "FAILED · does not parse"
        verdict = "PASSED" if self.passed else "FAILED"
        return (
            f"{verdict} · {self.checks_passed}/{self.checks_run} checks · "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )

    def repair_brief(self) -> str:
        """Findings rendered for the repair prompt.

        Errors only: asking a model to fix warnings alongside errors reliably
        produces churn on the warnings and no progress on the errors.
        """
        lines = []
        for finding in self.errors:
            location = f" (line {finding.line})" if finding.line else ""
            remedy = f" Fix: {finding.remedy}" if finding.remedy else ""
            lines.append(f"- {finding.check}{location}: {finding.message}.{remedy}")
        return "\n".join(lines)
