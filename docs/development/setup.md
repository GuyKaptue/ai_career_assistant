# Development setup

The project is designed to be straightforward to run locally. The fastest path
is to install the backend dependencies, start the API, and then run the frontend
in its own dev server. A Docker Compose setup is also included for teams that
prefer a single environment, but it requires Docker Desktop or an equivalent
local Docker engine.

## 1. Get the code

```bash
git clone https://github.com/GuyKaptue/ai_career_assistant.git
cd ai_career_assistant
```

## 2. Environment file

Create a project `.env` file from the repository example:

```bash
cp .env.example .env
```

The backend expects values such as `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_DB_URL` and
`HF_TOKEN`. `.env.example` lists every variable the code reads, with a
placeholder or a safe default for each. If your database password contains a
character like `@`, URL-encode it in the Postgres URL.

Example:

```env
SUPABASE_DB_URL=postgresql://postgres:your%40password@db.your-project.supabase.co:5432/postgres
```

## 3. Database migrations

Two migration sets exist and **both are applied by hand** — nothing runs them
automatically:

| Folder | Files | What they create |
|---|---|---|
| `supabase/migrations/` | 9 files, timestamped `2026…` | the core schema: users, profiles, documents, applications, projects links, the knowledge base, the semantic embeddings, the chat tables and the `handle_new_user` trigger |
| `backend/migrations/` | `rd08_001` … `rd08_004` | the RD-08 additions: the profile-preference columns and the `projects` table, the analysis/job-search tables, the `template` / `job_description` embedding types, and `chat_sessions.job_context` |

Apply them in the Supabase SQL editor (or with `psql`) in filename order.
Each file is idempotent, so re-running one is safe. Two notes:

- `backend/migrations/rd08_001_user_core_and_templates.sql` assumes the
  existing `user_id` columns are `text`; adjust the type if yours are `uuid`.
- `rd08_004_chat_session_job_context.sql` adds the column that lets a chat
  thread remember the job it is about. **Without it the chat still works**,
  but the job is only remembered inside the running process.

```bash
make db-migrate   # `supabase db push` — applies supabase/migrations/ with the Supabase CLI
```

`make db-migrate` pushes the `supabase/migrations/` folder with the Supabase
CLI. The `backend/migrations/` files are not part of that push — apply them in
the SQL editor.

## 4. Backend

Open a terminal in the project root and install the Python requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Then start the FastAPI service from the backend directory:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

This is the working local startup pattern because the application imports
modules using `from app...` and therefore needs the backend directory on the
Python import path.

## 5. Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## 6. Docker

The repository also includes a Compose configuration for local orchestration:

```bash
docker compose up --build
```

`make docker-up`, `make docker-logs` and `make docker-down` wrap the same
commands. The stack brings up the backend, the frontend and the local
inference service; see [`docs/deployment/overview.md`](../deployment/overview.md)
for the services and their ports.

If Docker Desktop or the local Docker engine is not available, use the backend
and frontend local startup commands above instead. The app is still fully
runnable without Docker in a local development environment.

## 7. Make targets

`make help` is not defined; the targets are listed by `grep -E '^[a-z-]+:' Makefile`.
The ones used most often:

| Target | What it runs |
|---|---|
| `make install` / `make install-dev` | install the backend (and dev) requirements |
| `make format-check` / `make lint` / `make typecheck` | the backend formatting, lint and type checks |
| `make test` / `make backend-test` | the backend test suite |
| `make test-unit` / `test-integration` / `test-api` / `test-security` / `test-contract` | one test layer each |
| `make coverage` | the backend coverage report |
| `make security` | the security scans (bandit and the secret scan) |
| `make validate` | format-check, lint, typecheck, test, coverage and security |
| `make verify` | lint, the backend tests and the frontend build |
| `make frontend-build` / `make frontend-dev` | the frontend production build and dev server |
| `make app` | run the backend with reload from `backend/` |
| `make docker-up` / `docker-logs` / `docker-down` / `docker-build` | the Compose stack |
| `make ollama-up` / `ollama-pull` / `ollama-logs` / `ollama-gpu-up` | the local inference service |
| `make db-migrate` / `db-reset` / `db-status` | the local database helpers |
| `make licenses` | refresh the third-party license list |

Frontend commands are the npm scripts in `frontend/package.json`: `npm run
dev`, `npm run build`, `npm run preview`, `npm test`, `npm run test:watch`.

## 8. The model CLI

The backend ships a CLI for the model registry, the routing decisions and the
job search. Run it from `backend/` with the venv active:

```
python -m app.cli models list [--task T] [--discovered] [--json]
python -m app.cli models validate [--json]            # exit 1 on inconsistencies / uncovered tasks
python -m app.cli models health [--live]
python -m app.cli models benchmark [--task T] [--json]            # offline routing benchmark
python -m app.cli models benchmark --live --model ID --runs 3     # real latency (needs HF_TOKEN)
python -m app.cli models discover [--task T]          # dry run, needs HF_TOKEN
python -m app.cli models refresh  [--task T]          # caches approved candidates, needs HF_TOKEN
python -m app.cli models enable|disable MODEL_ID      # restart the API afterwards
python -m app.cli ai test [--task T] [--language de] [--live] [--model ID]
python -m app.cli jobs search "python" --include-old
```

Offline by default; only `discover`, `refresh` and `--live` use the network
(`--live` sends the prompt to Hugging Face and says so). Discovered models are
**never routable automatically**: they need an explicit `models enable`, and the
license policy still blocks `REQUIRES_REVIEW` / `BLOCKED` ones. Operator
choices live in `~/.config/ai-career-assistant/*.json`
(`AI_MODEL_OVERRIDES_FILE`, `AI_DISCOVERED_MODELS_FILE`).
