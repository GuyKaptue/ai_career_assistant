"""Liveness and readiness probes (MASTER_IMPLEMANTATION_PROMPT §28).

- ``GET /health`` and ``GET /api/health`` — liveness, always 200 while the
  process serves requests.
- ``GET /api/ready`` — readiness: required runtime config present *and*
  the database answers a probe. 503 with a per-check report when not ready.
  Probe failures return safe messages only; details are logged server-side.
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

import app.application.services.shared_router as shared_router_module
from app.api.schemas import ReadyResponse
from app.application.services.ollama_first_adapter import OllamaFirstAdapter
from app.core.config import REQUIRED_RUNTIME_ENV_KEYS, settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def _config_check() -> dict:
    missing = [
        key
        for key in REQUIRED_RUNTIME_ENV_KEYS
        if not (os.getenv(key) or "").strip()
        or (os.getenv(key) or "").startswith("your_")
        or (os.getenv(key) or "").startswith("replace_with_")
    ]
    return {"ok": not missing, "missing": missing}


def _database_check() -> dict:
    """Probe PostgREST. Returns a status dict; never raises, never leaks."""
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return {"status": "not_configured", "detail": "Supabase is not configured; using local storage."}
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(
                f"{url}/rest/v1/",
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.error("readiness.database unreachable: %s", exc)
        return {"status": "unavailable", "detail": "The database could not be reached."}
    if response.status_code >= 400:
        logger.error("readiness.database rejected probe with HTTP %s", response.status_code)
        return {"status": "unavailable", "detail": "The database rejected the readiness probe."}
    return {"status": "ok"}


def _ai_check() -> dict:
    """Informational AI-channel status (no network I/O)."""
    huggingface = "configured" if (settings.huggingface_token or "").strip() else "missing"
    if not settings.use_ollama:
        ollama = "disabled"
    else:
        adapter = getattr(shared_router_module, "_adapter", None)
        if isinstance(adapter, OllamaFirstAdapter):
            ollama = "unreachable" if adapter.circuit_state == "OPEN" else "enabled"
        else:
            # No adapter has been built yet (or it could not be constructed):
            # no connect failure has been recorded, so report enabled.
            ollama = "enabled"
    return {"huggingface": huggingface, "ollama": ollama}


@router.get("/health", include_in_schema=False)
@router.get("/api/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}


@router.head("/health", include_in_schema=False)
@router.head("/api/health", include_in_schema=False)
def health_head() -> Response:
    return Response(status_code=200)


@router.get("/api/ready", response_model=ReadyResponse, summary="Readiness probe (§28)")
def readiness() -> JSONResponse:
    config = _config_check()
    database = _database_check()
    ai = _ai_check()
    ready = bool(config["ok"]) and database["status"] == "ok"
    checks = {"config": config, "database": database, "ai": ai}
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "checks": checks,
            "ai": ai,
        },
    )
