"""Natural language to :class:`SpecDraft`.

The pipeline, in order:

    raw prompt
      -> scrub (redact credentials, flag injection)
      -> fence as untrusted data
      -> LLM structured extraction
      -> SpecDraft (nulls preserved)
      -> conventional defaults, each one recorded
      -> clarifying questions for whatever is still missing

The extractor never raises on a bad prompt. An unusable request produces an
:class:`ExtractionResult` with low confidence and a list of questions, because
"I could not understand this, here is what I need" is a legitimate outcome that
the UI has to render.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .clarify import ClarifyingQuestion, build_questions, summarize_for_review
from .llm import LLMClient, LLMError
from .prompts import EXTRACTION_SYSTEM_PROMPT, PROMPT_VERSION, extraction_tool_schema
from .security import ScrubResult, SecurityFinding, scrub, wrap_untrusted
from .spec import SourceSpec, SpecDraft

logger = logging.getLogger(__name__)

#: Below this, do not proceed to generation even if the draft looks complete.
#: A confident-looking spec built from a vague prompt is the dangerous case.
CONFIDENCE_FLOOR = 0.5


class ExtractionResult(BaseModel):
    """Everything the API needs to render the review screen."""

    model_config = ConfigDict(frozen=True)

    draft: SpecDraft
    confidence: float = Field(ge=0.0, le=1.0)
    questions: tuple[ClarifyingQuestion, ...] = ()
    security_findings: tuple[SecurityFinding, ...] = ()
    notes: tuple[str, ...] = ()
    unsupported_request: str | None = None
    prompt_version: str = PROMPT_VERSION
    scrubbed_prompt: str = ""

    @property
    def needs_clarification(self) -> bool:
        return bool(self.questions)

    @property
    def ready_to_generate(self) -> bool:
        """Complete, confident, and supported."""
        return (
            self.draft.is_complete
            and not self.questions
            and self.confidence >= CONFIDENCE_FLOOR
            and self.unsupported_request is None
        )

    def summary(self) -> str:
        return summarize_for_review(self.draft)

    def finalize(self) -> SourceSpec:
        """Promote to a strict spec. Check :attr:`ready_to_generate` first."""
        if not self.ready_to_generate:
            raise ValueError(
                "Extraction is not ready: "
                f"complete={self.draft.is_complete}, "
                f"confidence={self.confidence:.2f}, "
                f"open_questions={len(self.questions)}"
            )
        return self.draft.finalize()


class SpecExtractor:
    """Turns a natural language request into a reviewable draft."""

    def __init__(
        self,
        client: LLMClient,
        *,
        max_questions: int = 3,
        confidence_floor: float = CONFIDENCE_FLOOR,
    ) -> None:
        self._client = client
        self._max_questions = max_questions
        self._confidence_floor = confidence_floor

    def extract(self, prompt: str) -> ExtractionResult:
        """Extract a draft from ``prompt``.

        Args:
            prompt: Untrusted user text.

        Returns:
            An :class:`ExtractionResult`, always. Failure is reported through
            low confidence and notes rather than by raising.
        """
        scrubbed = scrub(prompt)
        notes: list[str] = []

        if scrubbed.had_credentials:
            notes.append(
                "Credentials were detected in the request and removed. Supply them "
                "through the environment variables listed in the generated README."
            )
        if scrubbed.had_injection:
            notes.append(
                "The request contained instruction-like text. It was treated as "
                "data and did not influence extraction."
            )

        try:
            payload = self._call_model(scrubbed)
        except LLMError as exc:
            logger.error("Extraction failed: %s", exc)
            return ExtractionResult(
                draft=SpecDraft(),
                confidence=0.0,
                questions=tuple(build_questions(SpecDraft(), max_questions=1)),
                security_findings=scrubbed.findings,
                notes=(*notes, f"Extraction could not be completed: {exc}"),
                scrubbed_prompt=scrubbed.cleaned,
            )

        confidence = float(payload.get("confidence", 0.0) or 0.0)
        notes.extend(str(note) for note in payload.get("notes", []) or [])
        unsupported = payload.get("unsupported_request")

        if payload.get("injection_suspected") and not scrubbed.had_injection:
            notes.append("The model flagged possible instruction injection.")

        draft = self._build_draft(payload, notes)
        draft = draft.apply_defaults()

        questions = tuple(build_questions(draft, max_questions=self._max_questions))

        if unsupported:
            notes.append(
                f"Requested source type is not supported in this release: {unsupported}. "
                "Supported: postgresql, mysql, sqlserver, rest_api."
            )
        elif not questions and confidence < self._confidence_floor:
            notes.append(
                "The draft looks complete but the request was vague. Review every "
                "field before generating."
            )

        return ExtractionResult(
            draft=draft,
            confidence=confidence,
            questions=questions,
            security_findings=scrubbed.findings,
            notes=tuple(notes),
            unsupported_request=unsupported,
            scrubbed_prompt=scrubbed.cleaned,
        )

    def refine(self, draft: SpecDraft, answers: dict[str, str]) -> ExtractionResult:
        """Apply clarification answers and re-check for remaining gaps.

        No second model call: the answers map onto known fields, so folding them
        in is deterministic. Cheaper, faster, and it cannot introduce a new
        misreading of something the user already settled.
        """
        from .clarify import apply_answers

        updated = apply_answers(draft, answers).apply_defaults()
        questions = tuple(build_questions(updated, max_questions=self._max_questions))

        return ExtractionResult(
            draft=updated,
            # Answered directly by the user, so the remaining uncertainty is
            # only about whatever is still unanswered.
            confidence=1.0 if not questions else 0.7,
            questions=questions,
            notes=(
                ("Some details are still needed.",) if questions else ("All details confirmed.",)
            ),
        )

    # ---- Internals ---------------------------------------------------------

    def _call_model(self, scrubbed: ScrubResult) -> dict[str, Any]:
        return self._client.complete_json(
            system=EXTRACTION_SYSTEM_PROMPT,
            user=wrap_untrusted(scrubbed.cleaned),
            schema=extraction_tool_schema(),
            tool_name="emit_source_spec",
        )

    def _build_draft(self, payload: dict[str, Any], notes: list[str]) -> SpecDraft:
        """Build a draft, degrading field-by-field rather than all at once.

        A single bad enum value should cost you that one field, not the entire
        extraction. This is the difference between an agent that recovers and
        one that returns an empty form.
        """
        known = set(SpecDraft.model_fields)
        candidate = {k: v for k, v in payload.items() if k in known and v is not None}

        try:
            return SpecDraft(**candidate)
        except ValidationError as exc:
            bad = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
            notes.append(
                "Dropped unparseable field(s) from the extraction: " + ", ".join(sorted(bad))
            )
            for field in bad:
                candidate.pop(field, None)
            try:
                return SpecDraft(**candidate)
            except ValidationError:
                notes.append("Extraction output could not be parsed at all.")
                return SpecDraft()
