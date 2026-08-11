"""The clarification loop.

When a draft is incomplete the agent asks rather than guesses. The questions
themselves are **templated, not generated** — one fixed question per field, with
fixed options. Three reasons:

* A model asked to phrase its own questions will sometimes ask for something it
  already knows, or ask two things at once.
* Fixed options make the UI a set of buttons rather than a text box, which is
  the difference between a demo that flows and one that stalls.
* The answers map onto known fields, so applying them needs no second LLM call.

The model decides *what is missing*. The library decides *how to ask*.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .spec import AuthMethod, PaginationStyle, SourceType, SpecDraft


class ClarifyingQuestion(BaseModel):
    """One question about one field."""

    model_config = ConfigDict(frozen=True)

    field: str
    question: str
    why: str
    options: tuple[str, ...] = ()
    example: str | None = None
    free_text: bool = False


#: One entry per field that can be missing. Order here is the order asked.
QUESTION_LIBRARY: dict[str, ClarifyingQuestion] = {
    "source_type": ClarifyingQuestion(
        field="source_type",
        question="What kind of data source is this?",
        why="Determines which connector template and driver are used.",
        options=tuple(t.value for t in SourceType),
    ),
    "host": ClarifyingQuestion(
        field="host",
        question="What is the hostname or IP address of the server?",
        why="Required to build the connection URL.",
        example="reporting-db.internal",
        free_text=True,
    ),
    "database": ClarifyingQuestion(
        field="database",
        question="Which database should the connector attach to?",
        why="A server can host many databases; the connector targets one.",
        example="analytics",
        free_text=True,
    ),
    "base_url": ClarifyingQuestion(
        field="base_url",
        question="What is the base URL of the API?",
        why="All request paths are resolved against it.",
        example="https://api.vendor.com/v2",
        free_text=True,
    ),
    "auth_method": ClarifyingQuestion(
        field="auth_method",
        question="How does the source authenticate?",
        why="Selects the auth strategy and the environment variables read at runtime.",
        options=tuple(m.value for m in AuthMethod),
    ),
    "connector_name": ClarifyingQuestion(
        field="connector_name",
        question="What should the generated connector class be called?",
        why="Becomes the class name and the module filename.",
        example="ReportingAnalyticsConnector",
        free_text=True,
    ),
    "header_name": ClarifyingQuestion(
        field="header_name",
        question="Which header carries the API key?",
        why="api_key_header auth needs the exact header name.",
        options=("X-API-Key", "X-Api-Token", "Authorization", "api-key"),
        example="X-API-Key",
        free_text=True,
    ),
    "token_url": ClarifyingQuestion(
        field="token_url",
        question="What is the OAuth2 token endpoint?",
        why="Client-credentials flow exchanges credentials there for a token.",
        example="https://api.vendor.com/oauth/token",
        free_text=True,
    ),
    "pagination": ClarifyingQuestion(
        field="pagination",
        question="How does the API paginate results?",
        why="Determines the loop the generated connector emits.",
        options=tuple(p.value for p in PaginationStyle),
    ),
    "read_only": ClarifyingQuestion(
        field="read_only",
        question="Should the connector be read-only?",
        why="A read-only connector rejects writes before they reach the server.",
        options=("yes", "no"),
    ),
}

#: Fields that become required only once another field takes a certain value.
_CONDITIONAL: dict[tuple[str, str], tuple[str, ...]] = {
    ("auth_method", AuthMethod.API_KEY_HEADER.value): ("header_name",),
    ("auth_method", AuthMethod.OAUTH2_CLIENT_CREDENTIALS.value): ("token_url",),
    ("source_type", SourceType.REST_API.value): ("pagination",),
}


def build_questions(draft: SpecDraft, *, max_questions: int = 3) -> list[ClarifyingQuestion]:
    """Return the questions worth asking about ``draft``.

    Capped deliberately. Six questions in a row is an interrogation; the user
    abandons the form. Ask the most blocking few, act on the answers, ask again
    if still blocked.

    Args:
        draft: The current partial spec.
        max_questions: Ceiling per round.
    """
    needed: list[str] = list(draft.missing_required())

    for (field, value), dependents in _CONDITIONAL.items():
        current = getattr(draft, field, None)
        if current is not None and str(current) == value:
            needed.extend(d for d in dependents if getattr(draft, d, None) is None)

    seen: set[str] = set()
    questions: list[ClarifyingQuestion] = []
    for field in needed:
        if field in seen or field not in QUESTION_LIBRARY:
            continue
        seen.add(field)
        questions.append(QUESTION_LIBRARY[field])
        if len(questions) == max_questions:
            break
    return questions


_BOOL_TRUE = {"yes", "y", "true", "read-only", "read only", "1"}
_BOOL_FALSE = {"no", "n", "false", "read-write", "read write", "0"}


def apply_answers(draft: SpecDraft, answers: dict[str, str]) -> SpecDraft:
    """Fold user answers back into the draft.

    Answers arrive as strings from a form. Coercion happens here rather than in
    the model so that a bad answer produces a clear message instead of a
    validation traceback.

    Args:
        draft: Draft the questions were generated from.
        answers: Mapping of field name to the user's answer.

    Returns:
        A new draft. Unknown fields and blank answers are ignored.
    """
    updates: dict[str, object] = {}

    for field, raw in answers.items():
        if field not in QUESTION_LIBRARY or raw is None:
            continue
        value = raw.strip()
        if not value:
            continue

        match field:
            case "source_type":
                updates[field] = SourceType(value.lower())
            case "auth_method":
                updates[field] = AuthMethod(value.lower())
            case "pagination":
                updates[field] = PaginationStyle(value.lower())
            case "read_only":
                lowered = value.lower()
                if lowered in _BOOL_TRUE:
                    updates[field] = True
                elif lowered in _BOOL_FALSE:
                    updates[field] = False
            case "port" | "page_size":
                updates[field] = int(value)
            case _:
                updates[field] = value

    return draft.merge(**updates)


def summarize_for_review(draft: SpecDraft) -> str:
    """One-paragraph plain-English restatement, shown before generation.

    The point is to catch a misread early: it is far cheaper for the user to
    correct "MySQL" to "SQL Server" here than after a connector has been
    generated, validated, and tested.
    """
    if draft.source_type is None:
        return "Source type not yet identified."

    if draft.source_type.is_sql:
        where = f"{draft.host or '?'}:{draft.port or '?'}/{draft.database or '?'}"
    else:
        where = draft.base_url or "?"

    mode = "read-only" if draft.read_only is not False else "read-write"
    assumed = f" Assumed: {', '.join(draft.assumed_fields)}." if draft.assumed_fields else ""
    return (
        f"A {mode} {draft.source_type.value} connector named "
        f"{draft.connector_name or '?'}, pointing at {where}, authenticating via "
        f"{draft.auth_method.value if draft.auth_method else '?'}.{assumed}"
    )
