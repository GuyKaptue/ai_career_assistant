# Security overview

The project treats authentication, secret management, and configuration validation as first-class concerns. Secrets are never bundled into the repository, and environment variables are expected to carry the credentials for Supabase, AI providers, and other external services.

The backend validates Supabase bearer tokens with the project's dedicated `SUPABASE_JWT_SECRET`, verifies the HS256 signature, and requires both an expiry (`exp`) and user subject (`sub`). Supabase anon and service-role API keys are not signing secrets and must not be used for token verification. Missing verification configuration and invalid tokens fail explicitly.

The database layer is aligned with the Supabase pattern of Row-Level Security and user-scoped policies so data remains properly isolated. This is especially important in a product that stores CV drafts, job applications, and candidate details.

Local inference is credential-free by design: Ollama serves model weights from the `ollama_data` volume and reads no API key, so `USE_OLLAMA` and the `OLLAMA_*` variables add no secret to the configuration surface. Because Ollama has no authentication of its own, the compose stack binds it to `127.0.0.1` only and must never publish port `11434` on `0.0.0.0`; other containers reach it over the compose network, which that binding does not affect. Remote access requires a reverse proxy that terminates TLS and enforces authentication — see [`docs/deployment/ollama.md`](../deployment/ollama.md#security).

Profile, application-tracker, and saved-document endpoints require a verified bearer token. The authenticated user's `sub` claim is the only source of record ownership: request payloads cannot assign another owner, and records belonging to another user return `404` to avoid disclosing their existence. Health, template discovery, document generation, resume analysis, and job search remain public endpoints because they do not read or mutate saved user records.

Prompts and generated content never reach logs: routing decisions, model ids and latency are recorded, while the prompt, the completion and the provider base URL are excluded. That property is enforced by a static AST check in `backend/tests/contract/test_ollama_contracts.py` and by `caplog` assertions in the API-layer tests.
