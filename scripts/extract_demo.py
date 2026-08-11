#!/usr/bin/env python3
"""Walk a request through extraction, clarification, and finalization.

    python scripts/extract_demo.py "Onboard our Postgres DB at db.internal, database analytics"
    python scripts/extract_demo.py --offline          # canned responses, no API key

With no API key set it uses ``ScriptedClient``, which makes this safe to run in
a presentation where the wifi may not cooperate.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dsoa.agent import ScriptedClient, SpecExtractor, apply_answers  # noqa: E402
from dsoa.agent.llm import AnthropicClient, LLMError  # noqa: E402
from dsoa.logging_config import configure_logging  # noqa: E402

GREEN, RED, YELLOW, CYAN, DIM, BOLD, RESET = (
    "\033[92m",
    "\033[91m",
    "\033[93m",
    "\033[96m",
    "\033[2m",
    "\033[1m",
    "\033[0m",
)

OFFLINE_SCRIPT = {
    "reporting": {
        "source_type": "postgresql",
        "connector_name": "ReportingAnalyticsConnector",
        "host": "reporting-db.internal",
        "database": "analytics",
        "auth_method": "username_password",
        "read_only": True,
        "description": "Read-only Postgres reporting database",
        "confidence": 0.93,
        "assumed_fields": [],
    },
    "billing": {
        "source_type": "rest_api",
        "connector_name": "VendorBillingConnector",
        "description": "Vendor billing API",
        "confidence": 0.42,
        "assumed_fields": [],
        "notes": ["Base URL and authentication method were not stated"],
    },
}
OFFLINE_DEFAULT = {
    "description": "Unrecognised request",
    "confidence": 0.2,
    "assumed_fields": [],
}


def _rule(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}\n{DIM}{'─' * 62}{RESET}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", default="Onboard the vendor billing API.")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    configure_logging("WARNING")

    if args.offline or not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"{DIM}(offline mode — scripted responses){RESET}")
        client = ScriptedClient(OFFLINE_SCRIPT, default=OFFLINE_DEFAULT)
    else:
        try:
            client = AnthropicClient()
        except LLMError as exc:
            print(f"{RED}{exc}{RESET}")
            return 2

    extractor = SpecExtractor(client)

    _rule("1. Request")
    print(f"  {args.prompt}")

    result = extractor.extract(args.prompt)

    if result.security_findings:
        _rule("2. Security")
        for finding in result.security_findings:
            print(f"  {YELLOW}{finding.kind}{RESET}  {finding.label} — {finding.detail}")

    _rule("3. Extracted")
    print(f"  {result.summary()}")
    print(f"  {DIM}confidence {result.confidence:.2f}{RESET}")
    for note in result.notes:
        print(f"  {DIM}note: {note}{RESET}")

    if result.needs_clarification:
        _rule("4. Clarification needed")
        answers: dict[str, str] = {}
        for question in result.questions:
            print(f"\n  {CYAN}{question.question}{RESET}")
            print(f"  {DIM}{question.why}{RESET}")
            if question.options:
                print(f"  {DIM}options: {', '.join(question.options)}{RESET}")
            if question.example:
                print(f"  {DIM}example: {question.example}{RESET}")
            try:
                answer = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  (skipped)")
                answer = ""
            if answer:
                answers[question.field] = answer

        if answers:
            result = extractor.refine(apply_answers(result.draft, {}), answers)
            _rule("5. After clarification")
            print(f"  {result.summary()}")

    _rule("Final")
    if result.ready_to_generate:
        spec = result.finalize()
        print(f"  {GREEN}Ready to generate.{RESET}")
        print(f"  class        {spec.connector_name}")
        print(f"  module       {spec.module_name}")
        print(f"  template key {spec.template_key}")
        print(f"  reads env    {', '.join(spec.auth.secret_env_vars) or '(none)'}")
        return 0

    missing = ", ".join(result.draft.missing_required())
    print(
        f"  {YELLOW}Not ready.{RESET} Still missing: {missing or 'nothing — but confidence is low'}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
