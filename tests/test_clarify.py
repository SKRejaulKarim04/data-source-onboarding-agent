"""Clarification loop tests."""

from __future__ import annotations

import pytest

from dsoa.agent.clarify import (
    QUESTION_LIBRARY,
    apply_answers,
    build_questions,
    summarize_for_review,
)
from dsoa.agent.spec import AuthMethod, PaginationStyle, SourceType, SpecDraft

# ---- Question selection ----------------------------------------------------


def test_empty_draft_asks_about_source_type_first() -> None:
    questions = build_questions(SpecDraft())
    assert questions[0].field == "source_type"


def test_missing_host_is_asked_about() -> None:
    draft = SpecDraft(
        source_type=SourceType.POSTGRESQL, connector_name="XConnector", database="d"
    ).apply_defaults()

    assert "host" in {q.field for q in build_questions(draft)}


def test_complete_draft_asks_nothing() -> None:
    draft = SpecDraft(
        source_type=SourceType.POSTGRESQL,
        connector_name="SalesConnector",
        host="db.internal",
        database="sales",
    ).apply_defaults()

    assert build_questions(draft) == []


def test_api_key_auth_triggers_a_header_question() -> None:
    """A conditional requirement: header_name only matters for this auth method."""
    draft = SpecDraft(
        source_type=SourceType.REST_API,
        connector_name="BillingConnector",
        base_url="https://api.vendor.com",
        auth_method=AuthMethod.API_KEY_HEADER,
        pagination=PaginationStyle.NONE,
    ).apply_defaults()

    assert "header_name" in {q.field for q in build_questions(draft)}


def test_bearer_auth_does_not_trigger_a_header_question() -> None:
    draft = SpecDraft(
        source_type=SourceType.REST_API,
        connector_name="BillingConnector",
        base_url="https://api.vendor.com",
        auth_method=AuthMethod.BEARER_TOKEN,
        pagination=PaginationStyle.NONE,
    ).apply_defaults()

    assert "header_name" not in {q.field for q in build_questions(draft)}


def test_oauth_triggers_a_token_url_question() -> None:
    draft = SpecDraft(
        source_type=SourceType.REST_API,
        connector_name="CrmConnector",
        base_url="https://crm.io/api",
        auth_method=AuthMethod.OAUTH2_CLIENT_CREDENTIALS,
        pagination=PaginationStyle.NONE,
    ).apply_defaults()

    assert "token_url" in {q.field for q in build_questions(draft)}


def test_questions_are_capped() -> None:
    """Six questions in a row is an interrogation; the user abandons the form."""
    assert len(build_questions(SpecDraft(source_type=SourceType.REST_API), max_questions=2)) == 2


def test_no_duplicate_questions() -> None:
    fields = [q.field for q in build_questions(SpecDraft(source_type=SourceType.REST_API))]
    assert len(fields) == len(set(fields))


def test_every_question_explains_itself() -> None:
    """The 'why' is what makes the agent read as competent rather than nagging."""
    for question in QUESTION_LIBRARY.values():
        assert question.why
        assert question.question.endswith("?")
        assert question.options or question.free_text


# ---- Applying answers ------------------------------------------------------


def test_answers_are_coerced_to_enums() -> None:
    updated = apply_answers(SpecDraft(), {"source_type": "postgresql"})
    assert updated.source_type is SourceType.POSTGRESQL


def test_free_text_answers_are_applied() -> None:
    updated = apply_answers(SpecDraft(), {"host": "  db.internal  "})
    assert updated.host == "db.internal"


@pytest.mark.parametrize(("answer", "expected"), [("yes", True), ("no", False), ("true", True)])
def test_boolean_answers_are_coerced(answer: str, expected: bool) -> None:
    assert apply_answers(SpecDraft(), {"read_only": answer}).read_only is expected


def test_blank_answers_are_ignored() -> None:
    draft = SpecDraft(host="original.internal")
    assert apply_answers(draft, {"host": "   "}).host == "original.internal"


def test_unknown_fields_are_ignored() -> None:
    """A form can post anything; the loop only accepts fields it asked about."""
    updated = apply_answers(SpecDraft(), {"password": "hunter2", "host": "db.internal"})
    assert updated.host == "db.internal"
    assert not hasattr(updated, "password")


def test_answering_unblocks_the_draft() -> None:
    draft = SpecDraft(source_type=SourceType.POSTGRESQL, connector_name="XConnector")
    assert build_questions(draft)

    answered = apply_answers(draft, {"host": "db.internal", "database": "sales"}).apply_defaults()
    assert build_questions(answered) == []
    assert answered.is_complete


# ---- Review summary --------------------------------------------------------


def test_summary_reads_as_plain_english() -> None:
    draft = SpecDraft(
        source_type=SourceType.POSTGRESQL,
        connector_name="SalesConnector",
        host="db.internal",
        database="sales",
    ).apply_defaults()

    summary = summarize_for_review(draft)
    assert "postgresql" in summary
    assert "db.internal" in summary
    assert "read-only" in summary


def test_summary_discloses_assumptions() -> None:
    draft = SpecDraft(
        source_type=SourceType.POSTGRESQL,
        connector_name="SalesConnector",
        host="db.internal",
        database="sales",
    ).apply_defaults()

    assert "Assumed:" in summarize_for_review(draft)
    assert "port" in summarize_for_review(draft)


def test_summary_handles_an_unknown_source_type() -> None:
    assert "not yet identified" in summarize_for_review(SpecDraft())
