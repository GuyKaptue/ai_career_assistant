"""Shared contracts and defensive parsing helpers for job providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.domain.jobs.models import Job


@dataclass(frozen=True)
class JobSearchOptions:
    """Optional filters supported by providers that publish them."""

    radius_km: int | None = None
    published_since_days: int | None = None
    work_time: str | None = None
    contract_type: str | None = None


@dataclass(frozen=True)
class ProviderSearchResult:
    """Provider results and pagination information when the source exposes it."""

    jobs: list[Job]
    total: int | None = None
    has_more: bool | None = None


class JobProviderError(RuntimeError):
    """A safe provider error; it never contains a request URL or credentials."""

    def __init__(
        self,
        provider: str,
        category: str,
        *,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        self.provider = provider
        self.category = category
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(f"{provider}: {category}")


class JobProvider(Protocol):
    """Common synchronous provider interface used by the parallel aggregator."""

    name: str

    def search(
        self,
        query: str,
        location: str | None = None,
        limit: int = 5,
        page: int = 1,
        options: JobSearchOptions | None = None,
    ) -> ProviderSearchResult: ...


def first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def company_name(value: Any) -> str | None:
    if isinstance(value, dict):
        value = first_present(value, "name", "display_name", "company_name", "firma")
    return optional_text(value)


def valid_job_url(value: Any) -> str | None:
    """Accept only absolute HTTP(S) links without embedded credentials."""
    text = optional_text(value)
    if text is None:
        return None
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    return text


def response_rows(payload: Any, *keys: str, provider: str = "provider") -> list[dict[str, Any]]:
    """Extract a documented list field, rejecting malformed provider payloads."""
    from app.infrastructure.job_providers.base import JobProviderError

    if not isinstance(payload, dict):
        raise JobProviderError(provider, "invalid_response", retryable=False)
    present_key = next((key for key in keys if key in payload), None)
    if present_key is None:
        raise JobProviderError(provider, "invalid_response", retryable=False)
    value = payload[present_key]
    if not isinstance(value, list):
        raise JobProviderError(provider, "invalid_response", retryable=False)
    return [row for row in value if isinstance(row, dict)]


def optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None
