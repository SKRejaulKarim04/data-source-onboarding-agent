"""The repair loop.

A fair question: if templates are deterministic and validated output is clean,
what is there to repair?

Three real cases:

1. **Custom blocks.** When a request asks for something the template does not
   cover — a bespoke incremental-read method, a vendor-specific retry rule — the
   model writes that fragment, and model-written code needs checking.
2. **Template regressions.** A template edit that breaks conformance should be
   caught and, where possible, corrected rather than just reported.
3. **Imported connectors.** Phase 6 stretch goal: pull an existing hand-written
   connector into the framework and bring it up to standard.

The loop's design rule is that it must never make things worse. Each iteration
is accepted only if it strictly reduces the error count; otherwise the previous
candidate is kept and the loop stops. Without that guard a model that
"fixes" one error while introducing two will happily oscillate until it hits the
iteration cap, and the artifact you ship is whichever attempt happened to be
last — which is not a property you want in a code generator.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ..agent.llm import LLMClient, LLMError
from ..standards.models import ValidationReport
from .static import StaticValidator

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3

REPAIR_SYSTEM_PROMPT = """\
You repair Python data-source connector code so that it satisfies a fixed set of \
enterprise coding standards.

Rules:

1. Return the complete corrected module. Not a diff, not a fragment, not an \
explanation — the full file.
2. Change only what is needed to clear the reported findings. Do not rename \
things, restructure the class, or "improve" code that was not flagged.
3. Never introduce a credential, a literal password, an API key, or any other \
secret. Credentials come from environment variables.
4. Never add eval, exec, subprocess, os.system, or pickle deserialization.
5. Preserve the module docstring's provenance block (template, spec, generated) \
exactly as it is.
6. Keep the connector's class name and its base class unchanged.
"""

_FENCE = re.compile(r"^\s*```(?:python)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


@dataclass
class RepairAttempt:
    """One pass through the loop."""

    iteration: int
    errors_before: int
    errors_after: int
    accepted: bool
    note: str = ""

    @property
    def improved(self) -> bool:
        return self.errors_after < self.errors_before


@dataclass
class RepairOutcome:
    """Final state after the loop finishes."""

    code: str
    report: ValidationReport
    attempts: list[RepairAttempt] = field(default_factory=list)

    @property
    def iterations(self) -> int:
        return len(self.attempts)

    @property
    def repaired(self) -> bool:
        return any(a.accepted for a in self.attempts)

    def summary(self) -> str:
        if not self.attempts:
            return "No repair needed"
        accepted = sum(a.accepted for a in self.attempts)
        return f"{accepted}/{len(self.attempts)} repair iteration(s) accepted"


def strip_code_fences(text: str) -> str:
    """Remove markdown fences a model may have wrapped the code in.

    Always returns text ending in exactly one newline. That is not cosmetic:
    without it, a model returning byte-identical code minus the trailing newline
    reads as a change, the loop accepts a no-op iteration, and black flags the
    result. Normalizing here keeps the comparison in :meth:`RepairLoop.run`
    honest.
    """
    match = _FENCE.match(text)
    body = (match.group(1) if match else text).strip()
    return f"{body}\n" if body else ""


class RepairLoop:
    """Iteratively asks the model to fix blocking findings."""

    def __init__(
        self,
        client: LLMClient,
        validator: StaticValidator | None = None,
        *,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self._client = client
        self._validator = validator or StaticValidator()
        self._max_iterations = max_iterations

    def run(self, code: str, report: ValidationReport | None = None) -> RepairOutcome:
        """Repair ``code`` until it passes or the loop gives up.

        Args:
            code: Candidate connector source.
            report: A validation report if one has already been produced;
                recomputed when omitted.

        Returns:
            The best candidate seen, which is never worse than the input.
        """
        current_code = code
        current_report = report or self._validator.validate(code)
        attempts: list[RepairAttempt] = []

        for iteration in range(1, self._max_iterations + 1):
            if current_report.passed:
                break

            errors_before = len(current_report.errors) + (0 if current_report.syntax_ok else 1)
            logger.info(
                "Repair iteration %d/%d: %d blocking finding(s)",
                iteration,
                self._max_iterations,
                errors_before,
            )

            try:
                candidate = self._request_fix(current_code, current_report)
            except LLMError as exc:
                attempts.append(
                    RepairAttempt(
                        iteration=iteration,
                        errors_before=errors_before,
                        errors_after=errors_before,
                        accepted=False,
                        note=f"Model call failed: {exc}",
                    )
                )
                break

            # Compare on stripped text: whitespace-only differences are not a
            # repair, and treating them as one burns an iteration.
            if not candidate or candidate.strip() == current_code.strip():
                attempts.append(
                    RepairAttempt(
                        iteration=iteration,
                        errors_before=errors_before,
                        errors_after=errors_before,
                        accepted=False,
                        note="Model returned no change",
                    )
                )
                break

            candidate_report = self._validator.validate(candidate)
            errors_after = len(candidate_report.errors) + (0 if candidate_report.syntax_ok else 1)

            # The regression guard. Strictly fewer errors, or the candidate is
            # discarded and the loop stops.
            accepted = errors_after < errors_before
            attempts.append(
                RepairAttempt(
                    iteration=iteration,
                    errors_before=errors_before,
                    errors_after=errors_after,
                    accepted=accepted,
                    note=(
                        ""
                        if accepted
                        else "Rejected: did not reduce the error count, keeping previous candidate"
                    ),
                )
            )

            if not accepted:
                logger.warning(
                    "Repair iteration %d rejected (%d -> %d errors)",
                    iteration,
                    errors_before,
                    errors_after,
                )
                break

            current_code = candidate
            current_report = candidate_report

        return RepairOutcome(code=current_code, report=current_report, attempts=attempts)

    def _request_fix(self, code: str, report: ValidationReport) -> str:
        user = (
            "The following connector module failed validation.\n\n"
            "Findings to fix:\n"
            f"{report.repair_brief()}\n\n"
            "Current module:\n"
            "```python\n"
            f"{code}\n"
            "```\n\n"
            "Return the complete corrected module."
        )
        payload = self._client.complete_json(
            system=REPAIR_SYSTEM_PROMPT,
            user=user,
            schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The complete corrected Python module.",
                    },
                    "changes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "One line per change made.",
                    },
                },
                "required": ["code", "changes"],
            },
            tool_name="emit_repaired_module",
        )
        return strip_code_fences(payload["code"])

def repair_sandbox_error(client: LLMClient, code: str, error_type: str, error_msg: str, traceback_str: str) -> str | None:
    """Ask the model to fix a runtime sandbox error."""
    user = (
        "The following connector module failed during a live connection test.\n\n"
        "Runtime Error:\n"
        f"{error_type}: {error_msg}\n\n"
        "Traceback:\n"
        f"{traceback_str}\n\n"
        "Current module:\n"
        "```python\n"
        f"{code}\n"
        "```\n\n"
        "Return the complete corrected module. Do not introduce hardcoded credentials."
    )
    try:
        payload = client.complete_json(
            system=REPAIR_SYSTEM_PROMPT,
            user=user,
            schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The complete corrected Python module.",
                    },
                    "changes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "One line per change made.",
                    },
                },
                "required": ["code", "changes"],
            },
        )
        return strip_code_fences(payload["code"])
    except Exception as exc:
        logger.warning("Sandbox repair failed: %s", exc)
        return None
