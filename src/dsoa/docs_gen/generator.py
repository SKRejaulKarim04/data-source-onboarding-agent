"""Onboarding documentation for a generated connector.

The brief's Generative AI section asks for three things: onboarding
documentation, an explanation of the generated code, and dependency plus
configuration instructions.

Two of the three are template work. The README and `requirements.txt` are
derivable from the spec, so generating them with a model would add latency, cost,
and a chance of inventing an environment variable that does not exist — in
exchange for nothing.

The third genuinely wants a model. "Explain this code to a data engineer who has
to review it" is prose about intent, not a fact lookup, and it is where an LLM
actually earns its place. That is why :meth:`DocsGenerator.explain` is the only
method here that takes a client, and why it degrades to a template when none is
configured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ..agent.llm import LLMClient, LLMError
from ..generation import GeneratedConnector
from ..standards.checks import ALL_CHECKS
from ..templates.registry import DIALECTS
from ..templates.renderer import _target_summary

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "files"

EXPLAIN_SYSTEM_PROMPT = """\
You explain generated Python connector code to a data engineer who has to review \
it before it reaches production.

Write 4-6 short paragraphs in plain prose. No headings, no bullet lists, no code \
blocks.

Cover, in this order: what the connector connects to and how it is configured; \
how credentials are supplied and why they are absent from the file; what the \
read path does and what it refuses to do; how failures are handled; and anything \
a reviewer should check before approving it.

Be concrete and specific to the code you are given. Do not praise it. Do not \
restate the docstring. If something in the code looks questionable, say so.
"""


@dataclass(frozen=True)
class ConnectorDocs:
    """The documentation bundle shipped alongside a connector."""

    readme: str
    requirements: str
    explanation: str
    explanation_source: str  # "model" or "template"


class DocsGenerator:
    """Produces the documentation half of an artifact."""

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        template_dir: Path | None = None,
    ) -> None:
        self._client = client
        self._env = Environment(
            loader=FileSystemLoader(template_dir or TEMPLATE_DIR),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            autoescape=False,  # noqa: S701 - output is Markdown, not HTML
        )

    def generate(self, artifact: GeneratedConnector) -> ConnectorDocs:
        """Build the full documentation set for ``artifact``."""
        return ConnectorDocs(
            readme=self.readme(artifact),
            requirements=self.requirements(artifact),
            explanation=(explanation := self.explain(artifact))[0],
            explanation_source=explanation[1],
        )

    def readme(self, artifact: GeneratedConnector) -> str:
        """Render the onboarding README."""
        spec = artifact.spec
        template = self._env.get_template("README.md.j2")
        failed = {f.check for f in artifact.report.errors}
        return template.render(
            spec=spec,
            artifact=artifact,
            dialect=DIALECTS.get(spec.source_type),
            target_summary=_target_summary(spec),
            checks=[name for name, _ in ALL_CHECKS if name not in failed],
        )

    def requirements(self, artifact: GeneratedConnector) -> str:
        """Pin the packages this connector needs to run.

        Derived from the dialect profile rather than parsed out of the code, so
        a connector cannot ship a requirements file that omits its own driver.
        """
        dialect = DIALECTS.get(artifact.spec.source_type)
        lines = [
            f"# Dependencies for {artifact.module_name}",
            f"# Generated {artifact.generated_at} from spec {artifact.spec_checksum}",
            "",
        ]
        
        if dialect:
            lines.extend([
                "sqlalchemy>=2.0.30",
                "pydantic>=2.7",
            ])
            if dialect.driver_package:
                lines.append(f"{dialect.driver_package}    # {dialect.label} driver")
        else:
            lines.extend([
                "requests>=2.31.0",
                "pydantic>=2.7",
            ])
            
        lines.extend(
            [
                "",
                "# The connector framework itself. Replace with your internal",
                "# package index once this is published.",
                "# dsoa>=0.1.0",
                "",
            ]
        )
        return "\n".join(lines)

    def explain(self, artifact: GeneratedConnector) -> tuple[str, str]:
        """Explain the generated code in prose.

        Returns:
            ``(text, source)`` where source is ``"model"`` or ``"template"``.
            The caller shows the source in the UI so a reviewer knows whether
            they are reading generated prose or a canned summary.
        """
        if self._client is None:
            return self._fallback_explanation(artifact), "template"

        try:
            payload = self._client.complete_json(
                system=EXPLAIN_SYSTEM_PROMPT,
                user=(
                    f"Connector module `{artifact.module_name}`:\n\n"
                    "```python\n"
                    f"{artifact.code}\n"
                    "```"
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "explanation": {
                            "type": "string",
                            "description": "4-6 paragraphs of plain prose.",
                        },
                        "review_notes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Anything a reviewer should check.",
                        },
                    },
                    "required": ["explanation"],
                },
                tool_name="emit_explanation",
            )
        except LLMError as exc:
            logger.warning("Explanation unavailable, falling back to template: %s", exc)
            return self._fallback_explanation(artifact), "template"

        text = str(payload.get("explanation", "")).strip()
        if not text:
            return self._fallback_explanation(artifact), "template"

        notes = payload.get("review_notes") or []
        if notes:
            text += "\n\nPoints to check before approving:\n" + "\n".join(
                f"- {note}" for note in notes
            )
        return text, "model"

    def _fallback_explanation(self, artifact: GeneratedConnector) -> str:
        """A deterministic summary, used when no model is configured."""
        spec = artifact.spec
        dialect = DIALECTS.get(spec.source_type)
        
        if dialect is None:
            # REST API fallback
            return (
                f"{spec.connector_name} is a read-only REST API connector "
                f"targeting {_target_summary(spec)}. It extends RestBaseConnector, so "
                "HTTP sessions, schema introspection, and error handling "
                "come from the framework rather than from this file.\n\n"
                "Configuration comes entirely from the environment. The class holds "
                "the target base URL as a default, which is overridable through a "
                f"{spec.auth.env_prefix}-prefixed variable. Credentials are never "
                "present in the file; they are read at runtime.\n\n"
                "The read path uses standard HTTP GET requests and handles response "
                "parsing automatically.\n"
            )

        access = "read-only" if spec.options.read_only else "read-write"

        return (
            f"{spec.connector_name} is a {access} {dialect.label} connector "
            f"targeting {_target_summary(spec)}. It extends SQLBaseConnector, so "
            "connection pooling, retry, schema introspection, and query safety "
            "come from the framework rather than from this file.\n\n"
            "Configuration comes entirely from the environment. The class holds "
            "the target host, port, and database as defaults, and every one is "
            "overridable through a "
            f"{spec.auth.env_prefix}-prefixed variable. Credentials are never "
            "present in the file; they are read at runtime from "
            f"{', '.join(spec.auth.secret_env_vars)}.\n\n"
            "The read path binds parameters rather than interpolating them, and "
            + (
                "rejects write statements before they reach the server. "
                if spec.options.read_only
                else "permits writes, which is worth confirming against the "
                "service account's intended privileges. "
            )
            + "Multi-statement payloads are rejected in all cases.\n\n"
            "Transient failures — timeouts, refused connections, an exhausted "
            f"pool — retry up to {spec.options.max_retries} times with "
            "exponential backoff. Authentication failures do not retry. "
            "test_connection() returns a result object rather than raising, so a "
            "failed check can be logged and inspected.\n\n"
            "Before approving: confirm the service account has only the "
            "privileges this connector needs, and that the host and database "
            "match the system you intended to onboard."
        )
