# Evaluation methodology

## 1. Test strategy

The project uses a layered test strategy:

| Layer | Scope | Example |
|-------|-------|---------|
| Unit | Domain logic, services, utilities | `test_ats_checker.py`, `test_jobs_hardening.py` |
| Integration | Provider adapters, document generation | `test_cover_letter_docx.py` |
| API | HTTP endpoints, auth, validation, error model | `test_api.py`, `test_error_model.py` |
| Security | Token validation, cross-user isolation | `test_auth.py`, `test_authorization.py` |
| Contract | Schema validation, migration structure | `test_migrations.py` |
| Migration | Schema, constraints, RLS policy structure | `test_migrations.py` |

## 2. Hermetic tests

All tests run without a live Supabase instance. When `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` are unset, the stores use the in-memory
backend. Tests that require a live database are marked and skipped in
CI (`-k "not test_supabase_crud"`).

## 3. Quality gates

Every change must pass:

```
ruff check .                  # lint
ruff format --check .         # format
python -m mypy app            # type check
python -m pytest -q           # tests
```

## 4. Proof obligations

The project maintains explicit proofs for security-critical claims:

| Claim | Proof |
|-------|-------|
| Identity from JWT `sub`, never request body | `test_authorization.py` |
| Cross-user access returns 404 | `test_authorization.py` |
| No mock/placeholder job data (fail-fast 503) | `test_api.py::test_job_search_endpoint_requires_provider_configuration` |
| HS256 JWT with 32-char secret | `test_auth.py` |
| RLS policies scoped to `authenticated` | `test_migrations.py` |
| Migration constraints and ownership isolation | `test_migrations.py` |
| No copyleft dependencies | `make licenses` |

## 5. Metrics

Production metrics (§28):

- `ai_requests_total` / `ai_requests_success_total` / `ai_requests_failed_total`
- `ai_model_selected_total` (per model, per task)
- `ai_model_fallback_total`
- `ai_latency_seconds` (histogram, per task)
- `ai_tokens_input_total` / `ai_tokens_output_total`
- `ai_model_health` (gauge, per model)
- `ai_model_circuit_open` (gauge, per model)
- `ai_rate_limit_total` / `ai_timeout_total` / `ai_context_limit_total`
- `ai_provider_failure_total` (per failure type)

## 6. Known limitations of evaluation

- Live Supabase RLS proof requires a running Supabase instance; the
  API-layer IDOR tests cover the application boundary, and the
  migration tests cover the RLS policy structure.
- Docker builds cannot be verified locally when the Docker daemon is
  unavailable; the CI pipeline covers them.
- Frontend E2E (browser) is not configured in this environment; the
  CI pipeline covers browser validation.

## Related documents

- [limitations.md](limitations.md)
- [system.md](system.md)