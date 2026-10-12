"""Compatibility façade for job providers and domain-level normalization.

Provider HTTP implementations live in ``app.infrastructure.job_providers``;
this module preserves the public imports used by the API, CLI and existing
extensions while keeping domain aggregation independent of transport details.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.domain.jobs.models import Job
from app.infrastructure.job_providers import (
    AdzunaProvider,
    ArbeitnowProvider,
    ArbeitsagenturProvider,
    JobProvider,
    JobProviderError,
    JobSearchOptions,
    ProviderSearchResult,
    RemotiveProvider,
)
from app.infrastructure.job_providers.base import optional_text, valid_job_url

__all__ = [
    "Job",
    "JobProvider",
    "JobProviderError",
    "JobSearchOptions",
    "ProviderSearchResult",
    "RemotiveProvider",
    "ArbeitnowProvider",
    "AdzunaProvider",
    "ArbeitsagenturProvider",
]


_PROVIDERS = {
    "adzuna": AdzunaProvider,
    "arbeitsagentur": ArbeitsagenturProvider,
    "arbeitnow": ArbeitnowProvider,
    "remotive": RemotiveProvider,
}


def _provider_names() -> list[str]:
    raw = os.getenv("JOB_PROVIDER") or os.getenv("JOB_PROVIDERS") or ""
    configured = [part.strip().casefold() for part in raw.split(",") if part.strip()]
    if configured:
        unknown = sorted(set(configured) - _PROVIDERS.keys())
        if unknown:
            raise JobProviderError("configuration", "unknown_provider")
        return list(dict.fromkeys(configured))

    # Providers are opt-in: they must be named in JOB_PROVIDER/JOB_PROVIDERS
    # (see .env.example and domain/jobs/README.md). The single implicit
    # enablement is Adzuna, and only when both of its credentials are present.
    # With nothing configured the search fails fast (503) instead of inventing
    # results or silently reaching free sources the operator did not choose.
    if os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"):
        return ["adzuna"]
    return []


def _build_providers() -> list[JobProvider]:
    return [_PROVIDERS[name]() for name in _provider_names()]


def _coerce_job(value: Job | dict[str, Any]) -> Job:
    if isinstance(value, Job):
        return value
    payload = dict(value)
    raw_remote = payload.get("remote")
    raw_tags = payload.get("tags")
    tags: tuple[Any, ...] | list[Any] = raw_tags if isinstance(raw_tags, (list, tuple)) else ()
    return Job(
        title=optional_text(payload.get("title")),
        company=optional_text(payload.get("company")),
        location=optional_text(payload.get("location")),
        description=optional_text(payload.get("description")),
        url=valid_job_url(payload.get("url")),
        source=optional_text(payload.get("source") or payload.get("provider")) or "provider",
        provider_id=optional_text(payload.get("provider_id") or payload.get("raw_id") or payload.get("id")),
        published_at=optional_text(payload.get("published_at") or payload.get("created_at")),
        salary=optional_text(payload.get("salary") or payload.get("salary_range")),
        remote=raw_remote if isinstance(raw_remote, bool) else None,
        tags=tuple(str(tag).strip() for tag in tags if str(tag).strip()),
    )


def _normalized(value: str | None) -> str:
    if not value:
        return ""
    folded = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[^\w]+", " ", folded, flags=re.UNICODE).strip()


def _identity_key(job: Job, index: int) -> tuple[str, ...]:
    company, title, location = (_normalized(job.company), _normalized(job.title), _normalized(job.location))
    if company and title and location:
        return "identity", company, title, location
    if job.url:
        parsed = urlsplit(job.url)
        canonical_url = urlunsplit(
            (parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"), "", "")
        )
        return "url", canonical_url
    if job.source and job.provider_id:
        return "id", job.source.casefold(), job.provider_id.casefold()
    # Incomplete records without a stable provider identifier must not collapse
    # unrelated vacancies just because their missing fields are all null.
    return "unique", str(index)


def _deduplicate_jobs(values: Sequence[Job | dict[str, Any]]) -> list[Job]:
    """Deduplicate exact company/title/location matches, preserving unknowns."""
    unique: dict[tuple[str, ...], Job] = {}
    for index, value in enumerate(values):
        job = _coerce_job(value)
        key = _identity_key(job, index)
        existing = unique.get(key)
        if existing is None:
            unique[key] = job
            continue
        # Prefer the first provider for stable source attribution but fill its
        # unknown metadata from the duplicate rather than discarding evidence.
        unique[key] = Job(
            title=existing.title or job.title,
            company=existing.company or job.company,
            location=existing.location or job.location,
            description=existing.description or job.description,
            url=existing.url or job.url,
            source=existing.source,
            provider_id=existing.provider_id or job.provider_id,
            published_at=existing.published_at or job.published_at,
            salary=existing.salary or job.salary,
            remote=existing.remote if existing.remote is not None else job.remote,
            tags=existing.tags or job.tags,
        )
    return list(unique.values())
