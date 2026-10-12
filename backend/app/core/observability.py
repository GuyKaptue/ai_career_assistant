"""Structured logging / observability (MASTER_IMPLEMANTATION_PROMPT §28).

Every log line is emitted as one JSON object carrying the fields the spec
requires: timestamp, severity, module (logger name), operation, request
correlation ID, duration and — for failures — the error category.

A correlation ID lives in a ``ContextVar`` so any log emitted while a
request is in flight automatically carries it, including logs from deep
inside services and the centralized error handlers.

Secrets are never logged by construction: the formatter only serializes a
whitelist of non-sensitive fields, and neither request/response bodies nor
authorization headers are ever passed to the logger.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextvars import ContextVar, Token
from datetime import datetime, timezone

_CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_CORRELATION_ID_FORBIDDEN = re.compile(r"[^A-Za-z0-9._-]")
MAX_CORRELATION_ID_LENGTH = 64

# Whitelisted structured fields (§28). Anything not listed here is dropped by
# the formatter, which keeps tokens, credentials and payloads out of the log
# stream by construction.
STRUCTURED_FIELDS = (
    "operation",
    "method",
    "path",
    "status",
    "duration_ms",
    "error_category",
    "client",
    "correlation_id",
)

_HANDLER_MARKER = "_ai_career_assistant_structured"


def get_correlation_id() -> str | None:
    """Correlation ID of the request currently in flight, if any."""
    return _CORRELATION_ID.get()


def set_correlation_id(value: str | None) -> Token:
    return _CORRELATION_ID.set(value)


def reset_correlation_id(token: Token) -> None:
    _CORRELATION_ID.reset(token)


def sanitize_correlation_id(raw: str | None) -> str:
    """Turn a client-supplied ``X-Request-ID`` into a log-safe identifier.

    Client input is untrusted: characters that could break log structure
    (newlines, quotes) are replaced, the value is capped in length, and an
    empty result falls back to a generated UUID.
    """
    if not raw:
        return uuid.uuid4().hex
    cleaned = _CORRELATION_ID_FORBIDDEN.sub("-", raw).strip("-")[:MAX_CORRELATION_ID_LENGTH]
    return cleaned or uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger (module), msg + whitelist."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        correlation_id = get_correlation_id()
        if correlation_id is not None:
            payload["correlation_id"] = correlation_id
        for field in STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["stack"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def _coerce_level(level: str) -> int:
    mapping = logging.getLevelNamesMapping()
    return mapping.get(str(level or "INFO").upper(), logging.INFO)


def configure_logging(level: str = "INFO") -> None:
    """Attach the JSON formatter to the root logger exactly once (§28)."""
    resolved = _coerce_level(level)
    root = logging.getLogger()
    root.setLevel(resolved)
    for handler in root.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            handler.setLevel(resolved)
            return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.setLevel(resolved)
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
