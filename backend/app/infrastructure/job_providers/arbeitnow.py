"""Arbeitnow public job-board feed adapter."""

from __future__ import annotations

from typing import Any

from app.domain.jobs.models import Job
from app.infrastructure.job_providers.base import (
    JobProviderError,
    JobSearchOptions,
    ProviderSearchResult,
    company_name,
    optional_text,
    response_rows,
    valid_job_url,
)
from app.infrastructure.job_providers.http import get_json

# The feed exposes its own pagination (`links.next`). Following it is bounded so
# a misbehaving or infinite feed cannot turn one search into unbounded traffic.
MAX_FEED_PAGES = 5


class ArbeitnowProvider:
    name = "arbeitnow"

    def __init__(self, base_url: str | None = None, max_feed_pages: int = MAX_FEED_PAGES) -> None:
        self.base_url = base_url or "https://www.arbeitnow.com/api/job-board-api"
        self.max_feed_pages = max(1, int(max_feed_pages))

    def search(
        self,
        query: str,
        location: str | None = None,
        limit: int = 5,
        page: int = 1,
        options: JobSearchOptions | None = None,
    ) -> ProviderSearchResult:
        del options
        if not query.strip():
            raise ValueError("A search query is required.")
        page = max(1, page)
        limit = min(max(1, limit), 100)
        query_terms = query.casefold().split()
        location_term = location.casefold().strip() if location else ""
        matches: list[Job] = []
        has_more = False
        # The feed filters client-side, so a page can legitimately contain no
        # match for the query. Follow the response's own pagination metadata
        # (bounded by `max_feed_pages`) until `limit` matches are found, the
        # provider reports no next page, or the bound is reached.
        for _ in range(self.max_feed_pages):
            payload = get_json(self.name, self.base_url, params={"page": page})
            if not isinstance(payload, dict):
                raise JobProviderError(self.name, "invalid_response")

            rows = response_rows(payload, "data", provider=self.name)
            for item in rows:
                title = optional_text(item.get("title"))
                company = company_name(item.get("company_name"))
                job_location = optional_text(item.get("location"))
                description = optional_text(item.get("description"))
                raw_tags = item.get("tags")
                tags: list[Any] = raw_tags if isinstance(raw_tags, list) else []
                haystack = " ".join(
                    part for part in (title, company, job_location, description, " ".join(map(str, tags))) if part
                ).casefold()
                if any(term not in haystack for term in query_terms):
                    continue
                if (
                    location_term
                    and location_term not in " ".join((job_location or "", " ".join(map(str, tags)))).casefold()
                ):
                    continue

                remote = item.get("remote") if isinstance(item.get("remote"), bool) else None
                matches.append(
                    Job(
                        title=title,
                        company=company,
                        location=job_location,
                        description=description,
                        url=valid_job_url(item.get("url")),
                        source=self.name,
                        provider_id=optional_text(item.get("slug") or item.get("id")),
                        published_at=optional_text(item.get("created_at")),
                        salary=optional_text(item.get("salary_range")),
                        remote=remote,
                        tags=tuple(str(tag).strip() for tag in tags if str(tag).strip()),
                    )
                )

            links: Any = payload.get("links")
            has_more = isinstance(links, dict) and bool(links.get("next"))
            if len(matches) >= limit or not has_more:
                break
            page += 1

        # The feed does not document a page-size parameter. Preserve all
        # filtered items in its fetched pages so the aggregator can paginate
        # the combined list without silently discarding source rows.
        return ProviderSearchResult(jobs=matches, total=None, has_more=has_more)
