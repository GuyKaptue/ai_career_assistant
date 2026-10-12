"""Adzuna Germany search API adapter."""

from __future__ import annotations

import os
from typing import Any

from app.domain.jobs.models import Job
from app.infrastructure.job_providers.base import (
    JobProviderError,
    JobSearchOptions,
    ProviderSearchResult,
    company_name,
    optional_int,
    optional_text,
    response_rows,
    valid_job_url,
)
from app.infrastructure.job_providers.http import get_json


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _salary(item: dict[str, Any]) -> str | None:
    minimum = _to_float(item.get("salary_min"))
    maximum = _to_float(item.get("salary_max"))
    if minimum is None and maximum is None:
        return None
    if minimum is not None and maximum is not None:
        return f"{minimum:g}–{maximum:g}"
    if minimum is not None:
        return f"from {minimum:g}"
    if maximum is None:
        return None
    return f"up to {maximum:g}"


class AdzunaProvider:
    name = "adzuna"

    def __init__(
        self,
        app_id: str | None = None,
        app_key: str | None = None,
        country: str = "de",
        base_url: str | None = None,
    ) -> None:
        self.app_id = app_id or os.getenv("ADZUNA_APP_ID")
        self.app_key = app_key or os.getenv("ADZUNA_APP_KEY")
        self.country = (country or "de").strip().lower()
        self.base_url = base_url or f"https://api.adzuna.com/v1/api/jobs/{self.country}/search"

    def search(
        self,
        query: str,
        location: str | None = None,
        limit: int = 5,
        page: int = 1,
        options: JobSearchOptions | None = None,
    ) -> ProviderSearchResult:
        del options
        if not self.app_id or not self.app_key:
            raise JobProviderError(self.name, "not_configured")
        if not query.strip():
            raise ValueError("A search query is required.")

        page = max(1, page)
        limit = min(max(1, limit), 50)
        params: dict[str, str | int] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": query.strip(),
            "results_per_page": limit,
            "content-type": "application/json",
        }
        if location and location.strip():
            params["where"] = location.strip()
        payload = get_json(self.name, f"{self.base_url}/{page}", params=params)
        if not isinstance(payload, dict):
            raise JobProviderError(self.name, "invalid_response")
        rows = response_rows(payload, "results", provider=self.name)
        jobs = [
            Job(
                title=optional_text(item.get("title")),
                company=company_name(item.get("company")),
                location=optional_text((item.get("location") or {}).get("display_name"))
                if isinstance(item.get("location"), dict)
                else optional_text(item.get("location")),
                description=optional_text(item.get("description")),
                url=valid_job_url(item.get("redirect_url")),
                source=self.name,
                provider_id=optional_text(item.get("id")),
                published_at=optional_text(item.get("created")),
                salary=_salary(item),
                remote=item.get("telecommuting") if isinstance(item.get("telecommuting"), bool) else None,
            )
            for item in rows
        ]
        total = optional_int(payload.get("count"))
        has_more = page * limit < total if total is not None else None
        return ProviderSearchResult(jobs=jobs, total=total, has_more=has_more)
