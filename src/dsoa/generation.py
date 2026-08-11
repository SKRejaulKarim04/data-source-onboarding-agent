"""Spec in, validated artifact out.

The single entry point Phase 4's API will call:

    spec -> render -> validate -> (repair if needed) -> GeneratedConnector

Everything the review screen needs travels on the returned object, including the
provenance needed to answer "which template produced this, from which request".
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from .agent.llm import LLMClient
from .agent.spec import SourceSpec
from .standards.models import ValidationReport
from .templates.registry import TemplateRegistry
from .templates.renderer import ConnectorRenderer, RenderedConnector
from .validation.repair import RepairAttempt, RepairLoop
from .validation.static import StaticValidator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeneratedConnector:
    """A finished (or rejected) connector artifact."""

    code: str
    module_name: str
    spec: SourceSpec
    report: ValidationReport
    template_key: str
    template_version: str
    spec_checksum: str
    generated_at: str
    repair_attempts: tuple[RepairAttempt, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def code_checksum(self) -> str:
        return hashlib.sha256(self.code.encode()).hexdigest()[:12]

    @property
    def accepted(self) -> bool:
        """Whether this artifact may be published."""
        return self.report.passed

    @property
    def semver(self) -> str:
        """Artifact version.

        Minor tracks the template so a template bump is visible on every
        artifact it produced; patch counts repair iterations, which makes a
        connector that needed fixing distinguishable at a glance from one that
        rendered clean.
        """
        major, minor, _ = self.template_version.split(".")
        return f"{major}.{minor}.{len(self.repair_attempts)}"

    def summary(self) -> str:
        verdict = "ACCEPTED" if self.accepted else "REJECTED"
        repairs = f", {len(self.repair_attempts)} repair pass(es)" if self.repair_attempts else ""
        return (
            f"{verdict} · {self.module_name} · {self.report.conformance_pct:.0f}% "
            f"conformance{repairs}"
        )


class ConnectorGenerator:
    """Renders, validates, and (when needed) repairs a connector."""

    def __init__(
        self,
        *,
        renderer: ConnectorRenderer | None = None,
        validator: StaticValidator | None = None,
        repair_client: LLMClient | None = None,
        registry: TemplateRegistry | None = None,
        max_repair_iterations: int = 3,
    ) -> None:
        self._renderer = renderer or ConnectorRenderer(registry)
        self._validator = validator or StaticValidator()
        self._repair = (
            RepairLoop(repair_client, self._validator, max_iterations=max_repair_iterations)
            if repair_client is not None
            else None
        )

    def generate(self, spec: SourceSpec, *, generated_at: str | None = None) -> GeneratedConnector:
        """Produce a validated connector from ``spec``.

        Args:
            spec: A complete spec, typically from ``ExtractionResult.finalize()``.
            generated_at: Fixed timestamp for reproducible tests.

        Returns:
            A :class:`GeneratedConnector`. Check :attr:`~GeneratedConnector.accepted`
            before publishing — a rejected artifact is still returned so the UI
            can show what went wrong.
        """
        rendered: RenderedConnector = self._renderer.render(spec, generated_at=generated_at)
        report = self._validator.validate(rendered.code)

        code = rendered.code
        attempts: tuple[RepairAttempt, ...] = ()
        warnings: list[str] = []

        if not report.passed:
            if self._repair is None:
                warnings.append(
                    "Validation failed and no repair client is configured; "
                    "returning the unrepaired candidate."
                )
                logger.warning("Generation failed validation with no repair available")
            else:
                outcome = self._repair.run(code, report)
                code, report = outcome.code, outcome.report
                attempts = tuple(outcome.attempts)
                if not report.passed:
                    warnings.append(f"Still failing after {len(attempts)} repair iteration(s).")

        if report.tools_skipped:
            warnings.append(
                "Not installed, so these checks did not run: " + ", ".join(report.tools_skipped)
            )

        return GeneratedConnector(
            code=code,
            module_name=rendered.module_name,
            spec=spec,
            report=report,
            template_key=rendered.entry.key,
            template_version=rendered.entry.version,
            spec_checksum=rendered.meta.spec_checksum,
            generated_at=rendered.meta.generated_at,
            repair_attempts=attempts,
            warnings=tuple(warnings),
        )
