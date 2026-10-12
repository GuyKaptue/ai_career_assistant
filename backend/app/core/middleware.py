"""Security and observability middlewares (§12, §28).

Starlette runs the last-added middleware outermost; ``main.py`` wires them as:

    CORSMiddleware → RequestLoggingMiddleware → SecurityHeadersMiddleware
                   → RateLimitMiddleware → routes

* ``RequestLoggingMiddleware`` assigns and propagates the request correlation
  ID (echoing a sanitized ``X-Request-ID``), times the request and emits one
  structured log line per request with method, path, status, duration and —
  for failures — the error category. Bodies, headers and query strings are
  never logged.
* ``SecurityHeadersMiddleware`` adds hardening headers to every response.
  HSTS is production-only; the strict CSP is applied to JSON responses so the
  Swagger UI HTML page keeps working.
* ``RateLimitMiddleware`` enforces a per-client fixed-window request budget
  (``RATE_LIMIT_PER_MINUTE``; 0 disables) and returns the standard
  ``{detail, category}`` envelope with ``category: rate_limited`` plus a
  ``Retry-After`` header. Health/readiness probes and API docs are exempt so
  monitoring never trips the limiter.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import ClassVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.errors import category_for_status
from app.core.observability import reset_correlation_id, sanitize_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
JSON_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
HSTS_HEADER = "max-age=63072000; includeSubDomains"

_EXEMPT_RATE_LIMIT_PATHS = frozenset({"/health", "/api/health", "/api/ready", "/docs", "/redoc", "/openapi.json"})

DispatchNext = Callable[[Request], Awaitable[Response]]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Correlation ID propagation + one structured log line per request (§28)."""

    async def dispatch(self, request: Request, call_next: DispatchNext) -> Response:
        correlation_id = sanitize_correlation_id(request.headers.get("X-Request-ID"))
        token = set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id
        client = request.client.host if request.client else "-"
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.exception(
                    "%s %s raised an exception",
                    request.method,
                    request.url.path,
                    extra={
                        "operation": "http_request",
                        "method": request.method,
                        "path": request.url.path,
                        "status": 500,
                        "duration_ms": duration_ms,
                        "error_category": "internal",
                        "client": client,
                        "correlation_id": correlation_id,
                    },
                )
                raise

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            response.headers["X-Request-ID"] = correlation_id
            extra: dict[str, object] = {
                "operation": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "client": client,
                "correlation_id": correlation_id,
            }
            if response.status_code >= 400:
                extra["error_category"] = category_for_status(response.status_code)
                log = logger.error if response.status_code >= 500 else logger.warning
            else:
                log = logger.info
            log("%s %s -> %s", request.method, request.url.path, response.status_code, extra=extra)
            return response
        finally:
            reset_correlation_id(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Hardening headers on every response (§12)."""

    async def dispatch(self, request: Request, call_next: DispatchNext) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            if header not in response.headers:
                response.headers[header] = value
        if "application/json" in response.headers.get("content-type", "") and (
            "content-security-policy" not in response.headers
        ):
            response.headers["Content-Security-Policy"] = JSON_CONTENT_SECURITY_POLICY
        if settings.environment == "production" and "strict-transport-security" not in response.headers:
            response.headers["Strict-Transport-Security"] = HSTS_HEADER
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client fixed-window request budget (§12).

    Window state is class-level (one application instance per process);
    tests reset it via ``RateLimitMiddleware.clear()``.
    """

    _windows: ClassVar[dict[str, tuple[int, int]]] = {}
    _max_tracked_clients: ClassVar[int] = 10_000

    @classmethod
    def clear(cls) -> None:
        cls._windows.clear()

    async def dispatch(self, request: Request, call_next: DispatchNext) -> Response:
        limit = settings.rate_limit_per_minute
        if limit <= 0 or request.url.path in _EXEMPT_RATE_LIMIT_PATHS:
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        if len(self._windows) >= self._max_tracked_clients:
            # Bounded memory: wholesale reset keeps the tracker O(clients).
            self._windows.clear()
        seen = self._windows.get(client)
        count = seen[1] + 1 if seen is not None and seen[0] == window else 1

        if count > limit:
            retry_after = max(1, int((window + 1) * 60 - time.time()))
            logger.warning(
                "rate limit exceeded for client=%s path=%s",
                client,
                request.url.path,
                extra={
                    "operation": "rate_limit",
                    "path": request.url.path,
                    "client": client,
                    "error_category": "rate_limited",
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Too many requests. Retry after {retry_after} second(s).",
                    "category": "rate_limited",
                },
                headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(limit)},
            )

        self._windows[client] = (window, count)
        response = await call_next(request)
        if "x-ratelimit-limit" not in response.headers:
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response
