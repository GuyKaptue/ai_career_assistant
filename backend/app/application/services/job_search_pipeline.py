"""Job-search execution (RD-08 §3): analysis keys -> provider queries -> ranked matches.

Everything here is code. The LLM never builds queries, fills ``job_matches``,
produces URLs or assigns a ``match_score``: queries come from the validated
candidate analysis and the user's stated preferences; jobs come only from the
repository's real providers (``app.domain.jobs.service.search_jobs``); URLs are
copied from the provider response; the score is a documented formula over
observable features of each listing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Final

from app.application.services.candidate_analysis import (
    CandidateAnalysis,
    normalize_for_match,
    skill_in_text,
)
from app.domain.jobs.service import JobSearchFailed, search_jobs
from app.domain.users.user_core import UserCore

logger = logging.getLogger(__name__)

MAX_QUERIES: Final = 3
PER_QUERY_LIMIT: Final = 15
MAX_RESULTS: Final = 10

#: Score weights (sum to 1.0). Each term is in [0, 1].
W_SKILLS: Final = 0.45
W_TITLE: Final = 0.30
W_LOCATION: Final = 0.15
W_REMOTE: Final = 0.10

SearchFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ProviderQuery:
    """One structured query executed against every configured provider."""

    keywords: str
    location: str | None


@dataclass(frozen=True)
class RankedJob:
    """A real listing (all fields from the provider) plus a code-computed score."""

    job: dict[str, Any]
    score: float
    matched_skills: tuple[str, ...]


@dataclass(frozen=True)
class JobSearchOutcome:
    """Result of one pipeline run. ``matches`` may be empty; nothing is ever invented."""

    matches: tuple[RankedJob, ...]
    queries: tuple[ProviderQuery, ...]
    excluded_deal_breakers: int
    provider_failed: bool
    partial: bool


def build_provider_queries(core: UserCore, analysis: CandidateAnalysis) -> list[ProviderQuery]:
    """Structured queries: each target title (user's first, then inferred) + top skills, per location."""
    titles = list(core.target_titles) or ([analysis.role_archetype] if analysis.role_archetype else [])
    locations: list[str | None] = list(core.preferred_locations[:2]) or list(analysis.location_signals[:1]) or [None]
    if core.remote_policy == "remote":
        locations = [None]
    top_skills = " ".join(analysis.skills[:2])
    queries: list[ProviderQuery] = []
    seen: set[tuple[str, str | None]] = set()
    for title in titles[:2]:
        for location in locations:
            for keywords in (title, f"{title} {top_skills}".strip()):
                key = (keywords.casefold(), location.casefold() if location else None)
                if keywords and key not in seen:
                    seen.add(key)
                    queries.append(ProviderQuery(keywords, location))
    if not titles and analysis.skills:
        queries.append(ProviderQuery(" ".join(analysis.skills[:3]), locations[0]))
    return queries[:MAX_QUERIES]


def _job_text(job: dict[str, Any]) -> str:
    parts = [job.get("title"), job.get("description"), " ".join(job.get("tags") or ())]
    return normalize_for_match(" ".join(str(p) for p in parts if p))


def score_job(job: dict[str, Any], core: UserCore, analysis: CandidateAnalysis) -> tuple[float, tuple[str, ...]]:
    """Documented formula: skills overlap, title match, location match, remote match."""
    text = _job_text(job)
    matched = tuple(skill for skill in analysis.skills if skill_in_text(skill, text))
    skills_term = len(matched) / max(1, min(len(analysis.skills), 8))
    title_text = normalize_for_match(str(job.get("title") or ""))
    wanted = [*core.target_titles, analysis.role_archetype]
    title_term = 0.0
    for wanted_title in filter(None, wanted):
        words = [w for w in re.split(r"\s+", normalize_for_match(wanted_title).strip()) if w]
        if words:
            title_term = max(title_term, sum(1 for w in words if f" {w} " in title_text) / len(words))
    places = [p for p in (*core.preferred_locations, *analysis.location_signals) if p]
    job_location = normalize_for_match(str(job.get("location") or ""))
    location_term = 1.0 if not places or any(skill_in_text(p, job_location) for p in places) else 0.0
    remote = job.get("remote")
    if core.remote_policy == "remote":
        remote_term = 1.0 if remote else 0.0
    elif core.remote_policy == "onsite":
        remote_term = 0.0 if remote else 1.0
    else:
        remote_term = 1.0
    score = (
        W_SKILLS * min(1.0, skills_term) + W_TITLE * title_term + W_LOCATION * location_term + W_REMOTE * remote_term
    )
    return round(min(1.0, score), 3), matched


def _hits_deal_breaker(job: dict[str, Any], core: UserCore) -> bool:
    text = _job_text(job)
    return any(skill_in_text(term, text) for term in core.deal_breakers)


def run_job_search(
    core: UserCore,
    analysis: CandidateAnalysis,
    *,
    search: SearchFn = search_jobs,
    exclude_job_keys: frozenset[str] = frozenset(),
) -> JobSearchOutcome:
    """Execute queries, merge by ``job_key``, drop deal-breakers/applied, rank, cut to ``MAX_RESULTS``."""
    queries = build_provider_queries(core, analysis)
    merged: dict[str, dict[str, Any]] = {}
    failures = 0
    partial = False
    for query in queries:
        try:
            result = search(query.keywords, query.location, limit=PER_QUERY_LIMIT)
        except (JobSearchFailed, RuntimeError, ValueError):
            failures += 1
            continue
        partial = partial or bool(result.get("partial"))
        for job in result.get("results", []):
            key = str(job.get("job_key") or "")
            if key and key not in exclude_job_keys:
                merged.setdefault(key, job)
    excluded = 0
    ranked: list[RankedJob] = []
    for job in merged.values():
        if _hits_deal_breaker(job, core):
            excluded += 1
            continue
        score, matched = score_job(job, core, analysis)
        ranked.append(RankedJob(job, score, matched))
    ranked.sort(key=lambda r: (-r.score, str(r.job.get("title") or ""), str(r.job.get("job_key"))))
    logger.info(
        "jobsearch.done queries=%d results=%d failed=%d partial=%s",
        len(queries),
        len(ranked),
        failures,
        partial,
    )
    return JobSearchOutcome(
        matches=tuple(ranked[:MAX_RESULTS]),
        queries=tuple(queries),
        excluded_deal_breakers=excluded,
        provider_failed=bool(queries) and failures == len(queries),
        partial=partial,
    )
