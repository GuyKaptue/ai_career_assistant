"""Synchronous client for a local Ollama server (``/api/chat`` and ``/api/tags``).

Ollama needs no API key and has no quota. This adapter is deliberately
synchronous to match the rest of the inference stack (FastAPI runs sync
endpoints in a worker threadpool, ``httpx.Client`` is thread-safe).

Privacy: prompts and completions are never logged or placed in metrics.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Final
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.errors import AIProviderError
from app.core.metrics import record_ollama_outcome

__all__ = ["OllamaConfigError", "OllamaInferenceAdapter", "OllamaResult"]

logger = logging.getLogger(__name__)

_ALLOWED_ROLES: Final = frozenset({"system", "user", "assistant"})
_RETRYABLE_STATUS: Final = frozenset({500, 502, 503, 504})
_DEFAULT_MAX_RETRIES: Final = 2
_DEFAULT_BACKOFF_BASE_SECONDS: Final = 0.5
_DEFAULT_BACKOFF_MAX_SECONDS: Final = 4.0
_WRITE_TIMEOUT_SECONDS: Final = 10.0
_POOL_TIMEOUT_SECONDS: Final = 5.0
_MAX_TEMPERATURE: Final = 2.0

# Taxonomy binding (adaptation point 2): the existing §14 taxonomy has no
# INVALID_RESPONSE or REQUEST_REJECTED values, so both map to the closest
# existing one — SCHEMA_VALIDATION_FAILED (unusable response / rejected
# request; never retried, falls through to the next provider unchanged).
_UNAVAILABLE: Final = "MODEL_UNAVAILABLE"
_RATE_LIMITED: Final = "RATE_LIMITED"
_TIMEOUT: Final = "TIMEOUT"
_INVALID_RESPONSE: Final = "SCHEMA_VALIDATION_FAILED"
_REQUEST_REJECTED: Final = "SCHEMA_VALIDATION_FAILED"


class OllamaConfigError(ValueError):
    """Raised when the Ollama configuration is invalid."""


@dataclass(frozen=True, slots=True)
class OllamaResult:
    """Outcome of a successful chat completion."""

    content: str
    model: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int


class _TransientFailure(Exception):
    """Internal signal: the attempt failed in a way that is safe to retry."""

    def __init__(self, error: AIProviderError) -> None:
        super().__init__(str(error))
        self.error = error


def _provider_error(message: str, failure_class: str) -> AIProviderError:
    """Build a typed provider error. Single point of contact with ``AIProviderError``."""
    return AIProviderError(f"{failure_class}: {message}")


def _full_jitter(ceiling: float) -> float:
    """Return a delay drawn uniformly from ``[0, ceiling]`` (non-cryptographic use)."""
    return random.uniform(0.0, ceiling)  # noqa: S311


def _normalize_base_url(raw: str) -> str:
    candidate = raw.strip()
    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise OllamaConfigError("ollama base url is not a valid URL") from exc
    if parts.scheme not in {"http", "https"}:
        raise OllamaConfigError("ollama base url must use http or https")
    if not parts.hostname:
        raise OllamaConfigError("ollama base url must include a hostname")
    if parts.username or parts.password:
        raise OllamaConfigError("ollama base url must not embed credentials")
    if parts.query or parts.fragment:
        raise OllamaConfigError("ollama base url must not contain a query or fragment")
    return candidate.rstrip("/")


def _non_negative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _with_tag(name: str) -> str:
    """Ollama treats ``llama3.2`` and ``llama3.2:latest`` as the same model."""
    return name if ":" in name else f"{name}:latest"


def is_model_installed(model: str, installed: Iterable[str]) -> bool:
    """Return True when ``model`` is present in ``installed``.

    Single source of truth for the tag comparison, shared by
    :meth:`OllamaInferenceAdapter.is_available` and the readiness/CLI status
    probe so the two can never disagree. Pure function, no I/O.
    """
    wanted = _with_tag(model.strip())
    return any(_with_tag(name) == wanted for name in installed)


class OllamaInferenceAdapter:
    """Chat-completion client for a local Ollama server."""

    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        client: httpx.Client | None = None,
        timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
        keep_alive: str | None = None,
        default_temperature: float | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = _DEFAULT_BACKOFF_BASE_SECONDS,
        backoff_max_seconds: float = _DEFAULT_BACKOFF_MAX_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] = _full_jitter,
    ) -> None:
        self._base_url = _normalize_base_url(base_url if base_url is not None else settings.ollama_base_url)
        self._model = (model if model is not None else settings.ollama_model).strip()
        if not self._model:
            raise OllamaConfigError("ollama model must not be empty")

        read_timeout = timeout_seconds if timeout_seconds is not None else settings.ollama_timeout_seconds
        self._connect_timeout = (
            connect_timeout_seconds if connect_timeout_seconds is not None else settings.ollama_connect_timeout_seconds
        )
        self._keep_alive = keep_alive if keep_alive is not None else settings.ollama_keep_alive
        self._temperature = default_temperature if default_temperature is not None else settings.ollama_temperature
        if read_timeout <= 0 or self._connect_timeout <= 0:
            raise OllamaConfigError("ollama timeouts must be positive")
        if not 0.0 <= self._temperature <= _MAX_TEMPERATURE:
            raise OllamaConfigError("ollama temperature must be between 0 and 2")
        if max_retries < 0 or backoff_base_seconds < 0 or backoff_max_seconds < 0:
            raise OllamaConfigError("ollama retry settings must not be negative")

        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._sleep = sleep
        self._jitter = jitter

        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=self._connect_timeout,
                read=read_timeout,
                write=_WRITE_TIMEOUT_SECONDS,
                pool=_POOL_TIMEOUT_SECONDS,
            ),
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
            headers={"Accept": "application/json"},
        )
        self._closed = False

    def close(self) -> None:
        """Close the underlying HTTP client if this adapter created it. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OllamaInferenceAdapter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def model(self) -> str:
        """The configured model name."""
        return self._model

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        num_ctx: int | None = None,
    ) -> OllamaResult:
        """Run a non-streaming chat completion.

        Raises:
            ValueError: ``messages`` or an option is invalid (programming error).
            AIProviderError: the server is unavailable, rejected the request, or
                returned an unusable response.
        """
        payload = self._build_payload(messages, max_new_tokens, temperature, num_ctx)
        self._ensure_open()
        started = time.perf_counter()
        try:
            response = self._post_with_retry(f"{self._base_url}/api/chat", payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            result = self._parse_chat_response(response, latency_ms)
        except AIProviderError as exc:
            record_ollama_outcome(success=False, fallback_to_hf=True)
            logger.warning(
                "ai.ollama.chat failed model=%s latency_ms=%d error=%s",
                self._model,
                int((time.perf_counter() - started) * 1000),
                exc,
            )
            raise
        record_ollama_outcome(success=True)
        logger.info(
            "ai.ollama.chat ok model=%s latency_ms=%d prompt_tokens=%d completion_tokens=%d",
            result.model,
            result.latency_ms,
            result.prompt_tokens,
            result.completion_tokens,
        )
        return result

    def list_models(self) -> list[str]:
        """Return the names of the models installed on the server.

        Raises:
            AIProviderError: the server is unreachable or answered unexpectedly.
        """
        self._ensure_open()
        try:
            response = self._client.get(
                f"{self._base_url}/api/tags",
                timeout=httpx.Timeout(self._connect_timeout),
            )
        except httpx.TimeoutException as exc:
            raise _provider_error("ollama model listing timed out", _TIMEOUT) from exc
        except httpx.TransportError as exc:
            raise _provider_error("ollama is unreachable", _UNAVAILABLE) from exc
        if response.status_code != httpx.codes.OK:
            raise _provider_error(f"ollama model listing returned HTTP {response.status_code}", _UNAVAILABLE)
        try:
            body = response.json()
        except ValueError as exc:
            raise _provider_error("ollama model listing was not valid JSON", _INVALID_RESPONSE) from exc
        models = body.get("models") if isinstance(body, dict) else None
        if not isinstance(models, list):
            raise _provider_error("ollama model listing had an unexpected shape", _INVALID_RESPONSE)
        return [entry["name"] for entry in models if isinstance(entry, dict) and isinstance(entry.get("name"), str)]

    def is_available(self) -> bool:
        """Return True when the server is reachable and the model is installed.

        Never raises; intended for readiness probes.
        """
        try:
            installed = self.list_models()
        except AIProviderError as exc:
            logger.debug("ai.ollama.probe unavailable error=%s", exc)
            return False
        return is_model_installed(self._model, installed)

    def _ensure_open(self) -> None:
        if self._closed:
            raise _provider_error("ollama adapter is closed", _UNAVAILABLE)

    def _build_payload(
        self,
        messages: Sequence[Mapping[str, str]],
        max_new_tokens: int | None,
        temperature: float | None,
        num_ctx: int | None,
    ) -> dict[str, Any]:
        if not messages:
            raise ValueError("messages must not be empty")
        normalized: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            role = message.get("role")
            content = message.get("content")
            if not isinstance(role, str) or role not in _ALLOWED_ROLES or not isinstance(content, str):
                raise ValueError(f"invalid chat message at index {index}")
            normalized.append({"role": role, "content": content})

        effective_temperature = self._temperature if temperature is None else temperature
        if not 0.0 <= effective_temperature <= _MAX_TEMPERATURE:
            raise ValueError("temperature must be between 0 and 2")
        options: dict[str, Any] = {"temperature": effective_temperature}
        if max_new_tokens is not None:
            if max_new_tokens < 1:
                raise ValueError("max_new_tokens must be at least 1")
            options["num_predict"] = max_new_tokens
        if num_ctx is not None:
            if num_ctx < 1:
                raise ValueError("num_ctx must be at least 1")
            options["num_ctx"] = num_ctx
        return {
            "model": self._model,
            "messages": normalized,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": options,
        }

    def _post_with_retry(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        attempt = 0
        while True:
            try:
                return self._attempt(url, payload)
            except _TransientFailure as failure:
                if attempt >= self._max_retries:
                    raise failure.error from failure
                ceiling = min(self._backoff_max, self._backoff_base * (2**attempt))
                delay = self._jitter(ceiling)
                attempt += 1
                logger.warning(
                    "ai.ollama.retry model=%s attempt=%d/%d delay_ms=%d error=%s",
                    self._model,
                    attempt,
                    self._max_retries,
                    int(delay * 1000),
                    failure.error,
                )
                self._sleep(delay)

    def _attempt(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        try:
            response = self._client.post(url, json=payload)
        except (httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise _TransientFailure(_provider_error("ollama connection timed out", _TIMEOUT)) from exc
        except httpx.TimeoutException as exc:
            raise _provider_error("ollama timed out while generating", _TIMEOUT) from exc
        except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
            raise _TransientFailure(_provider_error("ollama is unreachable", _UNAVAILABLE)) from exc
        except httpx.TransportError as exc:
            raise _provider_error(f"ollama transport error ({type(exc).__name__})", _UNAVAILABLE) from exc

        status = response.status_code
        if status == httpx.codes.OK:
            return response
        if status == httpx.codes.NOT_FOUND:
            raise _provider_error(
                f"ollama model '{self._model}' is not installed; run `ollama pull {self._model}`",
                _UNAVAILABLE,
            )
        if status == httpx.codes.TOO_MANY_REQUESTS:
            raise _provider_error("ollama is rate limiting requests", _RATE_LIMITED)
        if status in _RETRYABLE_STATUS:
            raise _TransientFailure(_provider_error(f"ollama server error (HTTP {status})", _UNAVAILABLE))
        raise _provider_error(f"ollama rejected the request (HTTP {status})", _REQUEST_REJECTED)

    def _parse_chat_response(self, response: httpx.Response, latency_ms: int) -> OllamaResult:
        try:
            body = response.json()
        except ValueError as exc:
            raise _provider_error("ollama returned a non-JSON response", _INVALID_RESPONSE) from exc
        if not isinstance(body, dict):
            raise _provider_error("ollama returned an unexpected response shape", _INVALID_RESPONSE)
        message = body.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise _provider_error("ollama returned empty or missing content", _INVALID_RESPONSE)
        reported_model = body.get("model")
        return OllamaResult(
            content=content,
            model=reported_model if isinstance(reported_model, str) and reported_model else self._model,
            latency_ms=latency_ms,
            prompt_tokens=_non_negative_int(body.get("prompt_eval_count")),
            completion_tokens=_non_negative_int(body.get("eval_count")),
        )
