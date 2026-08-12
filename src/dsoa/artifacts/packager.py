"""Packaging a connector into a distributable artifact.

An artifact is the unit a data engineering team actually receives: the connector
module, its documentation, its dependencies, and a manifest that ties all of it
back to the original request.

The manifest is the part that matters six months later. When someone asks why a
connector in production behaves a certain way, the answer is a chain —
request -> spec -> template version -> code checksum -> artifact version — and
the manifest is where that chain is written down.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..docs_gen.generator import ConnectorDocs
from ..generation import GeneratedConnector
from ..sandbox.runner import SandboxResult


@dataclass(frozen=True)
class Artifact:
    """A packaged connector, ready to hand over."""

    name: str
    version: str
    files: dict[str, str]
    manifest: dict
    created_at: str

    @property
    def checksum(self) -> str:
        """Fingerprint of the whole bundle, not just the code."""
        digest = hashlib.sha256()
        for path in sorted(self.files):
            digest.update(path.encode())
            digest.update(self.files[path].encode())
        return digest.hexdigest()[:12]

    def to_zip(self) -> bytes:
        """Serialize to a zip archive.

        Timestamps are fixed rather than taken from the clock so that packaging
        the same artifact twice produces identical bytes — the same
        reproducibility argument as the code checksum.
        """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.files):
                info = zipfile.ZipInfo(f"{self.name}/{path}", date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, self.files[path])
        return buffer.getvalue()

    def write_to(self, directory: Path) -> Path:
        """Write the bundle as a directory tree. Returns the root."""
        root = directory / f"{self.name}-{self.version}"
        for path, content in self.files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return root


class ArtifactPackager:
    """Assembles generated code, docs, and provenance into one bundle."""

    def package(
        self,
        connector: GeneratedConnector,
        docs: ConnectorDocs,
        sandbox_result: SandboxResult | None = None,
    ) -> Artifact:
        """Build an artifact.

        Args:
            connector: The validated connector.
            docs: Its documentation bundle.
            sandbox_result: Live connection test, when one was run. Recorded in
                the manifest so a reviewer can see whether the connector was
                ever proven to work, rather than only proven to compile.
        """
        spec = connector.spec
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        manifest = {
            "name": spec.slug,
            "version": connector.semver,
            "created_at": created_at,
            "source": {
                "type": spec.source_type.value,
                "connector_class": spec.connector_name,
                "read_only": spec.options.read_only,
                "target": _safe_target(connector),
            },
            "provenance": {
                "template_key": connector.template_key,
                "template_version": connector.template_version,
                "spec_checksum": connector.spec_checksum,
                "code_checksum": connector.code_checksum,
                "generated_at": connector.generated_at,
                "repair_iterations": len(connector.repair_attempts),
            },
            "validation": {
                "passed": connector.report.passed,
                "checks_run": connector.report.checks_run,
                "checks_passed": connector.report.checks_passed,
                "conformance_pct": round(connector.report.conformance_pct, 1),
                "tools_run": list(connector.report.tools_run),
                "tools_skipped": list(connector.report.tools_skipped),
                "errors": [f.model_dump(mode="json") for f in connector.report.errors],
                "warnings": [f.model_dump(mode="json") for f in connector.report.warnings],
            },
            "connectivity": (
                {
                    "tested": True,
                    "success": sandbox_result.success,
                    "stage": sandbox_result.stage,
                    "tables_discovered": sandbox_result.table_count,
                    "duration_ms": round(sandbox_result.duration_ms, 1),
                    "error": sandbox_result.error,
                }
                if sandbox_result is not None
                else {"tested": False}
            ),
            # Names only. A manifest that carried values would defeat the entire
            # no-hardcoded-credentials design.
            "required_env": list(spec.auth.secret_env_vars)
            + (
                [
                    f"{spec.auth.env_prefix}HOST",
                    f"{spec.auth.env_prefix}PORT",
                    f"{spec.auth.env_prefix}DATABASE",
                ]
                if spec.source_type.is_sql
                else [
                    f"{spec.auth.env_prefix}BASE_URL",
                ]
            ),
        }

        files = {
            connector.module_name: connector.code,
            "README.md": docs.readme,
            "requirements.txt": docs.requirements,
            "EXPLANATION.md": (
                f"# How {spec.connector_name} works\n\n"
                f"_Source: {docs.explanation_source}_\n\n"
                f"{docs.explanation}\n"
            ),
            "manifest.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        }

        return Artifact(
            name=spec.slug,
            version=connector.semver,
            files=files,
            manifest=manifest,
            created_at=created_at,
        )


def _safe_target(connector: GeneratedConnector) -> str:
    spec = connector.spec
    if spec.sql_target is not None:
        return f"{spec.sql_target.host}:{spec.sql_target.port}/{spec.sql_target.database}"
    if spec.rest_target is not None:
        return spec.rest_target.base_url
    return "unknown"
