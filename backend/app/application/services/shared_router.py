"""Shared Hugging Face router with dynamic model discovery (AI-01, AI-02, AI-10).

This module provides a singleton router instance that is initialized at startup
with dynamic model discovery from the Hugging Face Hub. It also adds structured
logging for routing decisions (AI-10).
"""

from __future__ import annotations

import logging

from app.application.services.ai_discovery import ModelDiscoveryService
from app.application.services.ai_model_router import HuggingFaceInferenceAdapter, HuggingFaceModelRouter
from app.application.services.ai_registry import ModelApprovalPolicy
from app.application.services.ai_tokenizer import TokenizerService
from app.application.services.model_overrides import apply_overrides
from app.application.services.ollama_first_adapter import (
    GenerationAdapter,
    OllamaFirstAdapter,
    build_generation_adapter,
)
from app.application.services.ollama_status_probe import reset_probe_cache
from app.core.config import settings

logger = logging.getLogger(__name__)

_router: HuggingFaceModelRouter | None = None
_adapter: GenerationAdapter | None = None


def get_router() -> HuggingFaceModelRouter:
    """Get the shared router instance, initializing it on first access."""
    global _router
    if _router is None:
        _router = _create_router_with_discovery()
    return _router


def get_adapter() -> GenerationAdapter:
    """Get the shared generation adapter (Ollama-first, HF fallback)."""
    global _adapter
    if _adapter is None:
        _adapter = build_generation_adapter(HuggingFaceInferenceAdapter(router=get_router()))
    return _adapter


def set_adapter_for_testing(adapter: GenerationAdapter | None) -> None:
    """Override the shared adapter for testing purposes."""
    global _adapter
    _adapter = adapter


def set_router_for_testing(router: HuggingFaceModelRouter | None) -> None:
    """Override the shared router for testing purposes."""
    global _router
    _router = router


def reset_shared_state() -> None:
    """Reset shared state for testing (closes the Ollama HTTP client).

    Order matters: the adapter is captured and the module globals are cleared
    first (so any concurrent caller sees a clean slate and rebuilds from
    scratch), then the live adapter is closed, and finally the informational
    status-probe cache is dropped so no stale Ollama state survives.
    """
    global _router, _adapter
    adapter = _adapter
    _router = None
    _adapter = None
    if isinstance(adapter, OllamaFirstAdapter):
        try:
            adapter.close()
        except Exception:  # noqa: BLE001 - a teardown must never mask the caller
            logger.warning("ai.ollama close failed during reset_shared_state", exc_info=True)
    # Drop the cached Ollama status (and any probe bound to the old adapter).
    reset_probe_cache()


def _create_router_with_discovery() -> HuggingFaceModelRouter:
    """Create router and run dynamic model discovery if enabled (§5)."""
    tokenizer = TokenizerService()
    policy = ModelApprovalPolicy.from_settings()
    router = HuggingFaceModelRouter(tokenizer=tokenizer, policy=policy)

    if settings.ai_enable_discovery and settings.huggingface_token:
        try:
            logger.info(
                "ai.discovery starting query=%s limit=%s max_params=%s",
                settings.ai_discovery_query,
                settings.ai_discovery_limit,
                settings.ai_max_parameters,
            )
            discovery = ModelDiscoveryService(max_parameters=settings.ai_max_parameters)
            # Discover for the primary tasks
            for task in ("cv_generation", "cover_letter_generation", "resume_analysis"):
                report = discovery.discover(
                    task=task,
                    query=settings.ai_discovery_query,
                    languages=("en", "de", "fr"),
                    limit=settings.ai_discovery_limit,
                )
                if report.approved:
                    router.add_models(report.approved)
                    logger.info(
                        "ai.discovery task=%s discovered=%d approved=%d added",
                        task,
                        report.total_discovered,
                        len(report.approved),
                    )
                else:
                    logger.warning(
                        "ai.discovery task=%s discovered=%d approved=0",
                        task,
                        report.total_discovered,
                    )
        except Exception as exc:  # pragma: no cover - network errors
            logger.warning("ai.discovery failed: %s", exc)
    elif not settings.huggingface_token:
        logger.info("ai.discovery skipped: HF_TOKEN not configured")

    apply_overrides(router)  # operator choices from `models enable/disable`
    return router


def log_routing_decision(
    task: str,
    model_id: str,
    fallback_reason: str | None,
    fallback_chain: list[str],
    routing_score: float | None,
    required_context: int,
    success: bool,
) -> None:
    """Log a structured routing decision for observability (AI-10)."""
    logger.info(
        "ai.routing_decision task=%s model=%s fallback_reason=%s fallback_chain=%s "
        "routing_score=%s required_context=%s success=%s",
        task,
        model_id,
        fallback_reason or "none",
        ",".join(fallback_chain) if fallback_chain else "none",
        routing_score,
        required_context,
        success,
    )
