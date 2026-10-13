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
from fastapi.responses import JSONResponse

from app.api.schemas import HealthResponse, ReadyResponse
from app.application.services.ollama_status_probe import get_ollama_status
from app.core.config import REQUIRED_RUNTIME_ENV_KEYS

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


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
@router.get("/api/health", response_model=HealthResponse, summary="Liveness probe (§28)")
def health() -> dict:
    return {"status": "ok", "service": "ai-career-assistant"}


@router.get("/api/ready", response_model=ReadyResponse, summary="Readiness probe (§28)")
def readiness() -> JSONResponse:
    config = _config_check()
    database = _database_check()
    ready = bool(config["ok"]) and database["status"] == "ok"
    # Ollama is strictly informational for readiness: it never gates the
    # 200/503 decision. The cluster keeps serving when Ollama is down, just as
    # with any degraded optional channel. See §RD-01.
    ollama = get_ollama_status()
    checks = {"config": config, "database": database, "ollama": ollama.as_check()}
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "checks": checks,
        },
    )
