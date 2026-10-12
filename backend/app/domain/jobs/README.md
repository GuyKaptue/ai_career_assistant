# Domain — Jobs

## Purpose

Job discovery across free, public job APIs for the German
market (Arbeitsagentur, Arbeitnow, Adzuna; Remotive
opt-in) with parallel queries, provider isolation,
normalization, deduplication, posting-date sorting,
retries, caching, and pagination.

## Responsibilities

- Normalize provider responses into a canonical `Job` model
- Query all configured providers in parallel
- Deduplicate jobs by company + title + location
- Sort results by posting date (newest first)
- Isolate provider failures (one provider down does not affect others)
- Retry transient failures (429 rate limits, 5xx server errors) with exponential backoff
- Cache first-page results with a 1-hour TTL
- Paginate results (page / limit)

## Architecture

![Job API integration architecture](../../../docs/images/job_api_architecture.png)

*Figure: Job search request, aggregation and normalization pipeline (source: [`docs/diagrams/job_api_architecture.dot`](../../../docs/diagrams/job_api_architecture.dot)).*

```
domain/jobs/
├── __init__.py
├── models.py    # unified Job dataclass (single schema for all sources)
├── providers.py # provider registry + JobSearchOptions + normalization helpers
└── service.py   # search_jobs() orchestration: parallel merge, dedup, sort, cache, retry
```

The HTTP adapters for the four providers live in
`app/infrastructure/job_providers/` (see `infrastructure/job_providers/`);
`providers.py` is a domain-level façade that re-exports the public names while
keeping aggregation independent of transport details.

## Providers

| Provider | Credentials | Endpoint |
|----------|-------------|----------|
| `arbeitsagentur` | none (fixed `X-API-Key: jobboerse-jobsuche` header) | `rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs` |
| `arbeitnow` | none | `www.arbeitnow.com/api/job-board-api` |
| `adzuna` | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` (developer.adzuna.com) | `api.adzuna.com/v1/api/jobs/de/search/1` (German market) |
| `remotive` | none (opt-in) | `remotive.com/api/remote-jobs` |

Providers are opt-in: set `JOB_PROVIDER` (comma-separated)
or provide Adzuna credentials. With no provider configured
the service fails fast (503) — no mock/placeholder data.

## Public API

- `search_jobs(query, location=None, limit=5, page=1, options: JobSearchOptions | None = None) -> dict`
  Returns `{results, count, page, limit, total, partial, truncated, provider_status, audit}`.
  `JobSearchOptions` carries the optional provider filters `radius_km`,
  `published_since_days`, `work_time`, `contract_type`.
- `clear_job_cache()` — testing/admin hook.
- `ArbeitsagenturProvider.get_details(refnr)` — full job
  details (base64-encoded refnr, community-documented
  `/pc/v4/jobdetails` endpoint).

The HTTP layer (`GET /api/v1/jobs/search`, `search_jobs_route()` in
`app/main.py`) validates the same parameters with `Query` bounds
(query 1–200 chars, page 1–100, limit 1–50) and maps a blank query to 400,
a missing provider configuration to 503, and a total provider outage
(`JobSearchFailed`) to 502/`external_service`.

## Data Contracts

`Job` (frozen dataclass):
`title, company, location, description, url, source, provider_id,
published_at?, salary?, remote?`

## Dependencies

- `httpx` (HTTP client)
- `os` (provider configuration via `JOB_PROVIDER`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`)

## Configuration

- `JOB_PROVIDER` / `JOB_PROVIDERS` — comma-separated provider names
- `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` — Adzuna credentials
- `JOB_CACHE_TTL_SECONDS` — cache TTL (default 3600 = 1 hour)

## Security

- No user data is sent to job providers
- Provider credentials are read from environment, never hard-coded
- No mock/placeholder job data (fail-fast when no provider configured)

## Error Handling

- `ValueError` — empty query
- `RuntimeError` — no provider configured
- Provider failures are isolated and logged, never crash the search

## Testing

- `tests/unit/test_job_providers.py` — mocked-HTTP tests for
  every client + aggregator (parallel, dedup, sort, retry, cache)
- `tests/unit/test_jobs_hardening.py` — cache, retry, pagination, isolation
- `tests/api/test_api.py` — endpoint-level tests

## Usage

```python
from app.domain.jobs.service import search_jobs

result = search_jobs("data analyst", location="Berlin", limit=10, page=1)
print(result["count"], result["total"])
```

## Extension Points

- Add a new provider by subclassing `JobProvider` and registering it
  in `_build_providers()`
- Adjust cache TTL via `CACHE_TTL_SECONDS` or `JOB_CACHE_TTL_SECONDS`
- Adjust retry behavior via `MAX_RETRIES`, `BASE_BACKOFF_SECONDS`

## Limitations

- Cache is in-memory (not shared across workers)
- Adzuna requires credentials; Arbeitsagentur/Arbeitnow are free
- Arbeitsagentur is community-documented; payload parsing is
  defensive and accepts documented field variants

## Related Modules

- `app.api.routes` — HTTP endpoints
- `app.domain.applications` — saving a job to the tracker
