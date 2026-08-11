"""Deterministic code generation from a SourceSpec."""

from .registry import DIALECTS, DialectProfile, TemplateEntry, TemplateRegistry
from .renderer import ConnectorRenderer, GenerationMeta, RenderedConnector, spec_checksum

__all__ = [
    "DIALECTS",
    "ConnectorRenderer",
    "DialectProfile",
    "GenerationMeta",
    "RenderedConnector",
    "TemplateEntry",
    "TemplateRegistry",
    "spec_checksum",
]
