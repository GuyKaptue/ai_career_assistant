PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
MYPY ?= $(PYTHON) -m mypy
BANDIT ?= $(PYTHON) -m bandit
PIP_AUDIT ?= $(PYTHON) -m pip_audit
UVICORN ?= $(PYTHON) -m uvicorn
SUPABASE ?= supabase

screenshots:
	cd frontend && node scripts/screenshots.mjs: install install-dev format format-check lint lint-fix typecheck test test-unit test-integration test-api test-security test-e2e coverage security licenses validate backend-test frontend-build frontend-dev app dev docker-build docker-up docker-down docker-logs ollama-up ollama-pull ollama-logs ollama-gpu-up verify check-env db-migrate db-reset db-status clean backend frontend

check-env:
	cd backend && PYTHONPATH=. $(PYTHON) -c "from app.core.config import validate_runtime_environment; validate_runtime_environment(); print('Environment configuration looks valid.')"

install:
	$(PIP) install -r backend/requirements.txt
	cd frontend && npm install

install-dev: install

format:
	$(PYTHON) -m ruff format backend

format-check:
	$(PYTHON) -m ruff format --check backend

lint:
	$(RUFF) check backend

lint-fix:
	$(RUFF) check --fix backend

typecheck:
	$(MYPY) backend/app

test: backend-test

backend-test:
	$(PYTEST) backend/tests -q

# Unit tests: domain logic, services, utilities (no external I/O).
test-unit:
	$(PYTEST) backend/tests/unit -q

# Integration tests: provider adapters, document generation, persistence.
test-integration:
	$(PYTEST) backend/tests/integration -q

# API tests: HTTP endpoints, auth, validation, error model, E2E journey.
test-api:
	$(PYTEST) backend/tests/api -q

# Security tests: token validation, cross-user isolation, observability.
test-security:
	$(PYTEST) backend/tests/security -q

# Contract tests: schema validation, migration structure, CI/deploy config.
test-contract:
	$(PYTEST) backend/tests/contract -q

test-e2e:
	@echo "E2E tests are not configured in this environment; use the project CI pipeline for browser validation."

coverage:
	$(PYTEST) backend/tests --cov=backend/app --cov-report=term-missing -q

security:
	$(BANDIT) -r backend/app -q
	$(PIP_AUDIT) -r backend/requirements.txt --format columns

licenses:
	@echo "=== Python dependency licenses (backend) ==="
	cd backend && python3 -m piplicenses --format=plain 2>/dev/null | grep -iE "(fastapi|starlette|uvicorn|python-dotenv|httpx|PyJWT|python-multipart|huggingface_hub|pydantic|pypdf|reportlab|python-docx|PyYAML|tokenizers|Pillow|pytest|pytest-cov|ruff|mypy|bandit|cryptography|pip-audit|types-PyYAML)" | grep -vE "^(Name| *$$)" || echo "(pip-licenses not installed: pip install pip-licenses)"
	@echo ""
	@echo "=== Frontend dependency licenses ==="
	cd frontend && npm ls --all --depth=0 2>/dev/null || echo "(npm not available)"
	@echo ""
	@echo "=== Copyleft check (direct deps only; must be empty) ==="
	cd backend && python3 -m piplicenses --format=plain 2>/dev/null | grep -iE "(fastapi|starlette|uvicorn|python-dotenv|httpx|PyJWT|python-multipart|huggingface_hub|pydantic|pypdf|reportlab|python-docx|PyYAML|tokenizers|Pillow|pytest|pytest-cov|ruff|mypy|bandit|cryptography|pip-audit|types-PyYAML)" | grep -iE "(gpl|lgpl|agpl|affero|mpl|cddl)" && echo "WARNING: copyleft dependency found!" || echo "No copyleft dependencies detected."

validate: format-check lint typecheck test coverage security

frontend-build:
	cd frontend && npm run build

frontend-dev:
	cd frontend && npm run dev -- --host 0.0.0.0 --port 5173

app:
	cd backend && $(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

run-tests:
	$(MAKE) backend-test

verify: lint backend-test frontend-build

dev:
	docker compose up --build

docker-build:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# --- Ollama local inference (RD-01) ---
# The stack runs Ollama as a first-class service: the backend tries it before
# Hugging Face, and the breaker + template fallback keep the app working when it
# is down. These three targets never swallow an error.

# Start ollama and wait until it reports healthy. Fails (non-zero) if it does
# not become healthy, so a broken service is never reported as "up".
ollama-up:
	docker compose up -d --wait ollama

# Pull the configured model into the shared volume (one-shot, exit code visible).
# A failed pull fails this target: `--exit-code-from` returns the one-shot's
# status, so the pull cannot silently succeed.
# Inspect the one-shot afterwards with: docker compose ps -a
ollama-pull:
	@echo "Pulling $${OLLAMA_MODEL:-llama3.2:3b} into the ollama volume (one-shot; exit code is propagated)."
	docker compose up --exit-code-from ollama-pull ollama-pull
	@echo "One-shot finished — see 'docker compose ps -a' for its recorded exit code."

# Follow ollama logs (model pulls, generation, breaker decisions).
ollama-logs:
	docker compose logs -f ollama

# Opt-in GPU acceleration (requires the NVIDIA container toolkit on the host).
ollama-gpu-up:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --wait ollama

# Database management (Supabase CLI).
db-migrate:
	$(SUPABASE) db push

db-reset:
	$(SUPABASE) db reset

db-status:
	$(SUPABASE) db status

# Cleanup generated artifacts.
clean:
	rm -rf backend/.pytest_cache
	rm -rf backend/.mypy_cache
	rm -rf backend/.ruff_cache
	rm -rf frontend/node_modules
	rm -rf frontend/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Convenience aliases.
backend: app
frontend: frontend-dev
