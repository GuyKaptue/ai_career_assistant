"""Provider-isolated job search aggregation, pagination, retry and cache policy."""

from __future__ import annotations

import copy
import inspect
import logging
import os
import random
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from app.domain.jobs.models import Job
from app.domain.jobs.providers import (
    JobProvider,
    JobProviderError,
    JobSearchOptions,
    ProviderSearchResult,
    _build_providers,
    _deduplicate_jobs,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 8.0
MAX_PROVIDER_PAGE_SIZE = 50
MAX_PROVIDER_PAGES = 5
PROVIDER_SEARCH_TIMEOUT_SECONDS = 25.0
DEFAULT_CACHE_TTL_SECONDS = 3600.0
DEFAULT_RECENCY_DAYS = 30
MAX_RECENCY_DAYS = 100


def _cache_ttl() -> float:
    try:
        configured = float(os.getenv("JOB_CACHE_TTL_SECONDS", "3600"))
    except (TypeError, ValueError):
        return DEFAULT_CACHE_TTL_SECONDS
    return max(0.0, configured)


CACHE_TTL_SECONDS = _cache_ttl()


def default_recency_days() -> int | None:
    """Default maximum posting age (``JOB_DEFAULT_RECENCY_DAYS``, 30 by default).

    ``0`` (or a negative / invalid value) disables the default filter. The
    filter itself is applied by the aggregator to *every* provider, because
    only some sources can filter by age on their own.
    """
    raw = os.getenv("JOB_DEFAULT_RECENCY_DAYS")
    if raw is None:
        return DEFAULT_RECENCY_DAYS
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RECENCY_DAYS
    return min(days, MAX_RECENCY_DAYS) if days > 0 else None


@dataclass
class CacheEntry:
    response: Any
    expires_at: float


@dataclass
class SearchAudit:
    query: str
    location: str | None
    page: int
    limit: int
    providers_attempted: int
    providers_succeeded: int
    providers_failed: int
    total_results: int
    cached: bool
    duration_ms: int
    errors: list[dict[str, str]] = field(default_factory=list)
    recency_days: int | None = None
    filtered_old: int = 0
    undated_kept: int = 0
    excluded_applied: int = 0


@dataclass
class ProviderOutcome:
    provider: str
    jobs: list[Job]
    status: str
    error_category: str | None = None


class JobSearchFailed(RuntimeError):
    """Raised when every configured provider failed; contains no raw errors."""

    def __init__(self, provider_errors: list[dict[str, str]]) -> None:
        self.provider_errors = provider_errors
        super().__init__("All configured job providers are temporarily unavailable.")


_cache: dict[str, CacheEntry] = {}
_cache_lock = threading.RLock()


def _cache_key(
    query: str,
    location: str | None,
    page: int,
    limit: int,
    provider_names: tuple[str, ...] = (),
    options: JobSearchOptions | None = None,
    extra: str = "",
) -> str:
    filters = options or JobSearchOptions()
    normalized_location = " ".join((location or "").casefold().split())
    normalized_query = " ".join(query.casefold().split())
    filter_key = ":".join(
        str(value or "")
        for value in (filters.radius_km, filters.published_since_days, filters.work_time, filters.contract_type)
    )
    return "|".join(
        (normalized_query, normalized_location, str(page), str(limit), ",".join(provider_names), filter_key, extra)
    )


def _prune_cache(now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    with _cache_lock:
        expired = [key for key, entry in _cache.items() if entry.expires_at <= current]
        for key in expired:
            _cache.pop(key, None)


def _get_cached(
    query: str,
    location: str | None,
    page: int,
    limit: int,
    provider_names: tuple[str, ...] = (),
    options: JobSearchOptions | None = None,
    extra: str = "",
) -> Any | None:
    now = time.monotonic()
    key = _cache_key(query, location, page, limit, provider_names, options, extra)
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None or entry.expires_at <= now:
            _cache.pop(key, None)
            return None
        return copy.deepcopy(entry.response)


def _set_cache(
    query: str,
    location: str | None,
    page: int,
    limit: int,
    response: Any,
    provider_names: tuple[str, ...] = (),
    options: JobSearchOptions | None = None,
    extra: str = "",
) -> None:
    ttl = _cache_ttl()
    if ttl <= 0:
        return
    _prune_cache()
    key = _cache_key(query, location, page, limit, provider_names, options, extra)
    with _cache_lock:
        _cache[key] = CacheEntry(copy.deepcopy(response), time.monotonic() + ttl)


def _status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    message = str(exc)
    for code in (429, 500, 502, 503, 504, 505, 507):
        if str(code) in message:
            return code
    return None


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, JobProviderError):
        return exc.retryable
    code = _status_code(exc)
    if code == 429 or (code is not None and 500 <= code <= 599):
        return True
    message = str(exc).casefold()
    return "rate limit" in message or "too many requests" in message


# Kept for older callers/tests; transient server errors are included as well.
_is_rate_limit_error = _is_retryable_error


def _error_category(exc: Exception) -> str:
    if isinstance(exc, JobProviderError):
        return exc.category
    if _status_code(exc) == 429:
        return "rate_limited"
    if _status_code(exc) is not None:
        return "upstream_http_error"
    return "provider_error"


def _retry_delay(exc: Exception, attempt: int) -> float:
    retry_after = exc.retry_after if isinstance(exc, JobProviderError) else None
    if retry_after is not None:
        base = min(MAX_BACKOFF_SECONDS, retry_after)
    else:
        base = min(BASE_BACKOFF_SECONDS * (2**attempt), MAX_BACKOFF_SECONDS)
    return random.uniform(base * 0.8, base * 1.2)  # nosec B311 - retry jitter, not security-sensitive


def _invoke_provider(
    provider: JobProvider,
    query: str,
    location: str | None,
    limit: int,
    page: int,
    options: JobSearchOptions | None,
) -> ProviderSearchResult:
    """Call current adapters and older third-party implementations safely."""
    parameters = inspect.signature(provider.search).parameters
    accepts_keywords = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    kwargs: dict[str, Any] = {"query": query, "location": location, "limit": limit}
    if accepts_keywords or "page" in parameters:
        kwargs["page"] = page
    if accepts_keywords or "options" in parameters:
        kwargs["options"] = options
    result = provider.search(**kwargs)
    if isinstance(result, ProviderSearchResult):
        return result
    if isinstance(result, list):
        return ProviderSearchResult(jobs=result)
    raise JobProviderError(provider.name, "invalid_response")


def _search_with_retry_result(
    provider: JobProvider,
    query: str,
    location: str | None,
    limit: int,
    page: int = 1,
    options: JobSearchOptions | None = None,
) -> ProviderSearchResult:
    """Retry only classified transient errors; never log provider exception text."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return _invoke_provider(provider, query, location, limit, page, options)
        except Exception as exc:
            last_error = exc
            if not _is_retryable_error(exc) or attempt + 1 >= MAX_RETRIES:
                logger.warning("jobs.provider_error provider=%s category=%s", provider.name, _error_category(exc))
                break
            delay = _retry_delay(exc, attempt)
            logger.warning(
                "jobs.provider_retry provider=%s category=%s attempt=%d delay_ms=%d",
                provider.name,
                _error_category(exc),
                attempt + 1,
                round(delay * 1000),
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error
    return ProviderSearchResult(jobs=[])


def _search_with_retry(
    provider: JobProvider,
    query: str,
    location: str | None,
    limit: int,
    page: int = 1,
    options: JobSearchOptions | None = None,
) -> list[Job]:
    """Backward-compatible list-returning retry entry point."""
    return _search_with_retry_result(provider, query, location, limit, page, options).jobs


def _collect_provider(
    provider: JobProvider, query: str, location: str | None, result_window: int, options: JobSearchOptions | None
) -> ProviderOutcome:
    jobs: list[Job] = []
    remaining = result_window
    page = 1
    while remaining > 0 and page <= MAX_PROVIDER_PAGES:
        request_limit = min(MAX_PROVIDER_PAGE_SIZE, remaining)
        try:
            page_result = _search_with_retry_result(
                provider, query, location, request_limit, page=page, options=options
            )
        except Exception as exc:
            return ProviderOutcome(provider.name, jobs, "partial" if jobs else "failed", _error_category(exc))
        page_jobs = page_result.jobs
        jobs.extend(page_jobs)
        remaining = max(0, result_window - len(jobs))
        if page_result.has_more is False:
            break
        if len(jobs) >= result_window:
            break
        # Legacy adapters without pagination metadata only get one request.
        # New adapters continue when their contract says more rows are available.
        if page_result.has_more is None and len(page_jobs) < request_limit:
            break
        if not page_jobs and page_result.has_more is not True:
            break
        page += 1
    return ProviderOutcome(provider.name, jobs[:result_window], "succeeded")


def _parse_posted_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    for date_format in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return None


def _sort_by_posted_date(jobs: list[Job]) -> list[Job]:
    """Stable newest-first order; missing/invalid dates always sort last."""
    return sorted(jobs, key=lambda job: _parse_posted_at(job.published_at) or datetime.min, reverse=True)


def _apply_recency(jobs: list[Job], days: int | None, now: datetime | None = None) -> tuple[list[Job], int, int]:
    """Drop postings older than ``days``; returns ``(kept, dropped, undated_kept)``.

    A posting without a usable date cannot be proven old, so it is kept (and
    counted) instead of silently disappearing; it sorts last anyway.
    """
    if days is None:
        return jobs, 0, 0
    cutoff = (now or datetime.now(timezone.utc).replace(tzinfo=None)) - timedelta(days=days)
    kept: list[Job] = []
    dropped = 0
    undated = 0
    for job in jobs:
        posted = _parse_posted_at(job.published_at)
        if posted is None:
            undated += 1
            kept.append(job)
        elif posted >= cutoff:
            kept.append(job)
        else:
            dropped += 1
    return kept, dropped, undated


def _audit_to_dict(audit: SearchAudit) -> dict[str, Any]:
    return {
        "query": audit.query,
        "location": audit.location,
        "page": audit.page,
        "limit": audit.limit,
        "providers_attempted": audit.providers_attempted,
        "providers_succeeded": audit.providers_succeeded,
        "providers_failed": audit.providers_failed,
        "total_results": audit.total_results,
        "cached": audit.cached,
        "duration_ms": audit.duration_ms,
        "errors": audit.errors,
        "recency_days": audit.recency_days,
        "filtered_old": audit.filtered_old,
        "undated_kept": audit.undated_kept,
        "excluded_applied": audit.excluded_applied,
    }


def search_jobs(
    query: str,
    location: str | None = None,
    limit: int = 5,
    page: int = 1,
    options: JobSearchOptions | None = None,
    *,
    include_old: bool = False,
    exclude: Callable[[Job], bool] | None = None,
    exclude_token: str = "",
) -> dict[str, Any]:
    """Search configured sources concurrently, returning safe partial results.

    Recency: unless ``include_old`` is set, only postings published within
    ``options.published_since_days`` (default ``JOB_DEFAULT_RECENCY_DAYS``, 30)
    are returned, whichever provider they came from. ``exclude`` removes jobs
    the caller already handled (e.g. applied); ``exclude_token`` must change
    whenever the excluded set changes because it is part of the cache key.

    Aggregated pages are stable offsets into each provider's bounded (at most
    ``MAX_PROVIDER_PAGES`` × 50) fetched window. Complete failures raise
    ``JobSearchFailed``; successful empty searches remain valid empty results.
    """
    started = time.monotonic()
    if not query or not query.strip():
        raise ValueError("A search query is required before job results can be fetched.")
    normalized_query = " ".join(query.split())
    normalized_location = " ".join(location.split()) if location and location.strip() else None
    safe_limit = max(1, min(int(limit), 50))
    safe_page = max(1, min(int(page), 100))

    providers = _build_providers()
    if not providers:
        raise RuntimeError("No job provider has been configured. Configure at least one real provider.")
    provider_names = tuple(provider.name for provider in providers)
    if include_old:
        recency_days: int | None = None
    elif options is not None and options.published_since_days is not None:
        recency_days = options.published_since_days
    else:
        recency_days = default_recency_days()
    # Providers that can filter by age do so server-side; everyone else is
    # filtered below, so the behaviour is identical across sources.
    options = replace(options or JobSearchOptions(), published_since_days=recency_days)
    extra = f"x:{exclude_token}" if exclude is not None else ""
    cached = _get_cached(normalized_query, normalized_location, safe_page, safe_limit, provider_names, options, extra)
    if cached is not None:
        cached["audit"]["cached"] = True
        cached["audit"]["duration_ms"] = int((time.monotonic() - started) * 1000)
        return cached

    result_window = safe_page * safe_limit
    max_window = MAX_PROVIDER_PAGE_SIZE * MAX_PROVIDER_PAGES
    truncated = result_window > max_window
    result_window = min(result_window, max_window)
    outcomes: list[ProviderOutcome] = []
    executor = ThreadPoolExecutor(max_workers=max(1, len(providers)))

    def submit(provider: JobProvider):
        return executor.submit(
            _collect_provider,
            provider,
            normalized_query,
            normalized_location,
            result_window,
            options,
        )

    futures = {submit(provider): provider for provider in providers}
    try:
        for future in as_completed(futures, timeout=PROVIDER_SEARCH_TIMEOUT_SECONDS):
            provider = futures[future]
            try:
                outcomes.append(future.result())
            except Exception:
                outcomes.append(ProviderOutcome(provider.name, [], "failed", "provider_error"))
    except FuturesTimeoutError:
        for future, provider in futures.items():
            if not future.done():
                future.cancel()
                outcomes.append(ProviderOutcome(provider.name, [], "failed", "timeout"))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # Keep response provider ordering stable despite completion order.
    outcomes.sort(key=lambda outcome: provider_names.index(outcome.provider))
    errors = [
        {"provider": outcome.provider, "category": outcome.error_category or "provider_error"}
        for outcome in outcomes
        if outcome.status in {"failed", "partial"}
    ]
    successful_count = sum(outcome.status == "succeeded" for outcome in outcomes)
    if not successful_count and outcomes and all(not outcome.jobs for outcome in outcomes):
        raise JobSearchFailed(errors or [{"provider": "all", "category": "timeout"}])

    deduplicated = _deduplicate_jobs([job for outcome in outcomes for job in outcome.jobs])
    recent, filtered_old, undated_kept = _apply_recency(deduplicated, recency_days)
    excluded_applied = 0
    if exclude is not None:
        remaining = [job for job in recent if not exclude(job)]
        excluded_applied = len(recent) - len(remaining)
        recent = remaining
    merged = _sort_by_posted_date(recent)
    start = (safe_page - 1) * safe_limit
    page_jobs = merged[start : start + safe_limit]
    provider_status = [
        {"provider": outcome.provider, "status": outcome.status, "count": len(outcome.jobs)} for outcome in outcomes
    ]
    audit = SearchAudit(
        query=normalized_query,
        location=normalized_location,
        page=safe_page,
        limit=safe_limit,
        providers_attempted=len(providers),
        providers_succeeded=successful_count,
        providers_failed=len(errors),
        total_results=len(merged),
        cached=False,
        duration_ms=int((time.monotonic() - started) * 1000),
        errors=errors,
        recency_days=recency_days,
        filtered_old=filtered_old,
        undated_kept=undated_kept,
        excluded_applied=excluded_applied,
    )
    result = {
        "results": [job.to_dict() for job in page_jobs],
        "count": len(page_jobs),
        "page": safe_page,
        "limit": safe_limit,
        "total": len(merged),
        "partial": bool(errors),
        "truncated": truncated,
        "provider_status": provider_status,
        "audit": _audit_to_dict(audit),
    }
    # Cache only complete provider outcomes: partial data should be retried
    # rather than served as if it were a fresh complete aggregate.
    if not errors:
        _set_cache(normalized_query, normalized_location, safe_page, safe_limit, result, provider_names, options, extra)
    logger.info(
        "jobs.search page=%d limit=%d providers_succeeded=%d providers_failed=%d results=%d duration_ms=%d",
        safe_page,
        safe_limit,
        successful_count,
        len(errors),
        len(page_jobs),
        audit.duration_ms,
    )
    return result


def clear_job_cache() -> None:
    """Clear cached search responses (administrative/testing hook)."""
    with _cache_lock:
        _cache.clear()
