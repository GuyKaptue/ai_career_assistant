"""Shared HTTP boundary that keeps provider credentials out of logs/errors."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.infrastructure.job_providers.base import JobProviderError

# Adzuna requires its app key in the query string. HTTPX's INFO request log
# includes the full URL, so keep it disabled before any provider call.
logging.getLogger("httpx").setLevel(logging.WARNING)

REQUEST_TIMEOUT_SECONDS = 8.0


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def get_json(
    provider: str,
    url: str,
    *,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """GET JSON and convert all failures to URL/credential-free errors."""
    try:
        response = httpx.get(
            url,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise JobProviderError(provider, "timeout", retryable=True) from exc
    except httpx.RequestError as exc:
        raise JobProviderError(provider, "connection_error", retryable=True) from exc

    if response.status_code >= 400:
        retryable = response.status_code == 429 or response.status_code >= 500
        category = "rate_limited" if response.status_code == 429 else "upstream_http_error"
        raise JobProviderError(
            provider,
            category,
            retryable=retryable,
            retry_after=parse_retry_after(response.headers.get("Retry-After")),
        )

    try:
        return response.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise JobProviderError(provider, "invalid_json", retryable=False) from exc
