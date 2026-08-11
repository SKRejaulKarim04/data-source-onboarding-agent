"""API tests using FastAPI's TestClient."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dsoa.api import main
from dsoa.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "llm" in body


def test_index_serves_the_ui(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Data Source Onboarding Agent" in response.text


def test_index_prefers_the_react_build(tmp_path: Path, monkeypatch) -> None:
    """When frontend/dist exists, `/` serves it instead of the fallback page."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>Data Source Onboarding Agent</title>"
        '<script src="/assets/app.js"></script>'
    )
    (dist / "assets" / "app.js").write_text("console.log('built')")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)

    client = TestClient(create_app())

    assert "/assets/app.js" in client.get("/").text
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "built" in asset.text


def test_index_falls_back_when_the_bundle_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """No Node.js, no build — the single-file UI still answers."""
    monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path / "nothing-here")

    client = TestClient(create_app())

    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 404


def test_templates_endpoint_lists_the_registry(client: TestClient) -> None:
    keys = {t["key"] for t in client.get("/api/templates").json()["templates"]}
    assert "postgresql:username_password" in keys


def test_full_happy_path(client: TestClient) -> None:
    """Request -> spec -> generate -> artifact, in one pass."""
    created = client.post("/api/requests", json={"prompt": "Onboard our postgres source"})
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert created.json()["extraction"]["ready"]

    generated = client.post(f"/api/requests/{request_id}/generate").json()
    assert generated["connector"]["accepted"]
    assert generated["connector"]["conformance_pct"] == 100.0
    assert generated["artifact"]["name"]

    download = client.get(f"/api/requests/{request_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert len(download.content) > 1000


def test_incomplete_request_returns_questions(client: TestClient) -> None:
    body = client.post("/api/requests", json={"prompt": "Onboard the mysql orders db"}).json()

    assert body["status"] == "needs_clarification"
    assert body["extraction"]["questions"]
    assert not body["extraction"]["ready"]


def test_answering_questions_unblocks_generation(client: TestClient) -> None:
    request_id = client.post(
        "/api/requests", json={"prompt": "Onboard the mysql orders db"}
    ).json()["id"]

    answered = client.post(
        f"/api/requests/{request_id}/answers", json={"answers": {"host": "mysql.internal"}}
    ).json()

    assert answered["extraction"]["ready"]
    assert client.post(f"/api/requests/{request_id}/generate").json()["connector"]["accepted"]


def test_generating_an_incomplete_spec_is_rejected(client: TestClient) -> None:
    request_id = client.post(
        "/api/requests", json={"prompt": "Onboard the mysql orders db"}
    ).json()["id"]

    response = client.post(f"/api/requests/{request_id}/generate")
    assert response.status_code == 409


def test_pasted_credentials_are_flagged_and_never_returned(client: TestClient) -> None:
    body = client.post(
        "/api/requests",
        json={"prompt": "Onboard postgres at db.internal, database prod, password Hunter2Winter!"},
    ).json()

    assert any(f["kind"] == "credential" for f in body["extraction"]["security_findings"])
    assert "Hunter2Winter" not in str(body)


def test_unknown_request_is_404(client: TestClient) -> None:
    assert client.get("/api/requests/deadbeef").status_code == 404


def test_download_before_generation_is_409(client: TestClient) -> None:
    request_id = client.post(
        "/api/requests", json={"prompt": "Onboard our postgres source"}
    ).json()["id"]
    assert client.get(f"/api/requests/{request_id}/download").status_code == 409


def test_test_before_generation_is_409(client: TestClient) -> None:
    request_id = client.post(
        "/api/requests", json={"prompt": "Onboard our postgres source"}
    ).json()["id"]
    assert (
        client.post(f"/api/requests/{request_id}/test", json={"credentials": {}}).status_code == 409
    )


def test_requests_are_listed(client: TestClient) -> None:
    client.post("/api/requests", json={"prompt": "Onboard our postgres source"})
    assert len(client.get("/api/requests").json()["requests"]) >= 1


def test_activity_log_records_each_step(client: TestClient) -> None:
    request_id = client.post(
        "/api/requests", json={"prompt": "Onboard our postgres source"}
    ).json()["id"]
    body = client.post(f"/api/requests/{request_id}/generate").json()

    joined = " ".join(body["history"])
    assert "Request received" in joined
    assert "Validation" in joined
    assert "Artifact" in joined
