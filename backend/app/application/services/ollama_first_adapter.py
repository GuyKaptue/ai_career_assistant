"""Ollama-first generation adapter (RD-01).

Tries the local Ollama server first and falls back to the existing Hugging Face
adapter. If Hugging Face also fails its exception propagates unchanged, so the
template/deterministic fallbacks at the call sites keep working as before.

Privacy: prompts and completions are never logged or placed in metrics.
"""

from __future__ import annotations

import logging
import threading
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

_BREAKER_FAILURE_THRESHOLD: Final = 1
_BREAKER_RECOVERY_SECONDS: Final = 60.0
_BREAKER_FAILURE_CLASSES: Final = frozenset({MODEL_UNAVAILABLE})
_CIRCUIT_OPEN_REASON: Final = f"{MODEL_UNAVAILABLE}: ollama circuit breaker open"


def _context_length_from(body: object) -> int | None:
    """Pull the model's context length out of an ``/api/show`` response (F1).

    Accepts the documented shape (``model_info`` keys such as
    ``llama.context_length``) plus the older top-level ``context_length``.
    Any unexpected shape returns ``None`` so the caller keeps the configured
    value. Pure; never raises.
    """
    if not isinstance(body, dict):
        return None
    model_info = body.get("model_info")
    if isinstance(model_info, dict):
        for key, value in model_info.items():
            if (
                str(key).endswith("context_length")
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value > 0
            ):
                return value
    fallback = body.get("context_length")
    if isinstance(fallback, int) and not isinstance(fallback, bool) and fallback > 0:
        return fallback
    return None


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
        # F1: effective num_ctx, resolved once per adapter (configured window
        # clamped to the model's real context length) and reused afterwards.
        self._num_ctx_cache: int | None = None
        self._num_ctx_lock = threading.Lock()

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
                num_ctx=self._resolve_num_ctx(),
            )
        except AIProviderError as exc:
            failure_class = classify_failure(exc)
            # A connect timeout is a connect failure, not a hung read: treat it
            # as MODEL_UNAVAILABLE so the breaker trips and we stop retrying a
            # dead tunnel. A read timeout (hung generation) stays TIMEOUT and
            # does not trip the breaker.
            if failure_class == TIMEOUT and "connection timed out" in str(exc).lower():
                failure_class = MODEL_UNAVAILABLE
            if failure_class in _BREAKER_FAILURE_CLASSES:
                self._breaker.mark_failure(failure_class)
            else:
                self._breaker.mark_success()
            logger.info("ai.ollama.fallback model=%s reason=%s", self._ollama.model, exc)
            return None, str(exc)

        self._breaker.mark_success()
        return self._to_result(outcome, token_budget), None

    def _resolve_num_ctx(self) -> int:
        """Effective ``num_ctx`` for this adapter (finding F1).

        The configured ``settings.ollama_num_ctx`` clamped (cached after the first successful lookup)
        against the context length the running model actually reports via
        ``POST /api/show``. Later requests read the cache and never touch the
        network. Never raises: when the lookup fails, the configured value is
        used unchanged.
        """
        with self._num_ctx_lock:
            if self._num_ctx_cache is not None:
                return self._num_ctx_cache
            configured = settings.ollama_num_ctx
            reported = self._fetch_model_context_length()
            if reported is None:
                # Lookup failed: use the configured value now but do NOT cache
                # it, so the next request retries once Ollama is reachable.
                return configured
            self._num_ctx_cache = min(configured, reported)
            return self._num_ctx_cache

    def _fetch_model_context_length(self) -> int | None:
        """One-shot ``POST /api/show`` lookup of the model's context length (F1).

        Returns ``None`` whenever the answer is not usable — server down, stub
        client, non-200, unexpected body — so the configured value wins by
        default. Never raises; the response is reduced to an integer and
        nothing from it (nor the base URL) is ever logged.
        """
        try:
            response = self._ollama._client.post(
                f"{self._ollama._base_url}/api/show",
                # ``model`` is the documented key (Ollama >= 0.40); ``name`` is
                # the legacy alias, sent too so older servers answer as well.
                json={"model": self._ollama.model, "name": self._ollama.model},
                timeout=self._ollama._connect_timeout,
            )
        except Exception:
            # Deliberately no exception detail: it could carry the base URL.
            logger.debug("ai.ollama.context_length_lookup_failed")
            return None
        if response.status_code != 200:
            return None
        try:
            return _context_length_from(response.json())
        except ValueError:
            return None

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
