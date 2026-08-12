#!/usr/bin/env python3
"""Score spec extraction against the golden prompt set.

Run::

    python eval/runner.py                    # live model, needs ANTHROPIC_API_KEY
    python eval/runner.py --category clean   # one slice
    python eval/runner.py --json report.json # machine-readable, for the deck

Four metrics, and the second one is the one to watch:

* **Field accuracy** — of the fields that should be extracted, how many were,
  correctly. The headline number, and the easy one.
* **Hallucination rate** — how often a field that should have stayed null was
  invented instead. This is the metric that separates a usable agent from a
  confident liar, and the reason ``expect_null`` exists in the golden set.
* **Clarification recall** — of the fields that genuinely needed asking about,
  how many the agent actually asked about.
* **Security pass rate** — credentials redacted, injections flagged,
  unsupported sources refused.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dsoa.agent import ScriptedClient, SpecExtractor  # noqa: E402
from dsoa.agent.llm import AnthropicClient, LLMError  # noqa: E402

GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    "\033[92m",
    "\033[91m",
    "\033[93m",
    "\033[2m",
    "\033[1m",
    "\033[0m",
)


@dataclass
class CaseResult:
    case_id: str
    category: str
    fields_expected: int = 0
    fields_correct: int = 0
    nulls_expected: int = 0
    nulls_held: int = 0
    questions_expected: int = 0
    questions_asked: int = 0
    security_checks: int = 0
    security_passed: int = 0
    confidence: float = 0.0
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().lower().rstrip("/")


def evaluate_case(extractor: SpecExtractor, case: dict[str, Any]) -> CaseResult:
    """Run one golden case and score it."""
    result = CaseResult(case_id=case["id"], category=case.get("category", "unknown"))
    prompt = case["prompt"]

    extraction = extractor.extract(prompt)
    draft = extraction.draft
    result.confidence = extraction.confidence

    # 1. Fields that must be extracted correctly.
    for name, expected in (case.get("expect") or {}).items():
        result.fields_expected += 1
        actual = getattr(draft, name, None)
        if _normalize(actual) == _normalize(expected):
            result.fields_correct += 1
        else:
            result.failures.append(f"{name}: expected {expected!r}, got {actual!r}")

    # 2. Fields that must NOT be invented. Weighted heavier in the summary.
    for name in case.get("expect_null") or []:
        result.nulls_expected += 1
        actual = getattr(draft, name, None)
        assumed = name in draft.assumed_fields
        if actual is None or assumed:
            result.nulls_held += 1
        else:
            result.failures.append(f"HALLUCINATED {name}={actual!r} (should be null)")

    # 3. Clarifying questions.
    asked = {q.field for q in extraction.questions}
    for name in case.get("expect_questions") or []:
        result.questions_expected += 1
        if name in asked:
            result.questions_asked += 1
        else:
            result.failures.append(f"did not ask about {name}")

    # 4. Confidence bounds.
    floor = case.get("min_confidence")
    if floor is not None and extraction.confidence < floor:
        result.failures.append(f"confidence {extraction.confidence:.2f} below floor {floor}")
    ceiling = case.get("max_confidence")
    if ceiling is not None and extraction.confidence > ceiling:
        result.failures.append(
            f"confidence {extraction.confidence:.2f} above ceiling {ceiling} "
            "(overconfident on a vague prompt)"
        )

    # 5. Security.
    blob = json.dumps(extraction.model_dump(mode="json"), default=str)
    for secret in case.get("must_not_appear") or []:
        result.security_checks += 1
        if secret.lower() in blob.lower():
            result.failures.append(f"LEAKED {secret!r} into the extraction result")
        else:
            result.security_passed += 1

    if (kind := case.get("expect_finding")) is not None:
        result.security_checks += 1
        kinds = {f.kind.value for f in extraction.security_findings}
        if kind in kinds:
            result.security_passed += 1
        else:
            result.failures.append(f"no {kind} finding raised")

    if case.get("expect_unsupported"):
        result.security_checks += 1
        if extraction.unsupported_request or draft.source_type is None:
            result.security_passed += 1
        else:
            result.failures.append(f"unsupported source mapped onto {draft.source_type}")

    return result


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    def ratio(num: int, den: int) -> float:
        return (num / den * 100) if den else 100.0

    totals = {
        key: sum(getattr(r, key) for r in results)
        for key in (
            "fields_expected",
            "fields_correct",
            "nulls_expected",
            "nulls_held",
            "questions_expected",
            "questions_asked",
            "security_checks",
            "security_passed",
        )
    }

    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = by_category.setdefault(r.category, {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += int(r.passed)

    return {
        "cases_total": len(results),
        "cases_passed": sum(r.passed for r in results),
        "field_accuracy": ratio(totals["fields_correct"], totals["fields_expected"]),
        "hallucination_rate": 100 - ratio(totals["nulls_held"], totals["nulls_expected"]),
        "clarification_recall": ratio(totals["questions_asked"], totals["questions_expected"]),
        "security_pass_rate": ratio(totals["security_passed"], totals["security_checks"]),
        "by_category": by_category,
        "totals": totals,
    }


def print_report(results: list[CaseResult], summary: dict[str, Any]) -> None:
    print(f"\n{BOLD}Spec extraction — golden set{RESET}\n")

    for r in results:
        mark = f"{GREEN}PASS{RESET}" if r.passed else f"{RED}FAIL{RESET}"
        print(f"  {mark}  {r.case_id:<32} {DIM}{r.category:<12} conf={r.confidence:.2f}{RESET}")
        for failure in r.failures:
            colour = RED if failure.startswith(("HALLUCINATED", "LEAKED")) else YELLOW
            print(f"          {colour}{failure}{RESET}")

    print(f"\n{BOLD}Summary{RESET}")
    print(f"  Cases passed          {summary['cases_passed']}/{summary['cases_total']}")
    print(f"  Field accuracy        {summary['field_accuracy']:.1f}%   (target > 90%)")
    print(f"  Hallucination rate    {summary['hallucination_rate']:.1f}%   (target < 5%)")
    print(f"  Clarification recall  {summary['clarification_recall']:.1f}%   (target > 90%)")
    print(f"  Security pass rate    {summary['security_pass_rate']:.1f}%   (target 100%)")

    print(f"\n{BOLD}By category{RESET}")
    for category, counts in sorted(summary["by_category"].items()):
        print(f"  {category:<14} {counts['passed']}/{counts['total']}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(Path(__file__).parent / "golden_prompts.yaml"))
    parser.add_argument("--category", help="Run one category only")
    parser.add_argument("--case", help="Run one case by id")
    parser.add_argument("--json", help="Write the report to this path")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use ScriptedClient — exercises the harness itself, not the model",
    )
    args = parser.parse_args()

    data = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))
    cases = data["cases"]
    if args.category:
        cases = [c for c in cases if c.get("category") == args.category]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]

    if not cases:
        print("No cases matched.", file=sys.stderr)
        return 1

    if args.offline:
        client: Any = ScriptedClient(
            default={"confidence": 0.0, "description": "", "assumed_fields": []}
        )
    else:
        try:
            client = AnthropicClient()
        except LLMError as exc:
            print(f"{RED}{exc}{RESET}\nUse --offline to smoke-test the harness.", file=sys.stderr)
            return 2

    extractor = SpecExtractor(client)
    results = [evaluate_case(extractor, case) for case in cases]
    summary = summarize(results)
    print_report(results, summary)

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "prompt_set_version": data.get("version"),
                    "summary": summary,
                    "cases": [
                        {
                            "id": r.case_id,
                            "category": r.category,
                            "passed": r.passed,
                            "confidence": r.confidence,
                            "failures": r.failures,
                        }
                        for r in results
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{DIM}Report written to {args.json}{RESET}\n")

    return 0 if summary["cases_passed"] == summary["cases_total"] else 1


if __name__ == "__main__":
    sys.exit(main())
