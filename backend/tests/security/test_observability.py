"""Security headers, structured logging and rate limiting (§12, §28)."""

from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.middleware import RateLimitMiddleware
from app.core.observability import JsonFormatter, sanitize_correlation_id
from app.main import app

client = TestClient(app)

SECURITY_HEADERS = (
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Cross-Origin-Opener-Policy",
    "Permissions-Policy",
)


def test_security_headers_on_success_and_error_responses() -> None:
    for path in ("/api/health", "/definitely-missing-route"):
        response = client.get(path)
        for header in SECURITY_HEADERS:
            assert response.headers.get(header), f"missing {header} on {path}"
        # Strict CSP lands on JSON responses only (keeps Swagger UI working).
        assert response.headers.get("Content-Security-Policy")


def test_hsts_only_in_production() -> None:
    try:
        object.__setattr__(config.settings, "environment", "production")
        response = client.get("/api/health")
        assert response.headers["Strict-Transport-Security"] == "max-age=63072000; includeSubDomains"
    finally:
        object.__setattr__(config.settings, "environment", "development")
    assert "Strict-Transport-Security" not in client.get("/api/health").headers


def test_correlation_id_is_echoed() -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"


def test_correlation_id_generated_when_absent() -> None:
    response = client.get("/api/health")
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_correlation_id_is_sanitized() -> None:
    nasty = 'evil"trace\n<script>' + "x" * 100
    response = client.get("/api/health", headers={"X-Request-ID": nasty})
    cid = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,64}", cid)
    assert "\n" not in cid and '"' not in cid


def test_sanitize_correlation_id_falls_back_to_uuid() -> None:
    assert re.fullmatch(r"[0-9a-f]{32}", sanitize_correlation_id(None))
    assert re.fullmatch(r"[0-9a-f]{32}", sanitize_correlation_id("###"))


def test_request_log_carries_structured_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        response = client.get("/missing-for-logging", headers={"X-Request-ID": "log-trace-42"})
    assert response.status_code == 404
    record = next(
        r
        for r in caplog.records
        if getattr(r, "operation", None) == "http_request" and getattr(r, "path", None) == "/missing-for-logging"
    )
    assert record.method == "GET"
    assert record.status == 404
    assert record.error_category == "not_found"
    assert record.correlation_id == "log-trace-42"
    assert record.duration_ms >= 0
    assert record.levelno == logging.WARNING


def test_authorization_header_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    secret = "hf_secret_do_not_log_123"
    with caplog.at_level(logging.DEBUG):
        client.get("/api/health", headers={"Authorization": f"Bearer {secret}", "X-Request-ID": "secrecy-1"})
    messages = " ".join(record.getMessage() for record in caplog.records)
    formatted = " ".join(JsonFormatter().format(record) for record in caplog.records)
    assert secret not in messages
    assert secret not in formatted


def test_json_formatter_emits_spec_fields() -> None:
    logger = logging.getLogger("test.observability.formatter")
    record = logger.makeRecord(
        name="test.observability.formatter",
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="operation finished",
        args=(),
        exc_info=None,
        extra={"operation": "unit", "duration_ms": 12.5, "status": 200, "error_category": None},
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.observability.formatter"
    assert payload["msg"] == "operation finished"
    assert "ts" in payload
    assert payload["operation"] == "unit"
    assert payload["duration_ms"] == 12.5
    assert payload["status"] == 200
    assert "error_category" not in payload  # None values are dropped


def test_error_log_carries_correlation_id(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        response = client.get("/api/v1/profiles/alice", headers={"X-Request-ID": "auth-trace-7"})
    assert response.status_code == 401
    record = next(r for r in caplog.records if "category=authentication" in r.getMessage())
    assert "correlation_id=auth-trace-7" in record.getMessage()


def test_rate_limit_disabled_by_default_for_suite() -> None:
    assert config.settings.rate_limit_per_minute == 0
    assert client.get("/api/v1/templates").status_code == 200


def test_rate_limit_returns_429_envelope() -> None:
    RateLimitMiddleware.clear()
    object.__setattr__(config.settings, "rate_limit_per_minute", 2)
    try:
        assert client.get("/api/v1/templates").status_code == 200
        second = client.get("/api/v1/templates")
        assert second.status_code == 200
        assert second.headers.get("X-RateLimit-Limit") == "2"
        third = client.get("/api/v1/templates")
        assert third.status_code == 429
        assert third.headers.get("Retry-After")
        body = third.json()
        assert body["category"] == "rate_limited"
        assert "Too many requests" in body["detail"]
    finally:
        RateLimitMiddleware.clear()
        object.__setattr__(config.settings, "rate_limit_per_minute", 0)


def test_health_endpoints_exempt_from_rate_limit() -> None:
    RateLimitMiddleware.clear()
    object.__setattr__(config.settings, "rate_limit_per_minute", 1)
    try:
        assert [client.get("/api/health").status_code for _ in range(5)] == [200] * 5
        assert client.get("/api/v1/templates").status_code == 200
        assert client.get("/api/v1/templates").status_code == 429
    finally:
        RateLimitMiddleware.clear()
        object.__setattr__(config.settings, "rate_limit_per_minute", 0)
