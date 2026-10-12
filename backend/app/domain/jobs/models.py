"""Unified job model for the German-market job aggregation.

The :class:`Job` dataclass is the single schema shared by every
provider client and the aggregator. Each provider normalizes its
source-specific payload into this shape; the aggregator merges,
deduplicates (by company + title + location), and sorts Jobs by
posting date.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.domain.jobs.keys import job_key


@dataclass(frozen=True)
class Job:
    """Unified job schema across all providers.

    Attributes:
        title: job title.
        company: employer name.
        location: work location (city/region or "Remote").
        description: job description or summary.
        url: application URL.
        source: provider name — "adzuna", "arbeitsagentur",
            "arbeitnow", or "remotive".
        provider_id: source-specific raw id (raw_id).
        published_at: posting date (ISO 8601 when available).
        salary: salary information in provider format.
        remote: whether the role is remote (None when unknown).
    """

    title: str | None
    company: str | None
    location: str | None
    description: str | None
    url: str | None
    source: str
    provider_id: str | None
    published_at: str | None = None
    salary: str | None = None
    remote: bool | None = None
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provider"] = self.source
        # Stable identity shared with the tracker (applied-job exclusion).
        data["job_key"] = job_key(self.company, self.title, self.location)
        return data
