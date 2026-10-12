#!/usr/bin/env bash
#
# Apply every pending migration in supabase/migrations/ to the database named
# by SUPABASE_DB_URL in .env.
#
# The migrations are additive and idempotent (create if not exists /
# on conflict do nothing), so running this repeatedly is safe. It never
# drops a table.
#
# Prerequisites
#   * psql, or the Supabase CLI (supabase db push)
#   * SUPABASE_DB_URL in .env  (postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres)
#
# Usage
#   ./scripts/apply_db_migrations.sh            # normal
#   ./scripts/apply_db_migrations.sh --check    # report only, change nothing
#
# If authentication fails, the password in .env no longer matches the project:
# get the current one from the Supabase dashboard (Project Settings -> Database
# -> Connection string / Reset database password) and update SUPABASE_DB_URL
# (URL-encode any @ as %40) and SUPABASE_PASSWORD.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATIONS="$ROOT/supabase/migrations"
MODE="${1:-apply}"

# Load the plain keys from .env without exporting anything we do not need.
eval "$(python3 - <<'PY'
from dotenv import dotenv_values
import shlex, pathlib
env = pathlib.Path('.') / '.env'
values = dotenv_values(env) if env.exists() else {}
for key in ('SUPABASE_DB_URL', 'SUPABASE_PASSWORD'):
    if values.get(key):
        print(f'{key}={shlex.quote(values[key])}')
PY
)"

if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
  echo "SUPABASE_DB_URL is not set in .env" >&2
  exit 1
fi

echo "Migrations to apply (in order):"
for f in "$MIGRATIONS"/*.sql; do echo "  $(basename "$f")"; done
echo

if [[ "$MODE" == "--check" ]]; then
  echo "--check: no changes made."
  exit 0
fi

if command -v psql >/dev/null 2>&1; then
  echo "Using psql"
  for f in "$MIGRATIONS"/*.sql; do
    printf '  applying %s ... ' "$(basename "$f")"
    if psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -q -f "$f" >/dev/null 2>&1; then
      echo OK
    else
      echo FAILED
      psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -q -f "$f" || true
      exit 1
    fi
  done
  echo
  echo "Done."
else
  echo "psql not found; falling back to the Supabase CLI"
  WORKDIR="$(mktemp -d)"
  mkdir -p "$WORKDIR/migrations"
  cp "$MIGRATIONS"/*.sql "$WORKDIR/migrations/"
  cat >"$WORKDIR/config.toml" <<'TOML'
project_id = "your-project-ref"

[db]
major_version = 15
TOML
  supabase db push --db-url "$SUPABASE_DB_URL" --workdir "$WORKDIR"
  rm -rf "$WORKDIR"
fi
