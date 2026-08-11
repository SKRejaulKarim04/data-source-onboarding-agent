"""Static validator and repair loop tests."""

from __future__ import annotations

from typing import Any

import pytest

from dsoa.agent.llm import LLMError, ScriptedClient
from dsoa.standards import Severity
from dsoa.validation import StaticValidator
from dsoa.validation.repair import RepairLoop, strip_code_fences

from .test_standards import GOOD


class ExplodingClient:
    def complete_json(self, **_: Any) -> dict[str, Any]:
        raise LLMError("provider down")


class EchoClient:
    """Returns the input unchanged — simulates a model that gives up."""

    def __init__(self, code: str) -> None:
        self._code = code

    def complete_json(self, **_: Any) -> dict[str, Any]:
        return {"code": self._code}


BROKEN = GOOD.replace(
    '        prefix = os.environ.get("DSOA_SALES_PREFIX", "")',
    '        print("loading")\n        password = "hunter2"',
)


# ---- Static validator ------------------------------------------------------


def test_conforming_code_passes() -> None:
    report = StaticValidator().validate(GOOD)

    assert report.passed
    assert report.syntax_ok
    assert report.conformance_pct == 100.0


def test_broken_code_fails_with_specific_findings() -> None:
    report = StaticValidator().validate(BROKEN)

    assert not report.passed
    checks = {f.check for f in report.errors}
    assert "no-print" in checks
    assert "no-hardcoded-credentials" in checks


def test_syntax_error_short_circuits_everything() -> None:
    """No point running twelve checks on code that will not compile."""
    report = StaticValidator().validate("def broken(:\n    pass")

    assert not report.syntax_ok
    assert not report.passed
    assert len(report.findings) == 1
    assert report.findings[0].check == "syntax"


def test_warnings_alone_do_not_block() -> None:
    with_todo = GOOD.replace(
        '"""A conforming connector module."""', '"""A module. TODO: revisit."""'
    )
    report = StaticValidator().validate(with_todo)

    assert report.passed
    assert report.warnings


def test_missing_tools_are_recorded_not_fatal() -> None:
    """A grader without bandit installed still gets a working demo."""
    report = StaticValidator(run_ruff=False, run_black=False, run_bandit=False).validate(GOOD)

    assert report.passed
    assert report.tools_run == ("ast",)


def test_external_tools_run_when_available() -> None:
    report = StaticValidator().validate(GOOD)
    assert "ruff" in report.tools_run or "ruff" in report.tools_skipped


def test_ruff_findings_are_warnings_not_errors() -> None:
    """Lint style must not send the repair loop chasing whitespace."""
    unsorted = GOOD.replace("import os\n", "import sys\nimport os\n")
    report = StaticValidator().validate(unsorted)

    ruff_findings = [f for f in report.findings if f.tool == "ruff"]
    if ruff_findings:
        assert all(f.severity is Severity.WARNING for f in ruff_findings)


def test_validation_never_imports_the_candidate() -> None:
    """Importing would execute top-level code — that is Phase 4's job, sandboxed."""
    import sys

    hostile = GOOD.replace(
        '"""A conforming connector module."""',
        '"""A module."""\n\nimport sys\nsys.modules["__evidence__"] = "executed"',
    )
    StaticValidator().validate(hostile)

    assert "__evidence__" not in sys.modules


def test_repair_brief_lists_only_errors() -> None:
    report = StaticValidator().validate(BROKEN)
    brief = report.repair_brief()

    assert "no-print" in brief
    assert "Fix:" in brief
    for warning in report.warnings:
        assert warning.check not in brief


# ---- Repair loop -----------------------------------------------------------


def test_passing_code_needs_no_repair() -> None:
    outcome = RepairLoop(ScriptedClient()).run(GOOD)

    assert outcome.iterations == 0
    assert outcome.code == GOOD
    assert outcome.report.passed


def test_successful_repair_is_accepted() -> None:
    outcome = RepairLoop(ScriptedClient([{"code": GOOD}])).run(BROKEN)

    assert outcome.repaired
    assert outcome.report.passed
    assert outcome.code.strip() == GOOD.strip()
    assert outcome.attempts[0].improved


def test_regression_is_rejected_and_the_previous_candidate_kept() -> None:
    """The guard that stops the loop oscillating."""
    worse = BROKEN.replace(
        '        print("loading")', '        print("a")\n        print("b")\n        eval("x")'
    )
    outcome = RepairLoop(ScriptedClient([{"code": worse}])).run(BROKEN)

    assert not outcome.repaired
    assert outcome.code == BROKEN  # original kept, not the worse candidate
    assert not outcome.attempts[0].accepted
    assert "did not reduce" in outcome.attempts[0].note


def test_partial_improvement_is_accepted_and_the_loop_continues() -> None:
    half_fixed = BROKEN.replace('        password = "hunter2"', "")
    outcome = RepairLoop(ScriptedClient([{"code": half_fixed}, {"code": GOOD}])).run(BROKEN)

    assert outcome.report.passed
    assert outcome.iterations == 2
    assert all(a.accepted for a in outcome.attempts)


def test_loop_respects_the_iteration_cap() -> None:
    stuck = ScriptedClient([{"code": BROKEN.replace('print("loading")', 'print("x")')}] * 10)
    outcome = RepairLoop(stuck, max_iterations=2).run(BROKEN)

    assert outcome.iterations <= 2
    assert not outcome.report.passed


def test_no_change_from_the_model_stops_the_loop() -> None:
    outcome = RepairLoop(EchoClient(BROKEN)).run(BROKEN)

    assert outcome.iterations == 1
    assert "no change" in outcome.attempts[0].note.lower()


def test_provider_failure_returns_the_original_code() -> None:
    outcome = RepairLoop(ExplodingClient()).run(BROKEN)

    assert outcome.code == BROKEN
    assert "Model call failed" in outcome.attempts[0].note


def test_repair_never_returns_worse_code_than_it_received() -> None:
    """The loop's contract, stated as a test."""
    before = len(StaticValidator().validate(BROKEN).errors)
    worse = BROKEN + '\n\nAPI_KEY = "sk-live-leak"\n'
    outcome = RepairLoop(ScriptedClient([{"code": worse}])).run(BROKEN)

    assert len(outcome.report.errors) <= before


@pytest.mark.parametrize(
    "wrapped",
    ["```python\nx = 1\n```", "```\nx = 1\n```", "x = 1", "x = 1\n\n"],
)
def test_code_fences_are_stripped(wrapped: str) -> None:
    """Output always ends in exactly one newline — see strip_code_fences."""
    assert strip_code_fences(wrapped) == "x = 1\n"


def test_whitespace_only_difference_is_not_treated_as_a_repair() -> None:
    outcome = RepairLoop(EchoClient(BROKEN + "\n\n\n")).run(BROKEN)

    assert "no change" in outcome.attempts[0].note.lower()
