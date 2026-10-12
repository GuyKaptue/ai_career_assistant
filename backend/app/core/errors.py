"""Centralized error model (MASTER_IMPLEMANTATION_PROMPT §27).

Every failure that reaches a client is mapped to one consistent JSON envelope:

    {"detail": "<safe user-facing message>", "category": "<error category>"}

The nine spec categories each carry a fixed HTTP status. Internal details
(provider payloads, stack frames, DB response bodies) may be attached via
``internal=`` — they are logged server-side and never included in responses
(§26: no raw Python exceptions, no stack traces).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.observability import get_correlation_id

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for all classified application errors."""

    category: str = "internal"
    status_code: int = 500
    default_message: str = "The request could not be completed."
    headers: dict[str, str] | None = None

    def __init__(self, message: str | None = None, *, internal: str | None = None) -> None:
        self.message = message or self.default_message
        self.internal = internal
        super().__init__(self.message)


class ValidationError(AppError):
    category = "validation"
    status_code = 400
    default_message = "The request payload is invalid."


class AuthenticationError(AppError):
    category = "authentication"
    status_code = 401
    default_message = "Authentication is required."
    headers = {"WWW-Authenticate": "Bearer"}


class AuthorizationError(AppError):
    category = "authorization"
    status_code = 403
    default_message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    category = "not_found"
    status_code = 404
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    category = "conflict"
    status_code = 409
    default_message = "The request conflicts with the current state of the resource."


class ExternalServiceError(AppError):
    category = "external_service"
    status_code = 502
    default_message = "An upstream service is temporarily unavailable."


class AIProviderError(AppError, RuntimeError):
    """AI provider failure (DYNAMIC_HF_PROMPT §14 taxonomy).

    Also subclasses ``RuntimeError`` so every existing ``except RuntimeError``
    fallback (e.g. template fallback on AI failure) keeps working unchanged.
    """

    category = "ai_provider"
    status_code = 502
    default_message = "The AI provider could not complete the request."


class DatabaseError(AppError, RuntimeError):
    """Storage failure. RuntimeError-compatible for existing persistence
    ``except (httpx.HTTPError, RuntimeError)`` fallbacks."""

    category = "database"
    status_code = 503
    default_message = "The database could not be reached."


class ExportError(AppError):
    category = "export"
    status_code = 500
    default_message = "The document could not be exported."


class ConfigurationError(AppError, RuntimeError):
    category = "configuration"
    status_code = 503
    default_message = "The service is not configured to handle this request."


_STATUS_CATEGORIES: dict[int, str] = {
    400: "validation",
    401: "authentication",
    403: "authorization",
    404: "not_found",
    409: "conflict",
    413: "validation",
    415: "validation",
    422: "validation",
    429: "rate_limited",
    500: "internal",
    502: "external_service",
    503: "unavailable",
}


def category_for_status(status_code: int) -> str:
    """Map a bare HTTP status (e.g. from HTTPException) to an error category."""
    if status_code in _STATUS_CATEGORIES:
        return _STATUS_CATEGORIES[status_code]
    if 400 <= status_code < 500:
        return "validation"
    return "internal"


def format_pydantic_errors(exc: Exception) -> str:
    """Build a concise, user-facing summary of a pydantic validation failure.

    Field paths and messages only — never the raw exception repr.
    """
    parts: list[str] = []
    for error in getattr(exc, "errors", lambda: [])():
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = str(error.get("msg", "invalid value"))
        parts.append(f"{location}: {message}" if location else message)
    summary = "; ".join(parts)
    return summary[:400] if summary else "The request payload is invalid."


def request_correlation_id(request: Request) -> str | None:
    """Correlation ID assigned by the logging middleware (§28).

    Reads request-scoped state first (works even when the contextvar has
    already been reset, e.g. in the masked 500 handler), then the contextvar.
    """
    state_id = getattr(request.state, "correlation_id", None)
    return state_id or get_correlation_id()


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the centralized error model onto a FastAPI application (§27)."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        log = logger.warning if exc.status_code < 500 else logger.error
        correlation_id = request_correlation_id(request)
        extra = {"correlation_id": correlation_id} if correlation_id else None
        if exc.internal:
            log(
                "error category=%s status=%s path=%s correlation_id=%s internal=%s",
                exc.category,
                exc.status_code,
                request.url.path,
                correlation_id or "-",
                exc.internal,
                extra=extra,
            )
        else:
            log(
                "error category=%s status=%s path=%s correlation_id=%s",
                exc.category,
                exc.status_code,
                request.url.path,
                correlation_id or "-",
                extra=extra,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "category": exc.category},
            headers=exc.headers,
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else jsonable_encoder(exc.detail)
        log = logger.warning if exc.status_code < 500 else logger.error
        correlation_id = request_correlation_id(request)
        log(
            "error category=%s status=%s path=%s correlation_id=%s",
            category_for_status(exc.status_code),
            exc.status_code,
            request.url.path,
            correlation_id or "-",
            extra={"correlation_id": correlation_id} if correlation_id else None,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail, "category": category_for_status(exc.status_code)},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        raw_errors = exc.errors()
        errors = [
            {
                "loc": [str(item) for item in error.get("loc", ())],
                "msg": str(error.get("msg", "invalid value")),
                "type": str(error.get("type", "")),
            }
            for error in raw_errors
        ]
        summary_parts: list[str] = []
        for error in errors:
            loc = list(error["loc"])  # type: ignore[assignment]
            msg: str = error["msg"]  # type: ignore[assignment]
            if loc:
                loc_str = ".".join(loc)
                summary_parts.append(f"{loc_str}: {msg}")
            else:
                summary_parts.append(msg)
        summary = "; ".join(summary_parts)
        correlation_id = request_correlation_id(request)
        logger.warning(
            "error category=validation status=422 path=%s correlation_id=%s errors=%s",
            request.url.path,
            correlation_id or "-",
            errors,
            extra={"correlation_id": correlation_id} if correlation_id else None,
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Request validation failed: {summary}"[:500],
                "category": "validation",
                "errors": errors,
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Full traceback goes to the server log only — never to the client.
        correlation_id = request_correlation_id(request)
        logger.exception(
            "error category=internal status=500 path=%s correlation_id=%s",
            request.url.path,
            correlation_id or "-",
            extra={"correlation_id": correlation_id} if correlation_id else None,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error.", "category": "internal"},
        )
