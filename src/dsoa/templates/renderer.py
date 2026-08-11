"""Rendering a :class:`SourceSpec` into connector source code.

Deterministic by construction: same spec plus same template version produces
byte-identical output. That is what makes the checksum meaningful, and it is why
the LLM is nowhere near this module.

Jinja is configured with ``StrictUndefined`` so a template referencing a field
the spec does not have fails loudly at render time rather than emitting the
string "None" into someone's production connector.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ..agent.spec import SourceSpec
from .registry import TemplateEntry, TemplateRegistry

TEMPLATE_DIR = Path(__file__).parent / "files"


@dataclass(frozen=True)
class GenerationMeta:
    """Provenance stamped into the generated file's docstring."""

    template_name: str
    template_version: str
    spec_checksum: str
    generated_at: str


@dataclass(frozen=True)
class RenderedConnector:
    """Connector source plus everything needed to explain where it came from."""

    code: str
    module_name: str
    spec: SourceSpec
    entry: TemplateEntry
    meta: GenerationMeta

    @property
    def code_checksum(self) -> str:
        return hashlib.sha256(self.code.encode()).hexdigest()[:12]


def spec_checksum(spec: SourceSpec) -> str:
    """A stable fingerprint of the spec.

    ``sort_keys`` matters: without it, dict ordering changes would produce a new
    checksum for an unchanged spec and make regeneration look like a real diff.
    """
    payload = json.dumps(spec.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


class ConnectorRenderer:
    """Renders specs into connector source."""

    def __init__(
        self,
        registry: TemplateRegistry | None = None,
        *,
        template_dir: Path | None = None,
    ) -> None:
        self._registry = registry or TemplateRegistry()
        self._env = Environment(
            loader=FileSystemLoader(template_dir or TEMPLATE_DIR),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            # S701 flags autoescape=False as an XSS risk, which is correct for
            # HTML and wrong here: the output is a Python module. Escaping would
            # turn every quote in the generated file into &quot;.
            autoescape=False,  # noqa: S701
        )

    def render(self, spec: SourceSpec, *, generated_at: str | None = None) -> RenderedConnector:
        """Render ``spec`` into connector source code.

        Args:
            spec: A complete, validated spec.
            generated_at: Override the timestamp. Pass a fixed value in tests so
                that output stays byte-stable.

        Raises:
            ConfigurationError: no template registered for this spec.
        """
        entry = self._registry.get(spec.template_key)
        template = self._env.get_template(entry.template_name)

        meta = GenerationMeta(
            template_name=entry.template_name,
            template_version=entry.version,
            spec_checksum=spec_checksum(spec),
            generated_at=generated_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        code = template.render(
            spec=spec,
            dialect=entry.dialect,
            meta=meta,
            target_summary=_target_summary(spec),
        )

        return RenderedConnector(
            code=code,
            module_name=spec.module_name,
            spec=spec,
            entry=entry,
            meta=meta,
        )


def _target_summary(spec: SourceSpec) -> str:
    """Credential-free one-liner naming what the connector points at."""
    if spec.sql_target is not None:
        target = spec.sql_target
        base = f"{target.host}:{target.port}/{target.database}"
        return f"{base} (schema {target.schema_name})" if target.schema_name else base
    if spec.rest_target is not None:
        return spec.rest_target.base_url
    return "an unspecified target"
