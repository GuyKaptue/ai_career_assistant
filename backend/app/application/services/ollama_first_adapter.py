"""Ollama-first generation adapter (RD-01).

Tries the local Ollama server first and falls back to the existing Hugging Face
adapter. If Hugging Face also fails its exception propagates unchanged, so the
template/deterministic fallbacks at the call sites keep working as before.

Privacy: prompts and completions are never logged or placed in metrics.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any, Final, Protocol

from app.application.services.ai_model_router import (
    MODEL_UNAVAILABLE,
    RATE_LIMITED,
    TIMEOUT,
    CircuitBreaker,
    classify_failure,
)
from app.application.services.ollama_status_probe import (
    DEFAULT_CACHE_TTL_SECONDS,
    OllamaStatusProbe,
    configure_probe,
    reset_probe_cache,
)
from app.core.config import settings
from app.core.errors import AIProviderError
from app.core.metrics import record_ollama_skip
from app.infrastructure.ai.ollama_adapter import (
    OllamaConfigError,
    OllamaInferenceAdapter,
    OllamaResult,
)

__all__ = [
    "OLLAMA_MODEL_ID_PREFIX",
    "GenerationAdapter",
    "OllamaFirstAdapter",
    "OllamaStatusProbe",
    "build_generation_adapter",
]
logger = logging.getLogger(__name__)

OLLAMA_MODEL_ID_PREFIX: Final = "ollama:"

_BREAKER_FAILURE_THRESHOLD: Final = 3
_BREAKER_RECOVERY_SECONDS: Final = 30.0
_BREAKER_FAILURE_CLASSES: Final = frozenset({MODEL_UNAVAILABLE, TIMEOUT, RATE_LIMITED})
_CIRCUIT_OPEN_REASON: Final = f"{MODEL_UNAVAILABLE}: ollama circuit breaker open"


class GenerationAdapter(Protocol):
    """Slice of the HF adapter API that application code depends on."""

    def generate_with_fallback(
        self,
        task: str,
        prompt: str,
        token_budget: int = 4096,
        preferred_languages: Sequence[str] = (),
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
        system_prompt: str = "",
        preferred_model_id: str | None = None,
    ) -> dict:
        """Same contract as HuggingFaceModelRouter.generate_with_fallback."""
        ...


class OllamaFirstAdapter:
    """Wraps a Hugging Face adapter and tries Ollama before it."""

    def __init__(
        self,
        hf_adapter: GenerationAdapter,
        ollama: OllamaInferenceAdapter,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._hf = hf_adapter
        self._ollama = ollama
        self._breaker = breaker or CircuitBreaker(
            failure_threshold=_BREAKER_FAILURE_THRESHOLD,
            reset_timeout=_BREAKER_RECOVERY_SECONDS,
        )

    @property
    def ollama_model_id(self) -> str:
        """Model id reported for completions served by Ollama."""
        return f"{OLLAMA_MODEL_ID_PREFIX}{self._ollama.model}"

    @property
    def ollama_adapter(self) -> OllamaInferenceAdapter:
        """The wrapped Ollama client.

        Read-only, zero behaviour change. Exposed so the status probe can reuse
        this adapter's pooled connection and configuration instead of building a
        second one, and so callers never reach into a private attribute.
        """
        return self._ollama

    @property
    def circuit_state(self) -> str | None:
        """Read-only circuit state, exposed for health/readiness probes.

        The probe reads this to fill the ``circuit`` field; this property never
        mutates breaker state.
        """
        if self._breaker is None:
            return None
        return self._breaker.state

    def generate_with_fallback(
        self,
        task: str,
        prompt: str,
        token_budget: int = 4096,
        preferred_languages: Sequence[str] = (),
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
        system_prompt: str = "",
        preferred_model_id: str | None = None,
    ) -> dict:
        """Generate with Ollama first, then Hugging Face; same contract as HF."""
        ollama_reason: str | None = None
        if preferred_model_id is None or preferred_model_id == self.ollama_model_id:
            result, ollama_reason = self._try_ollama(prompt, token_budget, system_prompt)
            if result is not None:
                return result

        hf_result = self._hf.generate_with_fallback(
            task,
            prompt,
            token_budget=token_budget,
            preferred_languages=preferred_languages,
            max_retries=max_retries,
            base_backoff_seconds=base_backoff_seconds,
            system_prompt=system_prompt,
            preferred_model_id=None if preferred_model_id == self.ollama_model_id else preferred_model_id,
        )
        if ollama_reason is None:
            return hf_result
        return self._annotate_fallback(hf_result, ollama_reason)

    def close(self) -> None:
        """Release the Ollama HTTP client."""
        self._ollama.close()

    def __getattr__(self, name: str) -> Any:
        """Forward everything else (route, select_model, ...) to the HF adapter."""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._hf, name)

    def _try_ollama(self, prompt: str, token_budget: int, system_prompt: str) -> tuple[dict | None, str | None]:
        """Return ``(result, None)`` on success or ``(None, reason)`` for HF takeover."""
        if not self._breaker.allow_request():
            logger.info("ai.ollama.skip reason=circuit_open model=%s", self._ollama.model)
            record_ollama_skip()
            return None, _CIRCUIT_OPEN_REASON

        messages: list[dict[str, str]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            outcome = self._ollama.chat(
                messages,
                max_new_tokens=token_budget,
                num_ctx=token_budget,
            )
        except AIProviderError as exc:
            failure_class = classify_failure(exc)
            if failure_class in _BREAKER_FAILURE_CLASSES:
                self._breaker.mark_failure(failure_class)
            else:
                self._breaker.mark_success()
            logger.info("ai.ollama.fallback model=%s reason=%s", self._ollama.model, exc)
            return None, str(exc)

        self._breaker.mark_success()
        return self._to_result(outcome, token_budget), None

    def _to_result(self, outcome: OllamaResult, token_budget: int) -> dict:
        model_id = f"{OLLAMA_MODEL_ID_PREFIX}{outcome.model}"
        return {
            "content": outcome.content,
            "model_id": model_id,
            "fallback_reason": None,
            "fallback_chain": [model_id],
            "routing_score": None,
            "required_context": outcome.prompt_tokens if outcome.prompt_tokens is not None else token_budget,
        }

    def _annotate_fallback(self, hf_result: dict, ollama_reason: str) -> dict:
        annotated = dict(hf_result)
        hf_reason = annotated.get("fallback_reason")
        annotated["fallback_reason"] = f"{ollama_reason}; {hf_reason}" if hf_reason else ollama_reason
        chain = annotated.get("fallback_chain")
        annotated["fallback_chain"] = (
            [self.ollama_model_id, *chain] if isinstance(chain, list) else [self.ollama_model_id]
        )
        return annotated


def build_generation_adapter(hf_adapter: GenerationAdapter) -> GenerationAdapter:
    """Return the adapter the application should use for text generation."""
    if not settings.use_ollama:
        # Drop any probe bound to a previous adapter so the next
        # get_ollama_status() reports a clean disabled state.
        reset_probe_cache()
        return hf_adapter
    try:
        ollama = OllamaInferenceAdapter()
    except OllamaConfigError as exc:
        logger.error("ai.ollama.disabled invalid configuration: %s", exc)
        reset_probe_cache()
        return hf_adapter
    adapter = OllamaFirstAdapter(hf_adapter, ollama)
    # Bind the status probe to this adapter so the readiness endpoint and the CLI
    # read the same connection pool and the same breaker, instead of each
    # building (and closing) its own client per call.
    configure_probe(
        OllamaStatusProbe(
            settings_obj=settings,
            adapter_getter=lambda: adapter,
            circuit_state=lambda: adapter.circuit_state,
            cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
            clock=time.monotonic,
        )
    )
    return adapter
