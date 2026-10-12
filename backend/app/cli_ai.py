"""``models`` and ``ai`` command groups of the CLI.

Offline by default: ``list``, ``validate``, ``health``, ``benchmark`` and
``ai test`` use only the local registry and routing logic. Commands that call
Hugging Face say so (``discover``, ``refresh``, ``--live``).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from typing import Any

from app.application.services import model_overrides
from app.application.services.ai_discovery import ModelDiscoveryService
from app.application.services.ai_model_router import (
    HuggingFaceInferenceAdapter,
    HuggingFaceModelRouter,
    classify_failure,
)
from app.application.services.ai_registry import AI_TASKS, ModelApprovalPolicy, ModelMetadata, normalize_task
from app.application.services.ai_tokenizer import TokenizerService
from app.core.config import settings

DEFAULT_REFRESH_TASKS = ("cv_generation", "cover_letter_generation", "resume_analysis")
BENCHMARK_BUDGETS = (1024, 4096, 16384, 65536)
PROBE_PROMPT = "Reply with the single word: ok"


def _out(message: str = "") -> None:
    sys.stdout.write(message + "\n")


def _err(message: str) -> None:
    sys.stderr.write(message + "\n")


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = (
        [max(len(str(cell)) for cell in column) for column in zip(headers, *rows, strict=False)]
        if rows
        else [len(h) for h in headers]
    )
    line = lambda cells: "  ".join(str(cell).ljust(width) for cell, width in zip(cells, widths, strict=False)).rstrip()  # noqa: E731
    return "\n".join([line(headers), line(["-" * width for width in widths]), *(line(row) for row in rows)])


def build_router() -> HuggingFaceInferenceAdapter:
    """Local registry + operator overrides; never touches the network."""
    base = HuggingFaceModelRouter(tokenizer=TokenizerService(), policy=ModelApprovalPolicy.from_settings())
    model_overrides.apply_overrides(base)
    return HuggingFaceInferenceAdapter(router=base)


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def register(subparsers: Any) -> None:
    models = subparsers.add_parser("models", help="Inspect and manage the AI model registry")
    sub = models.add_subparsers(dest="models_command", required=True)

    listing = sub.add_parser("list", help="List registered models")
    listing.add_argument("--task", help="Only models that support this task")
    listing.add_argument("--discovered", action="store_true", help="Also show models cached by `models refresh`")
    listing.add_argument("--json", action="store_true", dest="as_json")

    for name, help_text in (
        ("discover", "Search the Hugging Face Hub for candidate models (dry run, network)"),
        ("refresh", "Discover models and save approved candidates to the local cache (network)"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--task", action="append", help="Task to discover for (repeatable)")
        command.add_argument("--query", default=None, help="Hub search text (default: AI_DISCOVERY_QUERY)")
        command.add_argument(
            "--limit", type=int, default=None, help="Max models per task (default: AI_DISCOVERY_LIMIT)"
        )
        command.add_argument("--json", action="store_true", dest="as_json")

    validate = sub.add_parser("validate", help="Check registry consistency and task coverage")
    validate.add_argument("--json", action="store_true", dest="as_json")

    health = sub.add_parser("health", help="Show model health and circuit-breaker state")
    health.add_argument("--live", action="store_true", help="Send a tiny probe prompt to every enabled model (network)")
    health.add_argument("--json", action="store_true", dest="as_json")

    bench = sub.add_parser("benchmark", help="Routing benchmark (offline) or latency benchmark (--live)")
    bench.add_argument("--task", action="append", help="Task to benchmark (default: all)")
    bench.add_argument("--live", action="store_true", help="Measure real latency of --model (network)")
    bench.add_argument("--model", help="Model id for --live")
    bench.add_argument("--runs", type=int, default=3, help="Calls per model for --live")
    bench.add_argument("--json", action="store_true", dest="as_json")

    for name, help_text in (("enable", "Enable a model"), ("disable", "Disable a model (it is never routed)")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("model_id")

    ai = subparsers.add_parser("ai", help="AI routing / inference diagnostics")
    ai_sub = ai.add_subparsers(dest="ai_command", required=True)
    test = ai_sub.add_parser("test", help="Show the routing decision for a task; --live runs the full chain")
    test.add_argument("--task", default="career_advice")
    test.add_argument("--prompt", default="Give one short tip for a CV summary.")
    test.add_argument("--language", action="append", help="Preferred language (repeatable)")
    test.add_argument("--budget", type=int, default=4096, help="Token budget for the routing decision")
    test.add_argument("--model", help="Prefer this model id (--live)")
    test.add_argument("--live", action="store_true", help="Send the prompt to Hugging Face (network)")
    test.add_argument("--json", action="store_true", dest="as_json")


def run(args: argparse.Namespace) -> int | None:
    if args.command == "models":
        handler = {
            "list": _models_list,
            "discover": lambda a: _models_discover(a, save=False),
            "refresh": lambda a: _models_discover(a, save=True),
            "validate": _models_validate,
            "health": _models_health,
            "benchmark": _models_benchmark,
            "enable": lambda a: _models_toggle(a, enable=True),
            "disable": lambda a: _models_toggle(a, enable=False),
        }[args.models_command]
        return handler(args)  # type: ignore[no-any-return]
    if args.command == "ai" and args.ai_command == "test":
        return _ai_test(args)
    return None


# --------------------------------------------------------------------------- #
# models list / validate / health
# --------------------------------------------------------------------------- #
def _model_row(model: ModelMetadata, breaker_state: str | None = None) -> dict[str, Any]:
    return {
        "model_id": model.model_id,
        "enabled": model.enabled,
        "health": model.health_status,
        "context_window": model.context_window,
        "license": model.license,
        "policy": model.license_policy_status,
        "languages": list(model.supported_languages),
        "tasks": list(model.task_capabilities) or ["(any)"],
        **({"circuit": breaker_state} if breaker_state else {}),
    }


def _models_list(args: argparse.Namespace) -> int:
    router = build_router()
    models = [m for m in router.models if not args.task or m.supports_task(args.task)]
    rows = [_model_row(m) for m in models]
    cached = []
    if args.discovered:
        known = {m.model_id for m in router.models}
        cached = [
            _model_row(m) | {"cached_only": True} for m in model_overrides.load_discovered() if m.model_id not in known
        ]
    if args.as_json:
        _out(json.dumps({"models": rows, "discovered": cached}, indent=2))
        return 0
    table = [
        [
            r["model_id"],
            "yes" if r["enabled"] else "NO",
            r["health"],
            str(r["context_window"] or "?"),
            str(r["policy"]),
            ",".join(r["languages"]),
        ]
        for r in rows
    ]
    _out(_table(table, ["MODEL", "ENABLED", "HEALTH", "CONTEXT", "LICENSE POLICY", "LANGUAGES"]))
    if cached:
        _out("\nCached by `models refresh` (not routable until `models enable <id>`):")
        _out("\n".join(f"  {r['model_id']}  policy={r['policy']}" for r in cached))
    return 0


def _models_validate(args: argparse.Namespace) -> int:
    router = build_router()
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for model in router.models:
        if not model.model_id.strip():
            errors.append("a model has an empty id")
            continue
        if model.model_id in seen:
            errors.append(f"{model.model_id}: duplicate registration")
        seen.add(model.model_id)
        if "/" not in model.model_id:
            warnings.append(f"{model.model_id}: id is not in 'org/name' form")
        if model.max_output_tokens <= 0:
            errors.append(f"{model.model_id}: max_output_tokens must be positive")
        if model.context_window is None:
            warnings.append(f"{model.model_id}: context window unknown (such models are not routed for long inputs)")
        elif model.context_window <= model.max_output_tokens:
            errors.append(
                f"{model.model_id}: context window {model.context_window} <= max output {model.max_output_tokens}"
            )
        if model.license_policy_status == "BLOCKED":
            warnings.append(f"{model.model_id}: license blocked by policy — never routed")
        elif model.license_policy_status == "REQUIRES_REVIEW":
            warnings.append(f"{model.model_id}: license requires review — not routed until approved")
    uncovered = []
    for task in AI_TASKS:
        try:
            router.rank_candidates(task, token_budget=1024)
        except Exception as exc:  # noqa: BLE001 - any routing failure means the task is not covered
            uncovered.append(task)
            errors.append(f"task '{task}': no eligible model ({str(exc)[:80]})")
    report = {
        "ok": not errors,
        "models": len(router.models),
        "tasks_covered": len(AI_TASKS) - len(uncovered),
        "tasks_total": len(AI_TASKS),
        "errors": errors,
        "warnings": warnings,
    }
    if args.as_json:
        _out(json.dumps(report, indent=2))
    else:
        _out(f"Models: {report['models']}   Tasks covered: {report['tasks_covered']}/{report['tasks_total']}")
        for item in errors:
            _out(f"  ERROR   {item}")
        for item in warnings:
            _out(f"  warning {item}")
        _out("Registry is valid." if not errors else f"{len(errors)} error(s) found.")
    return 0 if not errors else 1


def _probe(router: HuggingFaceInferenceAdapter, model: ModelMetadata) -> dict[str, Any]:
    started = time.monotonic()
    try:
        router._call_model(model, PROBE_PROMPT, 8)  # noqa: SLF001 - diagnostic probe of one specific model
    except Exception as exc:  # noqa: BLE001 - classified below, never raised to the operator as a traceback
        return {"ok": False, "failure": classify_failure(exc), "latency_ms": int((time.monotonic() - started) * 1000)}
    return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}


def _models_health(args: argparse.Namespace) -> int:
    router = build_router()
    if args.live and not settings.huggingface_token:
        _err("--live needs HF_TOKEN.")
        return 1
    rows = []
    for model in router.models:
        row = _model_row(model, router._circuit_breaker(model).state)  # noqa: SLF001
        if args.live and model.enabled:
            row["probe"] = _probe(router, model)
        rows.append(row)
    if args.as_json:
        _out(json.dumps({"models": rows, "live": args.live}, indent=2))
        return 0
    table = []
    for r in rows:
        probe = r.get("probe")
        table.append(
            [r["model_id"], "yes" if r["enabled"] else "NO", r["health"], r["circuit"]]
            + ([("ok" if probe["ok"] else probe["failure"]) + f" {probe['latency_ms']}ms"] if probe else [])
        )
    _out(_table(table, ["MODEL", "ENABLED", "HEALTH", "CIRCUIT"] + (["PROBE"] if args.live else [])))
    if not args.live:
        _out("\n(state of this process only; use --live to probe Hugging Face)")
    return 0


# --------------------------------------------------------------------------- #
# discover / refresh
# --------------------------------------------------------------------------- #
def _models_discover(args: argparse.Namespace, *, save: bool) -> int:
    if not settings.huggingface_token:
        _err("Discovery needs HF_TOKEN (it queries the Hugging Face Hub).")
        return 1
    tasks = [normalize_task(t) for t in (args.task or DEFAULT_REFRESH_TASKS)]
    unknown = [t for t in tasks if t not in AI_TASKS]
    if unknown:
        _err(f"Unknown task(s): {', '.join(unknown)}. Known: {', '.join(AI_TASKS)}")
        return 2
    service = ModelDiscoveryService(max_parameters=settings.ai_max_parameters)
    approved: dict[str, ModelMetadata] = {}
    summary: list[dict[str, Any]] = []
    for task in tasks:
        try:
            report = service.discover(
                task=task,
                query=args.query or settings.ai_discovery_query,
                languages=("en", "de", "fr"),
                limit=args.limit or settings.ai_discovery_limit,
            )
        except Exception as exc:  # noqa: BLE001 - network/Hub errors become a clear operator message
            _err(f"Discovery failed for '{task}': {type(exc).__name__}: {str(exc)[:120]}")
            return 1
        for model in report.approved:
            approved.setdefault(model.model_id, model)
        summary.append(
            {
                "task": task,
                "discovered": report.total_discovered,
                "compatible": report.compatible,
                "license_approved": report.license_approved,
                "task_matched": report.task_matched,
                "language_matched": report.language_matched,
                "resource_passed": report.resource_passed,
                "approved": [m.model_id for m in report.approved],
                "rejected": [{"model_id": mid, "reason": reason} for mid, reason in report.rejected[:20]],
            }
        )
    if save:
        model_overrides.save_discovered(list(approved.values()))
    if args.as_json:
        _out(
            json.dumps(
                {"saved": save, "tasks": summary, "cache": str(model_overrides.discovered_path()) if save else None},
                indent=2,
            )
        )
        return 0
    for item in summary:
        _out(
            f"{item['task']}: discovered={item['discovered']} compatible={item['compatible']} "
            f"licensed={item['license_approved']} task={item['task_matched']} "
            f"language={item['language_matched']} resources={item['resource_passed']} "
            f"approved={len(item['approved'])}"
        )
        for model_id in item["approved"]:
            _out(f"    + {model_id}")
    if save:
        _out(f"\nSaved {len(approved)} candidate(s) to {model_overrides.discovered_path()}")
        _out("They are NOT routable yet — enable one explicitly: `models enable <model_id>`.")
    else:
        _out("\nDry run — nothing saved. Use `models refresh` to cache the candidates.")
    return 0


# --------------------------------------------------------------------------- #
# enable / disable
# --------------------------------------------------------------------------- #
def _models_toggle(args: argparse.Namespace, *, enable: bool) -> int:
    router = build_router()
    registered = {m.model_id for m in router.models}
    cached = {m.model_id for m in model_overrides.load_discovered()}
    if args.model_id not in registered | cached:
        _err(f"Unknown model '{args.model_id}'. Run `models list --discovered` to see what is available.")
        return 2
    if enable:
        if args.model_id in registered:
            model_overrides.set_disabled(args.model_id, False)
        else:
            model_overrides.enable_discovered(args.model_id)
    else:
        model_overrides.set_disabled(args.model_id, True)
    _out(f"{'Enabled' if enable else 'Disabled'} {args.model_id} (saved to {model_overrides.overrides_path()}).")
    if enable and args.model_id not in registered:
        policy = next(m for m in model_overrides.load_discovered() if m.model_id == args.model_id)
        status = ModelApprovalPolicy.from_settings().evaluate(policy)
        if status != "APPROVED":
            _out(f"Note: license policy status is {status}; the router will not use it until that is resolved.")
    _out("Restart the API server for the change to take effect.")
    return 0


# --------------------------------------------------------------------------- #
# benchmark
# --------------------------------------------------------------------------- #
def _routing_benchmark(router: HuggingFaceModelRouter, tasks: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in tasks:
        for budget in BENCHMARK_BUDGETS:
            try:
                decision = router.route(task, token_budget=budget, preferred_languages=("en",))
            except Exception as exc:  # noqa: BLE001 - "no model fits" is a valid benchmark outcome
                rows.append({"task": task, "budget": budget, "model_id": None, "note": str(exc)[:80]})
                continue
            rows.append(
                {
                    "task": task,
                    "budget": budget,
                    "model_id": decision["model_id"],
                    "score": round(decision["routing_score"], 3),
                    "eligible": len(decision["eligible"]),
                    "eliminated": len(decision["eliminated"]),
                }
            )
    return rows


def _models_benchmark(args: argparse.Namespace) -> int:
    router = build_router()
    if args.live:
        if not settings.huggingface_token:
            _err("--live needs HF_TOKEN.")
            return 1
        model = next((m for m in router.models if m.model_id == args.model), None)
        if model is None:
            _err("--live needs --model <registered model id>.")
            return 2
        timings: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for _ in range(max(1, args.runs)):
            result = _probe(router, model)
            (timings if result["ok"] else failures).append(result)
        report = {
            "model_id": model.model_id,
            "runs": args.runs,
            "ok": len(timings),
            "failed": [f["failure"] for f in failures],
            "median_ms": int(statistics.median(t["latency_ms"] for t in timings)) if timings else None,
            "min_ms": min((t["latency_ms"] for t in timings), default=None),
            "max_ms": max((t["latency_ms"] for t in timings), default=None),
        }
        _out(json.dumps(report, indent=2) if args.as_json else "\n".join(f"{k}: {v}" for k, v in report.items()))
        return 0 if timings else 1
    tasks = [normalize_task(t) for t in (args.task or AI_TASKS)]
    unknown = [t for t in tasks if t not in AI_TASKS]
    if unknown:
        _err(f"Unknown task(s): {', '.join(unknown)}")
        return 2
    rows = _routing_benchmark(router, tasks)
    if args.as_json:
        _out(json.dumps({"mode": "routing", "rows": rows}, indent=2))
        return 0
    _out("Routing benchmark (offline: which model would be chosen for each task and context budget)\n")
    _out(
        _table(
            [
                [
                    r["task"],
                    str(r["budget"]),
                    r["model_id"] or "— none —",
                    str(r.get("score", "")),
                    f"{r.get('eligible', '')}/{r.get('eliminated', '')}",
                ]
                for r in rows
            ],
            ["TASK", "BUDGET", "SELECTED", "SCORE", "ELIGIBLE/ELIMINATED"],
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# ai test
# --------------------------------------------------------------------------- #
def _ai_test(args: argparse.Namespace) -> int:
    task = normalize_task(args.task)
    if task not in AI_TASKS:
        _err(f"Unknown task '{task}'. Known: {', '.join(AI_TASKS)}")
        return 2
    router = build_router()
    languages = tuple(args.language or ())
    try:
        decision = router.route(task, token_budget=args.budget, preferred_languages=languages)
    except Exception as exc:  # noqa: BLE001 - "no eligible model" is a normal diagnostic result
        _err(f"Routing failed: {str(exc)[:200]}")
        return 1
    result: dict[str, Any] = {"mode": "live" if args.live else "dry-run", "routing": decision}
    if args.live:
        if not settings.huggingface_token:
            _err("--live needs HF_TOKEN.")
            return 1
        _err("Note: --live sends the prompt to the Hugging Face Inference API.")
        started = time.monotonic()
        try:
            answer = router.generate_with_fallback(
                task,
                args.prompt,
                token_budget=args.budget,
                preferred_languages=languages,
                max_retries=1,
                base_backoff_seconds=0.5,
                preferred_model_id=args.model,
            )
        except Exception as exc:  # noqa: BLE001 - provider errors are reported, not raised
            result["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            _out(json.dumps(result, indent=2) if args.as_json else f"Live call failed: {result['error']}")
            return 1
        result["live"] = {
            "model_id": answer["model_id"],
            "fallback_chain": answer.get("fallback_chain"),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "output_preview": str(answer.get("content", ""))[:300],
        }
    if args.as_json:
        _out(json.dumps(result, indent=2, default=str))
        return 0
    _out(f"Task:      {task}  (budget {args.budget} tokens, languages: {', '.join(languages) or 'any'})")
    _out(f"Selected:  {decision['model_id']}  (score {decision['routing_score']:.3f})")
    _out(f"Eligible:  {', '.join(decision['eligible'])}")
    for item in decision["eliminated"]:
        _out(f"Eliminated: {item['model_id']} — {item['reason']}")
    _out(f"Why:       {decision['explanation']}")
    if args.live:
        live = result["live"]
        _out(f"\nLive:      {live['model_id']} in {live['latency_ms']} ms  chain={live['fallback_chain']}")
        _out(f"Output:    {live['output_preview']}")
    else:
        _out("\nDry run — no request was sent. Add --live to call Hugging Face.")
    return 0
