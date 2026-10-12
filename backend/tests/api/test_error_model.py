"""Stage 3 (BE-06 + BE-07): centralized error model, /api/ready, CORS (§26–§28)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.routes import health as health_module
from app.core import persistence as persistence_module
from app.core.config import REQUIRED_RUNTIME_ENV_KEYS, AppSettings, settings
from app.core.errors import (
    AIProviderError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DatabaseError,
    ExportError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
    register_exception_handlers,
)
from app.core.persistence import SupabaseRepository
from app.main import app as main_app

client = TestClient(main_app)
ALLOWED_ORIGIN = settings.cors_origins[0]


def build_error_app() -> FastAPI:
    """A bare app with only the centralized handlers — one route per error type."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/errs/validation")
    def _validation() -> None:
        raise ValidationError("Bad payload.")

    @test_app.get("/errs/authentication")
    def _authentication() -> None:
        raise AuthenticationError("Authenticate please.")

    @test_app.get("/errs/authorization")
    def _authorization() -> None:
        raise AuthorizationError("Not yours.")

    @test_app.get("/errs/not_found")
    def _not_found() -> None:
        raise NotFoundError("Nothing here.")

    @test_app.get("/errs/external-service")
    def _external_service() -> None:
        raise ExternalServiceError("Upstream is down.")

    @test_app.get("/errs/ai-provider")
    def _ai_provider() -> None:
        raise AIProviderError("Model failed.")

    @test_app.get("/errs/database")
    def _database() -> None:
        raise DatabaseError("Database down.", internal="postgres://user:pw@db.internal:5432")

    @test_app.get("/errs/export")
    def _export() -> None:
        raise ExportError("Export broke.")

    @test_app.get("/errs/configuration")
    def _configuration() -> None:
        raise ConfigurationError("Not configured.")

    @test_app.get("/errs/http-exception")
    def _http_exception() -> None:
        raise HTTPException(status_code=404, detail="Legacy detail.")

    @test_app.get("/errs/boom")
    def _boom() -> None:
        raise RuntimeError("secret-internals-12345")

    return test_app


error_client = TestClient(build_error_app())
masking_client = TestClient(build_error_app(), raise_server_exceptions=False)

TAXONOMY_CASES = [
    ("/errs/validation", 400, "validation"),
    ("/errs/authentication", 401, "authentication"),
    ("/errs/authorization", 403, "authorization"),
    ("/errs/not_found", 404, "not_found"),
    ("/errs/external-service", 502, "external_service"),
    ("/errs/ai-provider", 502, "ai_provider"),
    ("/errs/database", 503, "database"),
    ("/errs/export", 500, "export"),
    ("/errs/configuration", 503, "configuration"),
]


@pytest.mark.parametrize(("path", "status_code", "category"), TAXONOMY_CASES)
def test_error_taxonomy_maps_to_status_and_category(path: str, status_code: int, category: str) -> None:
    response = error_client.get(path)

    assert response.status_code == status_code
    body = response.json()
    assert body["category"] == category
    assert isinstance(body["detail"], str) and body["detail"]
    assert "Traceback" not in response.text


def test_authentication_error_keeps_www_authenticate_header() -> None:
    response = error_client.get("/errs/authentication")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_internal_details_are_logged_not_returned() -> None:
    response = error_client.get("/errs/database")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database down."
    assert "postgres://" not in response.text
    assert "db.internal" not in response.text


def test_http_exception_uses_the_same_envelope() -> None:
    response = error_client.get("/errs/http-exception")

    assert response.status_code == 404
    assert response.json() == {"detail": "Legacy detail.", "category": "not_found"}


def test_unexpected_errors_are_masked() -> None:
    response = masking_client.get("/errs/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error.", "category": "internal"}
    assert "secret-internals-12345" not in response.text
    assert "Traceback" not in response.text


# ---- Real API routes use the envelope (§26/§27) ---------------------------


def test_real_route_401_envelope() -> None:
    response = client.get("/api/v1/profiles/someone")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "A valid bearer token is required.",
        "category": "authentication",
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_typed_body_rejects_wrong_types_with_422() -> None:
    response = client.post("/api/v1/documents/cv/generate", json={"skills": "python-not-a-list"})

    assert response.status_code == 422
    body = response.json()
    assert body["category"] == "validation"
    assert "skills" in body["detail"]
    assert body["errors"][0]["loc"][-1] == "skills"
    assert "Traceback" not in response.text


def test_malformed_json_returns_structured_422() -> None:
    response = client.post(
        "/api/v1/resume/check",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["category"] == "validation"


def test_persistence_unconfigured_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(persistence_module, "settings", AppSettings())

    with pytest.raises(ConfigurationError) as excinfo:
        SupabaseRepository("probe_table", dict).get("some-id")

    assert isinstance(excinfo.value, RuntimeError)  # legacy fallbacks keep working
    assert excinfo.value.status_code == 503


# ---- /api/ready (§28) -----------------------------------------------------


def _force_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in REQUIRED_RUNTIME_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _force_valid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in REQUIRED_RUNTIME_ENV_KEYS:
        monkeypatch.setenv(key, f"test-{key.lower()}-value")


def test_ready_reports_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_missing_config(monkeypatch)

    response = client.get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["config"]["ok"] is False
    for key in REQUIRED_RUNTIME_ENV_KEYS:
        assert key in body["checks"]["config"]["missing"]
    assert "database" in body["checks"]


def test_ready_ok_when_configured_and_database_up(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_valid_config(monkeypatch)
    monkeypatch.setattr(health_module, "_database_check", lambda: {"status": "ok"})

    response = client.get("/api/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["config"]["ok"] is True
    assert body["checks"]["database"]["status"] == "ok"


def test_ready_masks_database_connection_details(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_valid_config(monkeypatch)

    class ExplodingClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def get(self, *args, **kwargs):
            raise httpx.ConnectError("connect to db.internal.prod:5432 failed")

    monkeypatch.setattr(health_module.httpx, "Client", ExplodingClient)

    response = client.get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"]["status"] == "unavailable"
    assert body["checks"]["database"]["detail"] == "The database could not be reached."
    assert "db.internal.prod" not in response.text
    assert "Traceback" not in response.text


def test_health_aliases_both_respond() -> None:
    for path in ("/health", "/api/health"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ---- CORS (§26) -----------------------------------------------------------


def test_cors_allows_configured_origin() -> None:
    response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_cors_rejects_unknown_origin() -> None:
    response = client.get("/health", headers={"Origin": "http://evil.test"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_for_documents_api() -> None:
    response = client.options(
        "/api/v1/documents",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )

    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert "authorization" in response.headers.get("access-control-allow-headers", "").lower()


# ---- OpenAPI (BE-07) ------------------------------------------------------


def test_openapi_documents_tags_and_error_responses() -> None:
    spec = client.get("/openapi.json").json()

    assert spec["info"]["title"] == "AI Career Assistant API"
    tag_names = {tag["name"] for tag in spec.get("tags", [])}
    assert {"health", "profiles", "documents", "applications", "generation", "jobs"} <= tag_names

    assert "/api/ready" in spec["paths"]
    generation_op = spec["paths"]["/api/v1/documents/cv/generate"]["post"]
    assert "422" in generation_op["responses"]
    assert "502" in generation_op["responses"]
    schema_ref = generation_op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref.endswith("CVGenerationPayload")

    documents_op = spec["paths"]["/api/v1/documents"]["get"]
    assert "401" in documents_op["responses"]
    assert "404" in documents_op["responses"]
