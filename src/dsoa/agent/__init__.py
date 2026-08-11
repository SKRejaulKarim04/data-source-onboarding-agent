"""The onboarding agent: natural language in, validated SourceSpec out."""

from .clarify import ClarifyingQuestion, apply_answers, build_questions
from .extractor import ExtractionResult, SpecExtractor
from .llm import AnthropicClient, LLMClient, LLMError, ScriptedClient, default_client
from .security import ScrubResult, SecurityFinding, scrub
from .spec import (
    AuthMethod,
    AuthSpec,
    ConnectorOptions,
    PaginationStyle,
    RestTarget,
    SourceSpec,
    SourceType,
    SpecDraft,
    SqlTarget,
    slugify,
)

__all__ = [
    "AnthropicClient",
    "AuthMethod",
    "AuthSpec",
    "ClarifyingQuestion",
    "ConnectorOptions",
    "ExtractionResult",
    "LLMClient",
    "LLMError",
    "PaginationStyle",
    "RestTarget",
    "ScriptedClient",
    "ScrubResult",
    "SecurityFinding",
    "SourceSpec",
    "SourceType",
    "SpecDraft",
    "SpecExtractor",
    "SqlTarget",
    "apply_answers",
    "build_questions",
    "default_client",
    "scrub",
    "slugify",
]
