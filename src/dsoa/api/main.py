"""The web API.

Deliberately in-memory: requests and artifacts live in a dict, not Postgres. The
brief's Postgres is the *onboarded source*, not the app's own store, and adding
SQLAlchemy models plus Alembic migrations here would be a lot of ceremony around
a dictionary. Swapping :class:`RequestStore` for a database-backed one is a
contained change when you need persistence — the rest of the app only sees the
five methods.

Flow:

    POST /api/requests          natural language in, draft + questions out
    POST /api/requests/{id}/answers   fold in clarification answers
    POST /api/requests/{id}/generate  render, validate, document, package
    POST /api/requests/{id}/test      live connection test in the sandbox
    GET  /api/requests/{id}/download  the artifact zip
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..agent.extractor import ExtractionResult, SpecExtractor
from ..agent.llm import AnthropicClient, GeminiClient, DeepseekClient, LLMError, ScriptedClient
from ..agent.spec import SpecDraft
from ..artifacts import Artifact, ArtifactPackager
from ..docs_gen import DocsGenerator
from ..generation import ConnectorGenerator
from ..sandbox import ConnectionSandbox, SandboxResult
from ..standards.checks import ALL_CHECKS

logger = logging.getLogger(__name__)

#: Pre-React single-file UI. Kept as a fallback so the app still serves a
#: working interface on a machine with no Node.js — the Python half of this
#: project has no build step and should not gain one.
STATIC_DIR = Path(__file__).parent / "static"

#: The React build. `npm run ui:build` writes it; `DSOA_FRONTEND_DIST` overrides
#: the location for deployments that ship the bundle separately from the source.
FRONTEND_DIST = Path(
    os.environ.get("DSOA_FRONTEND_DIST")
    or Path(__file__).resolve().parents[3] / "frontend" / "dist"
)


# --- Store ------------------------------------------------------------------


@dataclass
class OnboardingRequest:
    """One request as it moves through the pipeline."""

    id: str
    prompt: str
    created_at: str
    status: str = "extracted"
    extraction: ExtractionResult | None = None
    draft: SpecDraft | None = None
    connector: Any = None
    artifact: Artifact | None = None
    sandbox_result: SandboxResult | None = None
    history: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        self.history.append(f"{stamp}  {message}")


class RequestStore:
    """In-memory store. Replace with a database when you need persistence."""

    def __init__(self) -> None:
        self._items: dict[str, OnboardingRequest] = {}

    def create(self, prompt: str) -> OnboardingRequest:
        request = OnboardingRequest(
            id=uuid.uuid4().hex[:12],
            prompt=prompt,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._items[request.id] = request
        return request

    def get(self, request_id: str) -> OnboardingRequest:
        try:
            return self._items[request_id]
        except KeyError:
            raise HTTPException(status_code=404, detail="Request not found") from None

    def delete(self, request_id: str) -> None:
        try:
            del self._items[request_id]
        except KeyError:
            raise HTTPException(status_code=404, detail="Request not found") from None

    def list(self) -> list[OnboardingRequest]:
        return sorted(self._items.values(), key=lambda r: r.created_at, reverse=True)


# --- Wire models ------------------------------------------------------------


class CreateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)


class AnswersRequest(BaseModel):
    answers: dict[str, str]


class TestRequest(BaseModel):
    credentials: dict[str, str] = Field(
        default_factory=dict,
        description="Passed transiently to the sandbox. Never stored or logged.",
    )


# --- Serialization ----------------------------------------------------------


def _extraction_payload(request: OnboardingRequest) -> dict:
    extraction = request.extraction
    if extraction is None:
        return {}
    draft = request.draft or extraction.draft
    return {
        "summary": extraction.summary(),
        "confidence": extraction.confidence,
        "ready": draft.is_complete and extraction.confidence >= 0.5,
        "missing": list(draft.missing_required()),
        "assumed": list(draft.assumed_fields),
        "notes": list(extraction.notes),
        "security_findings": [
            {"kind": f.kind.value, "label": f.label, "detail": f.detail}
            for f in extraction.security_findings
        ],
        "questions": [
            {
                "field": q.field,
                "question": q.question,
                "why": q.why,
                "options": list(q.options),
                "example": q.example,
                "free_text": q.free_text,
            }
            for q in extraction.questions
        ],
        "draft": draft.model_dump(mode="json"),
    }


def _connector_payload(request: OnboardingRequest) -> dict:
    connector = request.connector
    if connector is None:
        return {}
    failed = {f.check for f in connector.report.errors}
    return {
        "module_name": connector.module_name,
        "code": connector.code,
        "accepted": connector.accepted,
        "semver": connector.semver,
        "template_key": connector.template_key,
        "template_version": connector.template_version,
        "spec_checksum": connector.spec_checksum,
        "code_checksum": connector.code_checksum,
        "conformance_pct": round(connector.report.conformance_pct, 1),
        "summary": connector.report.summary(),
        "warnings": list(connector.warnings),
        "repair_iterations": len(connector.repair_attempts),
        "checks": [{"name": name, "passed": name not in failed} for name, _ in ALL_CHECKS],
        "findings": [
            {
                "check": f.check,
                "severity": f.severity.value,
                "message": f.message,
                "line": f.line,
                "tool": f.tool,
                "remedy": f.remedy,
            }
            for f in connector.report.findings
        ],
    }


def _sandbox_payload(request: OnboardingRequest) -> dict:
    result = request.sandbox_result
    if result is None:
        return {}
    return {
        "success": result.success,
        "stage": result.stage,
        "summary": result.summary(),
        "duration_ms": round(result.duration_ms, 1),
        "error": result.error,
        "error_type": result.error_type,
        "tables": (result.tables or [])[:50],
        "table_count": result.table_count,
    }


def _request_payload(request: OnboardingRequest) -> dict:
    return {
        "id": request.id,
        "prompt": request.prompt,
        "status": request.status,
        "created_at": request.created_at,
        "history": request.history,
        "extraction": _extraction_payload(request),
        "connector": _connector_payload(request),
        "sandbox": _sandbox_payload(request),
        "artifact": (
            {
                "name": request.artifact.name,
                "version": request.artifact.version,
                "checksum": request.artifact.checksum,
                "files": sorted(request.artifact.files),
                "manifest": request.artifact.manifest,
            }
            if request.artifact
            else {}
        ),
    }


# --- App --------------------------------------------------------------------


def build_llm_client() -> GeminiClient | AnthropicClient | DeepseekClient | ScriptedClient:
    """Real client when a key is present, scripted fallback otherwise.

    The fallback is what makes this app demoable with no API key at all, which
    matters more than it sounds when the venue wifi is against you.
    """
    generic_key = os.environ.get("API_KEY", "")
    
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    
    if generic_key.startswith("sk-ant-"):
        anthropic_key = generic_key
    elif generic_key.startswith("sk-"):
        deepseek_key = generic_key
        
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if generic_key.startswith("AIza") or generic_key.startswith("AQ."):
        gemini_key = generic_key

    if deepseek_key:
        try:
            return DeepseekClient(api_key=deepseek_key)
        except LLMError as exc:
            logger.warning("Deepseek fallback: %s", exc)

    if anthropic_key:
        try:
            return AnthropicClient(api_key=anthropic_key)
        except LLMError as exc:
            logger.warning("Anthropic fallback: %s", exc)
            
    if gemini_key:
        try:
            return GeminiClient(api_key=gemini_key)
        except LLMError as exc:
            logger.warning("Gemini fallback: %s", exc)
    return ScriptedClient(
        {
            "postgres": {
                "source_type": "postgresql",
                "connector_name": "AnalyticsConnector",
                "host": "localhost",
                "port": 55432,
                "database": "dsoa_source",
                "auth_method": "username_password",
                "read_only": True,
                "description": "Local Postgres source",
                "confidence": 0.92,
                "assumed_fields": [],
            },
            "mysql": {
                "source_type": "mysql",
                "connector_name": "OrdersConnector",
                "database": "orders",
                "description": "MySQL orders database",
                "confidence": 0.55,
                "assumed_fields": [],
                "notes": ["Host was not stated"],
            },
        },
        default={
            "description": "Could not identify the source",
            "confidence": 0.2,
            "assumed_fields": [],
        },
    )


def create_app() -> FastAPI:
    """Build the application."""
    app = FastAPI(
        title="Data Source Onboarding Agent",
        version="0.1.0",
        description="Natural language in, validated Python connectors out.",
    )

    client = build_llm_client()
    store = RequestStore()
    extractor = SpecExtractor(client)
    generator = ConnectorGenerator(repair_client=client)
    docs_generator = DocsGenerator(client)
    packager = ArtifactPackager()
    sandbox = ConnectionSandbox()

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "llm": type(client).__name__,
            "live_model": isinstance(client, (AnthropicClient, GeminiClient)),
        }

    @app.get("/api/requests")
    def list_requests() -> dict:
        return {
            "requests": [
                {
                    "id": r.id,
                    "prompt": r.prompt[:120],
                    "status": r.status,
                    "created_at": r.created_at,
                }
                for r in store.list()
            ]
        }

    @app.post("/api/requests", status_code=201)
    def create_request(body: CreateRequest) -> dict:
        request = store.create(body.prompt)
        request.log("Request received")

        extraction = extractor.extract(body.prompt)
        request.extraction = extraction
        request.draft = extraction.draft
        request.status = "needs_clarification" if extraction.questions else "extracted"

        # Overwrite the stored prompt with the scrubbed version. The extractor
        # already keeps credentials away from the model, but the raw text was
        # still sitting in the store and going back out over the API — so a
        # pasted password survived in every response for that request. Scrubbing
        # at the boundary is not enough; the record has to hold the clean copy.
        request.prompt = extraction.scrubbed_prompt or body.prompt

        request.log(f"Extracted with confidence {extraction.confidence:.2f}")
        for finding in extraction.security_findings:
            request.log(f"Security: {finding.label}")
        if extraction.questions:
            request.log(f"{len(extraction.questions)} clarifying question(s)")

        return _request_payload(request)

    @app.get("/api/requests/{request_id}")
    def get_request(request_id: str) -> dict:
        return _request_payload(store.get(request_id))

    @app.delete("/api/requests/{request_id}")
    def delete_request(request_id: str) -> dict:
        store.delete(request_id)
        return {"status": "deleted", "id": request_id}

    @app.post("/api/requests/{request_id}/answers")
    def submit_answers(request_id: str, body: AnswersRequest) -> dict:
        request = store.get(request_id)
        if request.extraction is None or request.draft is None:
            raise HTTPException(status_code=409, detail="Nothing extracted yet")

        refined = extractor.refine(request.draft, body.answers)
        request.extraction = refined
        request.draft = refined.draft
        request.status = "needs_clarification" if refined.questions else "extracted"
        request.log(f"Answered {len(body.answers)} question(s)")

        return _request_payload(request)

    @app.post("/api/requests/{request_id}/generate")
    def generate(request_id: str) -> dict:
        request = store.get(request_id)
        if request.draft is None or not request.draft.is_complete:
            raise HTTPException(
                status_code=409,
                detail="Spec is incomplete; answer the outstanding questions first",
            )

        from pydantic import ValidationError
        try:
            spec = request.draft.finalize()
        except ValidationError as exc:
            # Format the validation error into a readable message for the UI
            errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
            msg = "; ".join(errors) if errors else str(exc)
            raise HTTPException(status_code=400, detail=msg)
        request.log(f"Generating from template {spec.template_key}")

        # Relative, not `src.dsoa...`: importing through the `src.` prefix loads
        # a *second* copy of the module, and the ConfigurationError raised by
        # the generator would then not match the one named here.
        from ..connectors.exceptions import ConfigurationError
        try:
            connector = generator.generate(spec)
        except ConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
            
        request.connector = connector
        request.log(f"Validation: {connector.report.summary()}")

        docs = docs_generator.generate(connector)
        request.log(f"Docs generated ({docs.explanation_source})")

        request.artifact = packager.package(connector, docs, request.sandbox_result)
        request.status = "generated" if connector.accepted else "rejected"
        request.log(f"Artifact {request.artifact.name} v{request.artifact.version}")

        return _request_payload(request)

    @app.post("/api/requests/{request_id}/test")
    def test_connection(request_id: str, body: TestRequest | None = None) -> dict:
        request = store.get(request_id)
        if request.connector is None:
            raise HTTPException(status_code=409, detail="Generate the connector first")

        from ..validation.repair import repair_sandbox_error
        import dataclasses
        
        for attempt in range(1, 4):
            request.log(f"Running connection test in sandbox (attempt {attempt})")
            result = sandbox.run(request.connector.code, request.connector.spec, body.credentials)
            request.sandbox_result = result
            request.log(f"Connection test: {result.summary()}")
            
            if result.success:
                break
                
            if attempt < 3 and result.error:
                request.log("Test failed, attempting automated repair...")
                new_code = repair_sandbox_error(
                    client, 
                    request.connector.code, 
                    result.error_type or "Error", 
                    result.error, 
                    result.traceback or ""
                )
                if new_code:
                    # Replace code in the frozen dataclass
                    request.connector = dataclasses.replace(
                        request.connector, 
                        code=new_code, 
                        warnings=request.connector.warnings + (f"Repaired sandbox error on attempt {attempt}",)
                    )
                else:
                    break
            else:
                break

        # Re-package so the manifest records the connectivity result.
        docs = docs_generator.generate(request.connector)
        request.artifact = packager.package(request.connector, docs, result)

        return _request_payload(request)

    @app.get("/api/requests/{request_id}/download")
    def download(request_id: str) -> Response:
        request = store.get(request_id)
        if request.artifact is None:
            raise HTTPException(status_code=409, detail="No artifact yet")

        return Response(
            content=request.artifact.to_zip(),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{request.artifact.name}-'
                    f'{request.artifact.version}.zip"'
                )
            },
        )

    @app.get("/api/templates")
    def templates() -> dict:
        from ..templates.registry import TemplateRegistry

        registry = TemplateRegistry()
        return {
            "templates": [
                {
                    "key": key,
                    "version": (entry := registry.get(key)).version,
                    "template": entry.template_name,
                    "description": entry.description,
                }
                for key in registry.template_keys()
            ]
        }

    @app.get("/")
    def index() -> FileResponse:
        """Serve the React build, falling back to the single-file UI.

        Checked per request rather than at startup so that building the front
        end while uvicorn is already running is enough — no restart needed.
        """
        spa = FRONTEND_DIST / "index.html"
        if spa.is_file():
            return FileResponse(spa, media_type="text/html")
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/assets/{asset_path:path}")
    def frontend_asset(asset_path: str) -> FileResponse:
        """Serve one file from the React bundle.

        A route rather than a StaticFiles mount, for the same reason as the
        index: the directory may not exist when the server starts, and a mount
        insists that it does. Filenames are content-hashed by Vite, so a hit can
        be cached indefinitely.
        """
        root = (FRONTEND_DIST / "assets").resolve()
        target = (root / asset_path).resolve()

        # `..` in the path would otherwise reach outside the bundle.
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")

        return FileResponse(
            target,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


app = create_app()
