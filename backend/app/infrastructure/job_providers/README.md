## Purpose

The HTTP adapters for the free, public job APIs. Each provider is a thin,
defensive client that returns the shared `Job` model; the aggregation and
the caching live in the domain layer (`app/domain/jobs`).

## Responsibilities

- One client per source: Arbeitsagentur, Arbeitnow, Adzuna (credentials
  required) and Remotive (opt-in)
- Parse the **documented** response shape, including the variants the APIs
  actually return (`ergebnisliste` / `stellenangebote` for the
  Bundesagentur, `data` + `links` + `meta` for Arbeitnow)
- Map the fields faithfully: an unknown value stays unknown, it is never
  replaced with a placeholder like "Unknown company" or "Remote"
- Fail with a typed, credential-free error (`JobProviderError`)
- Never let a credential reach a log: the HTTPX request log is disabled and
  the errors carry no URL

## Credentials

Only Adzuna needs credentials (`ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, free
tier). The other three are keyless. Adzuna's key travels in the query
string, which is exactly why the transport log is off.

## Architecture

```
job_providers/
├── __init__.py
├── adzuna.py          # German market, credentials required
├── arbeitnow.py       # keyless, own pagination
├── arbeitsagentur.py  # keyless, fixed X-API-Key header
├── base.py            # JobProvider protocol + shared helpers
├── http.py            # the shared HTTP client and the error mapping
└── remotive.py        # keyless, remote jobs
```

## Testing

- `tests/unit/test_job_providers.py` — mocked HTTP per provider
- `tests/unit/test_jobs_hardening.py` — aggregation, cache, retry

No test in this package reaches the network.

## Related Modules

- `app/domain/jobs` — the aggregation, the cache and the audit
- `app.application.services.position_extraction` — the posting parser
