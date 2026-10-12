"""Optional Remotive remote-job feed adapter retained for compatibility."""

from __future__ import annotations

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


class RemotiveProvider:
    name = "remotive"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or "https://remotive.com/api/remote-jobs"

    def search(
        self,
        query: str,
        location: str | None = None,
        limit: int = 5,
        page: int = 1,
        options: JobSearchOptions | None = None,
    ) -> ProviderSearchResult:
        del options, page
        if not query.strip():
            raise ValueError("A search query is required.")
        limit = min(max(1, limit), 20)
        payload = get_json(self.name, self.base_url, params={"search": query.strip(), "limit": limit})
        if not isinstance(payload, dict):
            raise JobProviderError(self.name, "invalid_response")
        rows = response_rows(payload, "jobs", provider=self.name)
        jobs: list[Job] = []
        for item in rows:
            job_location = optional_text(item.get("candidate_required_location") or item.get("job_location"))
            if location and job_location and location.casefold() not in job_location.casefold():
                continue
            remote = True if "remote" in (job_location or "").casefold() else None
            jobs.append(
                Job(
                    title=optional_text(item.get("title")),
                    company=company_name(item.get("company") or item.get("company_name")),
                    location=job_location,
                    description=optional_text(item.get("description")),
                    url=valid_job_url(item.get("url")),
                    source=self.name,
                    provider_id=optional_text(item.get("id")),
                    published_at=optional_text(item.get("published_at") or item.get("date")),
                    salary=optional_text(item.get("salary")),
                    remote=remote,
                )
            )
        return ProviderSearchResult(jobs=jobs, total=optional_int(payload.get("count")), has_more=None)
