"""Command-line interface for AI Career Assistant (CLI-01).

Commands:
    ai-career-assistant config validate   — validate runtime configuration
    ai-career-assistant db migrate        — apply Supabase migrations
    ai-career-assistant db status         — show migration status
    ai-career-assistant server            — start the API server
    ai-career-assistant jobs search       — search jobs via configured providers
    ai-career-assistant documents list    — list stored documents (requires auth)
    ai-career-assistant health            — check API health
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

import httpx

from app import cli_ai


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-career-assistant",
        description="AI Career Assistant CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # config validate
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("validate", help="Validate runtime configuration")

    # db migrate / status
    db_parser = subparsers.add_parser("db", help="Database management")
    db_sub = db_parser.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("migrate", help="Apply pending migrations")
    db_sub.add_parser("status", help="Show migration status")

    # server
    server_parser = subparsers.add_parser("server", help="Start the API server")
    # Security: bind to loopback by default (bandit B104). Pass
    # --host 0.0.0.0 explicitly when LAN access is intended.
    server_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    server_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    server_parser.add_argument("--reload", action="store_true", help="Enable reload")

    # jobs search
    jobs_parser = subparsers.add_parser("jobs", help="Job search")
    jobs_sub = jobs_parser.add_subparsers(dest="jobs_command", required=True)
    search_parser = jobs_sub.add_parser("search", help="Search jobs")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--location", default=None, help="Location filter")
    search_parser.add_argument("--limit", type=int, default=5, help="Max results")
    search_parser.add_argument("--page", type=int, default=1, help="Page number")
    search_parser.add_argument("--include-old", action="store_true", help="Disable the default 30-day recency filter")

    # documents list
    docs_parser = subparsers.add_parser("documents", help="Document management")
    docs_sub = docs_parser.add_subparsers(dest="docs_command", required=True)
    list_parser = docs_sub.add_parser("list", help="List documents")
    list_parser.add_argument("--token", required=True, help="Bearer JWT token")
    list_parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="API base URL")

    # health
    cli_ai.register(subparsers)

    health_parser = subparsers.add_parser("health", help="Health check")
    health_parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="API base URL")

    return parser


def _cmd_config_validate() -> int:
    from app.core.config import validate_runtime_environment

    try:
        validate_runtime_environment()
    except RuntimeError as exc:
        print(f"Configuration invalid: {exc}", file=sys.stderr)
        return 1
    print("Configuration is valid.")
    return 0


def _cmd_db_migrate() -> int:
    print("Database migrations are managed by the Supabase CLI.")
    print("Run: supabase db push")
    return 0


def _cmd_db_status() -> int:
    print("Database status is managed by the Supabase CLI.")
    print("Run: supabase db status")
    return 0


def _cmd_server(host: str, port: int, reload: bool) -> int:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
    )
    return 0


def _cmd_jobs_search(query: str, location: str | None, limit: int, page: int, include_old: bool = False) -> int:
    from app.domain.jobs.service import search_jobs

    try:
        result = search_jobs(query=query, location=location, limit=limit, page=page, include_old=include_old)
    except ValueError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


def _cmd_documents_list(token: str, api_url: str) -> int:
    try:
        response = httpx.get(
            f"{api_url}/api/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    if response.status_code >= 400:
        print(f"API error {response.status_code}: {response.text}", file=sys.stderr)
        return 1

    print(json.dumps(response.json(), indent=2))
    return 0


def _cmd_health(api_url: str) -> int:
    try:
        response = httpx.get(f"{api_url}/api/health", timeout=10.0)
    except httpx.HTTPError as exc:
        print(f"Health check failed: {exc}", file=sys.stderr)
        return 1

    if response.status_code >= 400:
        print(f"Unhealthy: HTTP {response.status_code}", file=sys.stderr)
        return 1

    print("Healthy.")
    print(json.dumps(response.json(), indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "config" and args.config_command == "validate":
        return _cmd_config_validate()

    if args.command == "db":
        if args.db_command == "migrate":
            return _cmd_db_migrate()
        if args.db_command == "status":
            return _cmd_db_status()

    if args.command == "server":
        return _cmd_server(args.host, args.port, args.reload)

    if args.command == "jobs" and args.jobs_command == "search":
        if args.include_old:
            return _cmd_jobs_search(args.query, args.location, args.limit, args.page, include_old=True)
        return _cmd_jobs_search(args.query, args.location, args.limit, args.page)

    if args.command == "documents" and args.docs_command == "list":
        return _cmd_documents_list(args.token, args.api_url)

    if args.command == "health":
        return _cmd_health(args.api_url)

    try:
        ai_result = cli_ai.run(args)
    except BrokenPipeError:  # e.g. `... | head`: the reader went away, which is not an error
        return 0
    if ai_result is not None:
        return ai_result

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
