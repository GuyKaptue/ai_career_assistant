# Backend changes — project workflow, job filters, tracker, CLI

Verified on the delivered tree: ruff clean, `ruff format --check` clean, mypy clean (94 files),
bandit clean, **609 tests pass** (was 416). The 8 remaining failures (+ the `tests/contract` errors)
are unchanged from the original upload: they need files that are not in `backend.zip`
(personal CV PDFs, `supabase/migrations`, Makefile, CI files, `.env.example`).

See `docs/WORKFLOW_IMPLEMENTATION.md` for behaviour, API and CLI. Apply the migration in
`supabase/migrations/` before using the Supabase-backed stores.

## New files
- `app/api/routes/projects.py`, `positions.py`, `_uploads.py`
- `app/application/services/project_store.py`, `apply_flow.py`, `position_extraction.py`, `model_overrides.py`
- `app/domain/projects/`, `app/domain/positions/`, `app/domain/jobs/keys.py`
- `app/cli_ai.py`
- tests: `tests/api/test_projects_workflow.py`, `tests/unit/test_position_extraction.py`,
  `tests/unit/test_job_keys_and_filters.py`, `tests/unit/test_cli_models.py`

## Modified files
- `app/main.py` (routers; `/jobs/search`: `include_old`, `include_applied`, optional login)
- `app/domain/jobs/service.py` (default recency for all providers, exclusion hook, audit counters)
- `app/domain/jobs/models.py` (`job_key` in results)
- `app/domain/applications/models.py`, `application_tracking.py`, `app/api/routes/applications.py`,
  `app/api/schemas.py` (GET/PATCH application, link fields, job matching)
- `app/application/services/ai_model_router.py` (`set_model_enabled`), `shared_router.py` (apply overrides)
- `app/core/errors.py` (`ConflictError`), `app/cli.py` (registers `models` / `ai`, `jobs search --include-old`)
- tests: `conftest.py` (store + override-file isolation), `test_job_providers.py` (one date-dependent test made explicit)

## Bugs found by the new tests while building this
- Latin-1/Windows-1252 text was decoded as UTF-16 garbage (fixed: UTF-16 only with BOM).
- An invalid `follow_up_date` on apply returned HTTP 500 instead of 400 (fixed).
