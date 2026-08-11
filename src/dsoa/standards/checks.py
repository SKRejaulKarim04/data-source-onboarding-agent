"""Enterprise coding standards, as executable checks.

This module is the answer to the brief's *"ensure generated connectors follow
predefined enterprise coding standards."* Every bullet in the README's standards
list is a function here, and every one operates on the **AST** — the generated
code is parsed, never imported.

That distinction is the whole safety story of Phase 3. Importing a module runs
its top-level code, so a validator that imports what it is validating has already
executed the thing it was supposed to vet. Execution happens exactly once, in
Phase 4, inside a sandbox. Here we only read.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator

from .models import Finding, Severity

CheckFn = Callable[[ast.Module, str], Iterator[Finding]]

#: Attribute and variable names that must never be assigned a string literal.
_SECRET_NAMES = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "client_secret",
        "private_key",
        "credentials",
    }
)

#: Callables that must not appear anywhere in generated code.
_FORBIDDEN_CALLS = {
    "eval": "arbitrary code execution",
    "exec": "arbitrary code execution",
    "compile": "arbitrary code execution",
    "__import__": "dynamic import bypasses static analysis",
    "system": "shell execution",
    "popen": "shell execution",
    "loads": None,  # only flagged for pickle/marshal, resolved below
}

_REQUIRED_BASE = "SQLBaseConnector"
_ALLOWED_BASES = frozenset({"SQLBaseConnector", "RestBaseConnector", "BaseConnector"})


def _public_functions(tree: ast.Module) -> Iterator[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("__"):
            yield node


def _classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield node


def _connector_classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    """Classes that look like connectors, by base-class name."""
    for cls in _classes(tree):
        base_names = {b.id for b in cls.bases if isinstance(b, ast.Name)}
        base_names |= {b.attr for b in cls.bases if isinstance(b, ast.Attribute)}
        if base_names & _ALLOWED_BASES:
            yield cls


# --- Checks -----------------------------------------------------------------


def check_subclasses_base_connector(tree: ast.Module, source: str) -> Iterator[Finding]:
    """A connector must extend the framework base class."""
    if any(_connector_classes(tree)):
        return
    yield Finding(
        check="subclasses-base-connector",
        severity=Severity.ERROR,
        message=f"No class extends {_REQUIRED_BASE} or another framework base",
        remedy=(
            f"Declare the connector as `class NameConnector({_REQUIRED_BASE}):` and "
            "import it from dsoa.connectors.sql_base"
        ),
    )


def check_class_naming(tree: ast.Module, source: str) -> Iterator[Finding]:
    """Connector classes are PascalCase ending in 'Connector'."""
    for cls in _connector_classes(tree):
        if not (cls.name.endswith("Connector") and cls.name[0].isupper()):
            yield Finding(
                check="class-naming",
                severity=Severity.ERROR,
                message=f"Class {cls.name!r} must be PascalCase ending in 'Connector'",
                line=cls.lineno,
                remedy=f"Rename {cls.name} to something like {cls.name.title()}Connector",
            )


def check_declares_source_type(tree: ast.Module, source: str) -> Iterator[Finding]:
    """The registry and the UI key off ``source_type``, so it must be set."""
    for cls in _connector_classes(tree):
        assigned = {
            target.id
            for node in cls.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            for target in [node.target]
        }
        assigned |= {
            t.id
            for node in cls.body
            if isinstance(node, ast.Assign)
            for t in node.targets
            if isinstance(t, ast.Name)
        }
        if "source_type" not in assigned:
            yield Finding(
                check="declares-source-type",
                severity=Severity.ERROR,
                message=f"{cls.name} does not declare source_type",
                line=cls.lineno,
                remedy='Add `source_type: ClassVar[str] = "postgresql"` (or the correct type)',
            )


def check_no_hardcoded_credentials(tree: ast.Module, source: str) -> Iterator[Finding]:
    """No secret-shaped name may be assigned a non-empty string literal.

    The highest-value check in the file. A generated connector that carries a
    password is not a style problem, it is an incident.
    """

    def _flag(name: str, node: ast.AST, value: ast.AST) -> Finding | None:
        if name.lower().lstrip("_") not in _SECRET_NAMES:
            return None
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            return None
        if not value.value.strip():
            return None
        return Finding(
            check="no-hardcoded-credentials",
            severity=Severity.ERROR,
            message=f"{name!r} is assigned a string literal",
            line=getattr(node, "lineno", None),
            remedy=(
                "Read the value from the environment instead: "
                "os.environ[...] or SqlConnectionConfig.from_env(prefix)"
            ),
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = (
                    target.id
                    if isinstance(target, ast.Name)
                    else target.attr if isinstance(target, ast.Attribute) else None
                )
                if name and (finding := _flag(name, node, node.value)):
                    yield finding
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            name = (
                node.target.id
                if isinstance(node.target, ast.Name)
                else node.target.attr if isinstance(node.target, ast.Attribute) else None
            )
            if name and (finding := _flag(name, node, node.value)):
                yield finding
        elif isinstance(node, ast.Call):
            # password="literal" passed as a keyword argument
            for kw in node.keywords:
                if kw.arg and (finding := _flag(kw.arg, node, kw.value)):
                    yield finding
        elif isinstance(node, ast.Dict):
            # {"password": "literal"}
            for key, value in zip(node.keys, node.values, strict=False):
                is_str_key = isinstance(key, ast.Constant) and isinstance(key.value, str)
                if is_str_key and (finding := _flag(key.value, node, value)):
                    yield finding


def check_no_print(tree: ast.Module, source: str) -> Iterator[Finding]:
    """Structured logging only. ``print`` bypasses log levels and formatting."""
    for node in ast.walk(tree):
        is_print = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        )
        if is_print:
            yield Finding(
                check="no-print",
                severity=Severity.ERROR,
                message="print() is not permitted in connector code",
                line=node.lineno,
                remedy="Use self._logger.info(...) or logging.getLogger(__name__)",
            )


def check_no_bare_except(tree: ast.Module, source: str) -> Iterator[Finding]:
    """Bare and over-broad excepts swallow bugs, including KeyboardInterrupt."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                yield Finding(
                    check="no-bare-except",
                    severity=Severity.ERROR,
                    message="Bare `except:` catches SystemExit and KeyboardInterrupt",
                    line=node.lineno,
                    remedy="Catch a specific exception, e.g. `except SQLAlchemyError as exc:`",
                )
            elif isinstance(node.type, ast.Name) and node.type.id in {
                "Exception",
                "BaseException",
            }:
                yield Finding(
                    check="no-bare-except",
                    severity=Severity.WARNING,
                    message=f"`except {node.type.id}` is very broad",
                    line=node.lineno,
                    remedy="Narrow to the exceptions this block can actually handle",
                )


def check_type_hints(tree: ast.Module, source: str) -> Iterator[Finding]:
    """Public functions carry annotations on parameters and return."""
    for func in _public_functions(tree):
        if func.returns is None:
            yield Finding(
                check="type-hints",
                severity=Severity.ERROR,
                message=f"{func.name}() has no return annotation",
                line=func.lineno,
                remedy=f"Annotate the return type of {func.name}, e.g. `-> dict[str, Any]:`",
            )
        for arg in [*func.args.args, *func.args.kwonlyargs]:
            if arg.arg in {"self", "cls"} or arg.annotation is not None:
                continue
            yield Finding(
                check="type-hints",
                severity=Severity.ERROR,
                message=f"Parameter {arg.arg!r} of {func.name}() is unannotated",
                line=func.lineno,
                remedy=f"Annotate {arg.arg}, e.g. `{arg.arg}: str`",
            )


def check_docstrings(tree: ast.Module, source: str) -> Iterator[Finding]:
    """Module, classes, and public methods are documented."""
    if not ast.get_docstring(tree):
        yield Finding(
            check="docstrings",
            severity=Severity.ERROR,
            message="Module has no docstring",
            line=1,
            remedy="Add a module docstring describing the source and its provenance",
        )
    for cls in _classes(tree):
        if not ast.get_docstring(cls):
            yield Finding(
                check="docstrings",
                severity=Severity.ERROR,
                message=f"Class {cls.name} has no docstring",
                line=cls.lineno,
                remedy=f"Add a docstring to {cls.name}",
            )
    for func in _public_functions(tree):
        if func.name.startswith("_"):
            continue
        if not ast.get_docstring(func):
            yield Finding(
                check="docstrings",
                severity=Severity.ERROR,
                message=f"{func.name}() has no docstring",
                line=func.lineno,
                remedy=f"Add a docstring to {func.name} describing args and returns",
            )


def check_no_dynamic_sql(tree: ast.Module, source: str) -> Iterator[Finding]:
    """SQL must not be built by interpolation.

    Flags f-strings, ``%`` formatting, ``.format()``, and ``+`` concatenation
    passed to ``text()``, ``execute()``, or ``executemany()``.
    """
    sql_sinks = {"text", "execute", "executemany", "read", "scalar"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr if isinstance(node.func, ast.Attribute) else None
        )
        if func_name not in sql_sinks:
            continue

        for arg in node.args[:1]:
            kind = None
            if isinstance(arg, ast.JoinedStr):
                kind = "an f-string"
            elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
                kind = "%-formatting"
            elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
                kind = "string concatenation"
            elif (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "format"
            ):
                kind = ".format()"

            if kind:
                yield Finding(
                    check="no-dynamic-sql",
                    severity=Severity.ERROR,
                    message=f"SQL built with {kind} — injection risk",
                    line=node.lineno,
                    remedy=(
                        "Use bound parameters: text('... WHERE col = :value') with "
                        "params={'value': value}"
                    ),
                )


def check_no_dangerous_calls(tree: ast.Module, source: str) -> Iterator[Finding]:
    """No eval, exec, shell execution, or pickle deserialization."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name) and node.func.id in {
            "eval",
            "exec",
            "compile",
            "__import__",
        }:
            yield Finding(
                check="no-dangerous-calls",
                severity=Severity.ERROR,
                message=f"{node.func.id}() is not permitted in generated code",
                line=node.lineno,
                remedy=f"Remove the {node.func.id}() call",
            )

        if isinstance(node.func, ast.Attribute):
            owner = node.func.value
            owner_name = owner.id if isinstance(owner, ast.Name) else None
            attr = node.func.attr
            if (owner_name, attr) in {
                ("os", "system"),
                ("os", "popen"),
                ("subprocess", "call"),
                ("subprocess", "run"),
                ("subprocess", "Popen"),
                ("pickle", "loads"),
                ("pickle", "load"),
                ("marshal", "loads"),
            }:
                yield Finding(
                    check="no-dangerous-calls",
                    severity=Severity.ERROR,
                    message=f"{owner_name}.{attr}() is not permitted in generated code",
                    line=node.lineno,
                    remedy=f"Remove the {owner_name}.{attr}() call",
                )


def check_no_wildcard_imports(tree: ast.Module, source: str) -> Iterator[Finding]:
    """``from x import *`` defeats static analysis of what is in scope."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            yield Finding(
                check="no-wildcard-imports",
                severity=Severity.ERROR,
                message=f"Wildcard import from {node.module}",
                line=node.lineno,
                remedy="Import the specific names the module uses",
            )


def check_env_for_secrets(tree: ast.Module, source: str) -> Iterator[Finding]:
    """Credentials must be sourced from the environment.

    Paired with :func:`check_no_hardcoded_credentials`: that one proves secrets
    are absent, this one proves there is a supported way to supply them.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            return
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name in {"from_env", "getenv"}:
                return
    yield Finding(
        check="env-for-secrets",
        severity=Severity.ERROR,
        message="No environment lookup found; credentials have no supported source",
        remedy="Build the config with SqlConnectionConfig.from_env(prefix)",
    )


def check_no_todo_markers(tree: ast.Module, source: str) -> Iterator[Finding]:
    """A generated artifact should not ship with unfinished markers."""
    for number, line in enumerate(source.splitlines(), start=1):
        upper = line.upper()
        for marker in ("TODO", "FIXME", "XXX", "NOT IMPLEMENTED", "PLACEHOLDER"):
            if marker in upper:
                yield Finding(
                    check="no-todo-markers",
                    severity=Severity.WARNING,
                    message=f"{marker} marker left in generated code",
                    line=number,
                    remedy=f"Complete or remove the {marker}",
                )
                break


#: Every check, in the order the report lists them.
ALL_CHECKS: tuple[tuple[str, CheckFn], ...] = (
    ("subclasses-base-connector", check_subclasses_base_connector),
    ("class-naming", check_class_naming),
    ("declares-source-type", check_declares_source_type),
    ("no-hardcoded-credentials", check_no_hardcoded_credentials),
    ("env-for-secrets", check_env_for_secrets),
    ("no-dynamic-sql", check_no_dynamic_sql),
    ("no-dangerous-calls", check_no_dangerous_calls),
    ("no-print", check_no_print),
    ("no-bare-except", check_no_bare_except),
    ("no-wildcard-imports", check_no_wildcard_imports),
    ("type-hints", check_type_hints),
    ("docstrings", check_docstrings),
    ("no-todo-markers", check_no_todo_markers),
)


def run_checks(source: str) -> tuple[list[Finding], int, int]:
    """Run every standards check against ``source``.

    Args:
        source: Python source text. Never imported, only parsed.

    Returns:
        ``(findings, checks_run, checks_passed)``.

    Raises:
        SyntaxError: if the source does not parse. Callers handle this as its
            own kind of failure — there is nothing to check in code that will
            not compile.
    """
    tree = ast.parse(source)
    findings: list[Finding] = []
    passed = 0

    for _name, check in ALL_CHECKS:
        results = list(check(tree, source))
        findings.extend(results)
        if not any(f.severity is Severity.ERROR for f in results):
            passed += 1

    return findings, len(ALL_CHECKS), passed
