#!/usr/bin/env python3
"""Show the full pipeline: request -> spec -> code -> validation.

    python scripts/generate_demo.py                        # postgres
    python scripts/generate_demo.py --source-type mysql
    python scripts/generate_demo.py --break-it             # fault injection
    python scripts/generate_demo.py --write out/           # save the artifact

``--break-it`` is the interesting flag. It corrupts the rendered code the way a
careless template edit would and shows the validator catching each fault by name.
A validator that has only ever been shown passing code has demonstrated nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dsoa.agent.spec import AuthMethod, SourceType, SpecDraft  # noqa: E402
from dsoa.generation import ConnectorGenerator  # noqa: E402
from dsoa.logging_config import configure_logging  # noqa: E402
from dsoa.standards.checks import ALL_CHECKS  # noqa: E402
from dsoa.standards.models import ValidationReport  # noqa: E402
from dsoa.validation import StaticValidator  # noqa: E402

GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    "\033[92m",
    "\033[91m",
    "\033[93m",
    "\033[2m",
    "\033[1m",
    "\033[0m",
)

FIXED_TIME = "2026-08-07T00:00:00Z"

#: Each entry corrupts the generated code the way a bad template edit would.
FAULTS: list[tuple[str, str, str]] = [
    (
        "hardcoded credential",
        "    env_prefix: ClassVar[str] =",
        '    password = "hunter2"\n    env_prefix: ClassVar[str] =',
    ),
    (
        "print statement",
        "    value = os.environ.get(",
        '    print("looking up env")\n    value = os.environ.get(',
    ),
    (
        "dangerous call",
        "    return value if value else fallback",
        '    eval("1 + 1")\n    return value if value else fallback',
    ),
    (
        "dynamic SQL",
        "        return cls(config)",
        '        cls().read(f"SELECT * FROM t WHERE x = {prefix}")\n        return cls(config)',
    ),
    (
        "bare except",
        "        resolved_prefix = prefix or cls.env_prefix",
        "        try:\n            pass\n        except:\n            pass\n"
        "        resolved_prefix = prefix or cls.env_prefix",
    ),
]


def _rule(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}\n{DIM}{'─' * 66}{RESET}")


def show_checklist(report: ValidationReport) -> None:
    """The standards table — the most convincing screen in the whole project."""
    failed = {f.check for f in report.errors}
    for name, _ in ALL_CHECKS:
        mark = f"{RED}FAIL{RESET}" if name in failed else f"{GREEN}PASS{RESET}"
        print(f"  {mark}  {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-type", default="postgresql", choices=[t.value for t in SourceType if t.is_sql]
    )
    parser.add_argument("--name", default="ReportingConnector")
    parser.add_argument("--host", default="reporting-db.internal")
    parser.add_argument("--database", default="analytics")
    parser.add_argument(
        "--break-it", action="store_true", help="Inject faults and show the validator catching them"
    )
    parser.add_argument("--write", help="Directory to write the artifact into")
    parser.add_argument("--show-code", action="store_true")
    args = parser.parse_args()

    configure_logging("WARNING")

    spec = SpecDraft(
        source_type=SourceType(args.source_type),
        connector_name=args.name,
        host=args.host,
        database=args.database,
        auth_method=AuthMethod.USERNAME_PASSWORD,
    ).finalize()

    _rule("1. Spec")
    print(f"  source type   {spec.source_type.value}")
    print(f"  class         {spec.connector_name}")
    print(
        f"  target        {spec.sql_target.host}:{spec.sql_target.port}/{spec.sql_target.database}"
    )
    print(f"  template key  {spec.template_key}")
    print(f"  reads env     {', '.join(spec.auth.secret_env_vars)}")

    result = ConnectorGenerator().generate(spec, generated_at=FIXED_TIME)

    _rule("2. Generated")
    print(f"  module        {result.module_name}")
    print(f"  template      {result.template_key} v{result.template_version}")
    print(f"  spec sha      {result.spec_checksum}")
    print(f"  code sha      {result.code_checksum}")
    print(f"  lines         {len(result.code.splitlines())}")

    _rule("3. Standards")
    show_checklist(result.report)
    print(f"\n  {result.report.summary()}")
    if result.report.tools_run:
        print(f"  {DIM}tools: {', '.join(result.report.tools_run)}{RESET}")
    if result.report.tools_skipped:
        print(f"  {DIM}skipped (not installed): {', '.join(result.report.tools_skipped)}{RESET}")

    if args.break_it:
        _rule("4. Fault injection")
        print(f"  {DIM}Corrupting the generated code and re-validating.{RESET}\n")
        validator = StaticValidator()
        for label, needle, replacement in FAULTS:
            if needle not in result.code:
                print(f"  {YELLOW}SKIP{RESET}  {label} {DIM}(anchor not present){RESET}")
                continue
            broken = result.code.replace(needle, replacement, 1)
            report = validator.validate(broken)
            caught = {f.check for f in report.errors}
            if report.passed:
                print(f"  {RED}MISSED{RESET}  {label} — validator did not object")
            else:
                print(f"  {GREEN}CAUGHT{RESET}  {label} {DIM}-> {', '.join(sorted(caught))}{RESET}")

    if args.show_code:
        _rule("Generated code")
        print(result.code)

    if args.write:
        out = Path(args.write)
        out.mkdir(parents=True, exist_ok=True)
        path = out / result.module_name
        path.write_text(result.code, encoding="utf-8")
        print(f"\n  {DIM}written to {path}{RESET}")

    _rule("Verdict")
    if result.accepted:
        print(f"  {GREEN}{result.summary()}{RESET}")
        print(f"  {DIM}artifact version {result.semver}{RESET}\n")
        return 0

    print(f"  {RED}{result.summary()}{RESET}")
    for finding in result.report.errors:
        print(f"    {finding}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
