# Development setup

The project is designed to be straightforward to run locally on a development machine. The fastest path is to install the backend dependencies, start the API, and then run the frontend in its own dev server. A Docker Compose setup is also included for teams that prefer a single environment, but it requires Docker Desktop or an equivalent local Docker engine.

## 1. Environment file

Create a project `.env` file from the repository example:

```bash
cp .env.example .env
```

The backend expects values such as `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_DB_URL`, and `HF_TOKEN`. If your database password contains a character like `@`, URL-encode it in the Postgres URL.

Example:

```env
SUPABASE_DB_URL=postgresql://postgres:your%40password@db.your-project.supabase.co:5432/postgres
```

## 2. Backend

Open a terminal in the project root and install the Python requirements:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then start the FastAPI service from the backend directory:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

This is the working local startup pattern because the application imports modules using `from app...` and therefore needs the backend directory on the Python import path.

## 3. Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## 4. Docker

The repository also includes a Compose configuration for local orchestration:

```bash
docker compose up --build
```

If Docker Desktop or the local Docker engine is not available, use the backend and frontend local startup commands above instead. The app is still fully runnable without Docker in a local development environment.
