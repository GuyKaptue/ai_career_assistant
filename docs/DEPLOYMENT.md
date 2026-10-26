# Deployment (Render + Vercel + Supabase)

Free-tier deployment: frontend on Vercel, FastAPI backend on Render, data on Supabase.

## Deploy order

1. Rotate secrets (Supabase password/API keys that appeared in repo history).
2. Apply Supabase migrations `rd08_004` and `rd08_005` to your project.
3. Merge the deploy branch, then in Render choose **New → Blueprint** and connect the repo. Enter secret values in the dashboard.
4. Copy the Render URL into `frontend/vercel.json` and push.
5. Import the repo into Vercel (root directory `frontend`, build `npm run build`, output `dist`).
6. Add the Vercel URL in Supabase under **Auth → URL Configuration**.
7. Add a UptimeRobot monitor on `https://<render-url>/health`.
8. Smoke test: log in, send a chat message, generate a CV as PDF, run a job search.

## Environment variables (backend)

Set secrets in the Render dashboard (`sync: false` in `render.yaml`). Names only:

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | yes (for Supabase mode) | Leave empty for in-memory/local mode. |
| `SUPABASE_ANON_KEY` | optional | Frontend uses its own copy. |
| `SUPABASE_SERVICE_ROLE_KEY` | yes (for Supabase mode) | Server-side only. |
| `SUPABASE_JWT_SECRET` | yes (for auth) | HS256 secret. |
| `SUPABASE_DB_URL` / `DATABASE_URL` | optional | Not used by the app runtime (Supabase is reached over REST); kept for tooling/migrations. If a direct Postgres host fails from Render (it may be IPv6-only), use the Supabase pooler connection string. |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | optional | Job provider credentials. |
| `CORS_ORIGINS` | optional | Comma-separated allowlist; include the Vercel origin for direct calls. |
| `USE_OLLAMA` | no | Set `false` in production. |
| `HF_TOKEN` / `HUGGINGFACE_TOKEN` | optional | Leave unset for a public demo. |
| `LOG_LEVEL`, `RATE_LIMIT_PER_MINUTE`, `DEFAULT_TEMPLATE`, `APP_ENV`, … | optional | See `.env.example`. |

Frontend (Vercel): set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`; leave `VITE_API_URL` empty so requests use the `/api` proxy.

## Post-deploy smoke test

- `curl -i https://<render-url>/health` (GET and HEAD) → 200 `{"status":"ok"}`.
- `curl -i https://<render-url>/api/health` (GET and HEAD) → 200.
- `curl https://<render-url>/api/ready` → 200 when Supabase configured.
- Frontend loads at the Vercel URL; login, chat, CV PDF export, job search succeed.

## UptimeRobot

Monitor `https://<render-url>/health` with GET or HEAD every 5–10 minutes to reduce cold starts.

## Ollama (optional, remote via tunnel)

Production uses Hugging Face as the primary source. Ollama can run on the developer machine and be exposed through a tunnel so Render can reach it (`USE_OLLAMA=true`). If the tunnel is down, the chain falls through to Hugging Face and then the deterministic template.

- Connect timeout: 3 s. Generation/read timeout: 10 s (`OLLAMA_TIMEOUT_SECONDS`).
- `OLLAMA_BASE_URL` may be an `https://host` URL with no port and an optional path prefix; the client normalizes a trailing slash.
- Auth: set both `OLLAMA_AUTH_HEADER` and `OLLAMA_AUTH_TOKEN` to send that header; if either is unset, no auth header is sent. Never expose Ollama without auth.
- Tunnel runbook:
  1. Run `ollama serve` locally and `ollama pull <model>`; the Render `OLLAMA_MODEL` must match the pulled model.
  2. Run a Caddy reverse proxy on `:8080` that requires `X-Ollama-Token` (return 401 otherwise) and forwards to `127.0.0.1:11434`.
  3. Start the tunnel: `cloudflared tunnel --url http://localhost:8080` or `ngrok http 8080`.
  4. In Render set `OLLAMA_BASE_URL` to the tunnel URL, `OLLAMA_AUTH_TOKEN` to the secret, `USE_OLLAMA=true`. Set `USE_OLLAMA=false` when the tunnel is off.
- Security: never expose Ollama without auth; use a fine-grained Hugging Face token with inference permission only; rotate on exposure; never commit tokens or paste them into logs/issues.
- Render blueprint caveat: a dashboard override of `USE_OLLAMA` is lost on blueprint re-sync; the value in `render.yaml` is the default.

## AI readiness

`/api/ready` reports AI status under `checks.ai` (and top-level `ai`) without network I/O:

- `huggingface`: `configured` when `HF_TOKEN`/`HUGGINGFACE_TOKEN` is set, otherwise `missing`.
- `ollama`: `disabled` when `USE_OLLAMA` is false/unset; `enabled` when no connect failure has been recorded; `unreachable` when the circuit breaker is open.

An unreachable Ollama never causes 503. Missing required runtime keys (Supabase URL/service role/JWT) do.

## Known limits (Render free tier)

- Service sleeps after ~15 minutes of idle; first request after wake takes ~1 minute.
- 512 MB RAM, ephemeral filesystem, 750 free hours/month.
- One free web service is enough for this API.
- The `/api` proxy is untested for a cold Render start; if Vercel times out during wake-up, set `VITE_API_URL` to the Render URL and add CORS for the Vercel domain.

### Oracle VM option

An always-on Oracle Cloud free-tier VM can host Ollama instead of a laptop tunnel: install Ollama and the same Caddy auth proxy there, expose only the HTTPS endpoint, and set `OLLAMA_BASE_URL` to that endpoint. Apply the same `X-Ollama-Token` auth and firewall rules as the tunnel runbook above.