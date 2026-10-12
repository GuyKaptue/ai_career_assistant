"""HTTP adapters for external job-search providers."""

from app.infrastructure.job_providers.adzuna import AdzunaProvider
from app.infrastructure.job_providers.arbeitnow import ArbeitnowProvider
from app.infrastructure.job_providers.arbeitsagentur import ArbeitsagenturProvider
from app.infrastructure.job_providers.base import (
    JobProvider,
    JobProviderError,
    JobSearchOptions,
    ProviderSearchResult,
)
from app.infrastructure.job_providers.remotive import RemotiveProvider

__all__ = [
    "AdzunaProvider",
    "ArbeitsagenturProvider",
    "ArbeitnowProvider",
    "JobProvider",
    "JobProviderError",
    "JobSearchOptions",
    "ProviderSearchResult",
    "RemotiveProvider",
]
