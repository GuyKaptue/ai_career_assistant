"""Informational Ollama channel status probe (RD-01 observability; no availability impact).

Produces a single source of truth, :class:`OllamaStatus`, consumed by both the
``/api/ready`` endpoint and the CLI (``models list`` / ``ai test --live``).

Design constraints, in order of importance:

* **Never affects availability.** The probe only *reads*: it does not trip or
  reset the circuit breaker, and it never mutates the shared adapter. The
  200/503 decision in ``/api/ready`` is taken before the probe result is used.
* **Bounded.** ``list_models()`` uses the adapter's connect timeout as the
  whole-request timeout, so a full probe stays within that budget (default 3 s)
  even against a black-holed server.
* **Cheap.** A short TTL cache (default 5 s, monotonic clock, lock-protected)
  absorbs health checks that hit ``/api/ready`` every second, so Ollama is
  probed at most once per TTL. ``reset_shared_state()`` clears it.
* **Silent when disabled.** ``use_ollama=False`` short-circuits before any
  network call.
* **Private.** The status never contains the base URL, prompts or completions.
* **Never raises.** Every failure maps to a typed status, logged once.

Thread safety: the cache is guarded by an ``RLock``; the probe itself runs
outside the lock so a slow Ollama never blocks other probes.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from app.application.services.ai_model_router import classify_failure
from app.core.config import AppSettings
from app.infrastructure.ai.ollama_adapter import (
    OllamaConfigError,
    OllamaInferenceAdapter,
    is_model_installed,
)

__all__ = [
    "OllamaStatus",
    "OllamaStatusProbe",
    "get_ollama_status",
    "reset_probe_cache",
]

logger = logging.getLogger(__name__)

#: Circuit states as reported by ``CircuitBreaker.state`` (uppercase in the
#: router) mapped to the lowercase vocabulary used in the readiness payload.
_CIRCUIT_STATES: Final[dict[str, Literal["closed", "open", "half_open"]]] = {
    "CLOSED": "closed",
    "OPEN": "open",
    "HALF_OPEN": "half_open",
}

#: Short TTL cache (monotonic clock). Health checks hammering ``/api/ready``
#: every second therefore reach Ollama at most once per TTL.
DEFAULT_CACHE_TTL_SECONDS: Final[float] = 5.0

#: Documented wall-clock ceiling for a single probe. ``list_models()`` enforces
#: it by using the adapter's connect timeout as the whole-request timeout; this
#: constant names the budget so tests can assert against it.
MAX_PROBE_SECONDS: Final[float] = 3.0

# Guards the one-time invalid-configuration error log so a probe hitting a
# misconfigured channel does not spam the log on every health check.
_config_error_lock: Final[threading.Lock] = threading.Lock()
_config_error_logged: bool = False


@dataclass(frozen=True, slots=True)
class OllamaStatus:
    """Informational snapshot of the local Ollama channel.

    ``None`` means "unknown": a probe that hit a hard error, a timeout, or an
    invalid configuration reports ``None`` rather than fabricating a value.

    This dataclass deliberately carries no base URL and no prompt/completion
    content, so it is safe to serialize into a public readiness response.
    """

    enabled: bool
    reachable: bool | None = None
    model: str | None = None
    model_installed: bool | None = None
    circuit: Literal["closed", "open", "half_open"] | None = None
    latency_ms: int | None = None

    def as_check(self) -> dict[str, Any]:
        """Serialize for the readiness payload (``checks`` sub-dict)."""
        return {
            "enabled": self.enabled,
            "reachable": self.reachable,
            "model": self.model,
            "model_installed": self.model_installed,
            "circuit": self.circuit,
            "latency_ms": self.latency_ms,
        }


class _StatusCache:
    """Lock-protected TTL cache for :class:`OllamaStatus` values."""

    __slots__ = ("_lock", "_result", "_expires_at", "_ttl", "_clock")

    def __init__(self, ttl_seconds: float, clock: Callable[[], float]) -> None:
        if ttl_seconds < 0:
            raise ValueError("cache ttl must not be negative")
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._result: OllamaStatus | None = None
        self._expires_at: float = 0.0

    def get(self) -> OllamaStatus | None:
        """Return the cached value, or ``None`` when absent or expired."""
        with self._lock:
            if self._result is not None and self._clock() < self._expires_at:
                return self._result
            return None

    def set(self, result: OllamaStatus) -> None:
        """Store ``result`` for one TTL from now."""
        with self._lock:
            self._result = result
            self._expires_at = self._clock() + self._ttl

    def clear(self) -> None:
        """Drop any cached value."""
        with self._lock:
            self._result = None
            self._expires_at = 0.0


def _circuit_name(raw_state: str | None) -> Literal["closed", "open", "half_open"] | None:
    """Map ``CircuitBreaker.state`` to the lowercase readiness vocabulary."""
    if not raw_state:
        return None
    return _CIRCUIT_STATES.get(raw_state)


def _log_config_error_once(exc: Exception) -> None:
    """Log an invalid-configuration error exactly once per process.

    A probe is not a config validation path: repeating the message on every
    health check would flood the log, so the first occurrence is recorded and
    later ones are silently mapped to ``enabled=False``.
    """
    global _config_error_logged
    with _config_error_lock:
        if _config_error_logged:
            return
        _config_error_logged = True
    logger.error("ai.ollama.status disabled invalid configuration: %s", exc)


class OllamaStatusProbe:
    """Read-only, TTL-cached probe of the local Ollama channel.

    Args:
        settings_obj: Process settings; read for ``use_ollama``/``ollama_model``.
        adapter_getter: Returns the shared generation adapter. When it is an
            :class:`OllamaFirstAdapter` the probe reuses its pooled Ollama
            client (one connection, one configuration) and never closes it.
            Otherwise a short-lived adapter is built in a ``with`` block.
        circuit_state: Read-only accessor for the wrapper's breaker state.
        cache_ttl_seconds: How long a result stays fresh.
        clock: Injectable monotonic clock, so tests can drive cache expiry.
        adapter_factory: Builds a temporary :class:`OllamaInferenceAdapter`;
            injectable so tests can supply a ``MockTransport`` client.

    The probe never mutates the adapter or the breaker.
    """

    __slots__ = (
        "_settings",
        "_adapter_getter",
        "_circuit_state",
        "_cache",
        "_adapter_factory",
    )

    def __init__(
        self,
        *,
        settings_obj: AppSettings,
        adapter_getter: Callable[[], Any],
        circuit_state: Callable[[], str | None],
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        adapter_factory: Callable[[], OllamaInferenceAdapter] = OllamaInferenceAdapter,
    ) -> None:
        self._settings = settings_obj
        self._adapter_getter = adapter_getter
        self._circuit_state = circuit_state
        self._cache = _StatusCache(cache_ttl_seconds, clock)
        self._adapter_factory = adapter_factory

    @property
    def cache_ttl_seconds(self) -> float:
        """The TTL this probe caches results for."""
        return self._cache._ttl  # noqa: SLF001 - read-only accessor for tests

    def current(self) -> OllamaStatus:
        """Return the status, probing at most once per TTL. Never raises."""
        cached = self._cache.get()
        if cached is not None:
            return cached
        result = self._do_probe()
        self._cache.set(result)
        return result

    def invalidate(self) -> None:
        """Drop the cached value so the next call re-probes."""
        self._cache.clear()

    # -- probing ---------------------------------------------------------------

    def _unreachable(self) -> OllamaStatus:
        """Build the status for a probe that could not reach Ollama.

        ``circuit`` is reported even here: the contract is that ``circuit`` is
        ``null`` *only* when the channel is disabled, so an operator reading
        ``/api/ready`` can tell an open breaker from a merely unreachable
        server. Reading the breaker state never mutates it.
        """
        return OllamaStatus(
            enabled=True,
            reachable=False,
            model=self._configured_model(),
            model_installed=None,
            circuit=_circuit_name(self._read_circuit_state()),
            latency_ms=None,
        )

    def _do_probe(self) -> OllamaStatus:
        """Perform the probe. Every branch returns; none raise."""
        if not self._settings.use_ollama:
            # Disabled: no network call at all.
            return OllamaStatus(enabled=False)

        try:
            ollama, owned = self._resolve_adapter()
        except OllamaConfigError as exc:
            # One-time, build-time-style log; the channel simply stays off.
            _log_config_error_once(exc)
            return OllamaStatus(enabled=False)
        except Exception as exc:  # noqa: BLE001 - a probe must never escape
            logger.warning("ai.ollama.status probe setup failed: %s", exc)
            return self._unreachable()

        try:
            started = time.perf_counter()
            installed = ollama.list_models()
            latency_ms = int((time.perf_counter() - started) * 1000)
        except OllamaConfigError as exc:  # defensive: config errors can surface late
            _log_config_error_once(exc)
            return OllamaStatus(enabled=False)
        except Exception as exc:  # noqa: BLE001 - unreachable/timeout/invalid
            failure_class = classify_failure(exc)
            logger.warning(
                "ai.ollama.status probe failed model=%s failure_class=%s",
                self._configured_model(),
                failure_class,
            )
            return self._unreachable()
        finally:
            if owned:
                self._close_quietly(ollama)

        model = self._configured_model()
        if model is None:
            # Reachable but no configured model: nothing to compare against.
            return OllamaStatus(
                enabled=True,
                reachable=True,
                model=None,
                model_installed=None,
                circuit=_circuit_name(self._read_circuit_state()),
                latency_ms=latency_ms,
            )
        return OllamaStatus(
            enabled=True,
            reachable=True,
            model=model,
            model_installed=is_model_installed(model, installed),
            circuit=_circuit_name(self._read_circuit_state()),
            latency_ms=latency_ms,
        )

    def _resolve_adapter(self) -> tuple[OllamaInferenceAdapter, bool]:
        """Return ``(ollama_adapter, owned)``.

        ``owned`` is True when this probe created the adapter and must close it;
        the shared adapter is never closed.
        """
        # Local import to keep the module graph acyclic (see TYPE_CHECKING above).
        from app.application.services.ollama_first_adapter import OllamaFirstAdapter

        shared = self._adapter_getter()
        if isinstance(shared, OllamaFirstAdapter):
            return shared.ollama_adapter, False
        return self._adapter_factory(), True

    @staticmethod
    def _close_quietly(adapter: OllamaInferenceAdapter) -> None:
        """Close a temporary adapter without letting the failure escape.

        A probe exists to observe, never to raise: if the client cannot be
        closed the status is still valid and the error is noted at debug level.
        """
        try:
            adapter.close()
        except Exception:  # noqa: BLE001 - closing must never break the probe
            logger.debug("ai.ollama.status adapter close failed", exc_info=True)

    def _configured_model(self) -> str | None:
        """The configured model name, or ``None`` when unavailable."""
        return getattr(self._settings, "ollama_model", None) or None

    def _read_circuit_state(self) -> str | None:
        """Read the breaker state without mutating it."""
        getter = self._circuit_state
        if getter is None:
            return None
        try:
            return getter()
        except Exception:  # noqa: BLE001 - a probe must never escape
            return None


# -- module-level singleton ---------------------------------------------------

#: Reentrant on purpose: ``get_ollama_status`` builds a probe that may resolve
#: the shared adapter, whose construction touches ``_probe`` through
#: ``reset_probe_cache``/``configure_probe``. A plain Lock would be re-entered
#: by that path, so it must be reentrant to stay correct under concurrency.
_probe_lock: Final[threading.RLock] = threading.RLock()
_probe: OllamaStatusProbe | None = None


def _default_probe() -> OllamaStatusProbe:
    """Build the process-wide probe, wired to the shared generation adapter."""
    from app.application.services.shared_router import get_adapter

    def _adapter_getter() -> Any:
        return get_adapter()

    def _circuit_getter() -> str | None:
        """Read the breaker state from whatever the shared adapter exposes.

        A wrapper exposes `circuit_state` as a read-only *property* (a plain
        string), while a test-injected probe may supply a callable. Both forms
        are accepted so a cold start — before `build_generation_adapter` has
        installed an explicitly-bound probe — still reports a real circuit state
        instead of `null`. Reading it never mutates the breaker.
        """
        adapter = _adapter_getter()
        state = getattr(adapter, "circuit_state", None)
        if state is None:
            return None
        return state() if callable(state) else state

    return OllamaStatusProbe(
        settings_obj=_settings(),
        adapter_getter=_adapter_getter,
        circuit_state=_circuit_getter,
        cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
        clock=time.monotonic,
    )


def _settings() -> AppSettings:
    """The process settings, imported lazily to keep the module import graph acyclic."""
    from app.core.config import settings

    return settings


def get_ollama_status() -> OllamaStatus:
    """Return the current Ollama informational status (cached, bounded, never raises).

    Single entry point used by ``/api/ready`` and the CLI.

    The probe is deliberately built **outside** the lock: building it resolves
    the shared generation adapter, and that may call
    ``build_generation_adapter`` -> ``reset_probe_cache``, which mutates
    ``_probe`` (and installs an explicitly-bound probe) through this very lock.
    Holding the lock across that call would re-enter a lock guarding the global
    being assigned, and CPython's ``threading.Lock`` is reentrant, so the
    re-entrant reset would clobber the assignment and nothing would ever be
    cached. Building first, then a double-checked assignment, keeps the lock
    honest and lets an explicitly-bound probe win.
    """
    global _probe
    probe = _probe
    if probe is None:
        probe = _default_probe()
        with _probe_lock:
            probe = _probe if _probe is not None else probe
            _probe = probe
    status = probe.current()
    with _probe_lock:
        # The probe's very first run resolves the shared generation adapter,
        # whose construction may call ``reset_probe_cache`` and drop what was
        # just installed. Re-install so this probe's TTL cache is effective on
        # the next call — without ever clobbering an explicitly-bound probe.
        if _probe is None:
            _probe = probe
    return status


def reset_probe_cache() -> None:
    """Clear the probe cache and forget the configured probe.

    Called by ``reset_shared_state()`` so tests and reconfiguration start clean.
    """
    global _probe
    with _probe_lock:
        if _probe is not None:
            _probe.invalidate()
        _probe = None
    with _config_error_lock:
        global _config_error_logged
        _config_error_logged = False


def configure_probe(probe: OllamaStatusProbe | None) -> None:
    """Install a probe instance, or drop it when ``None``.

    Used by :func:`build_generation_adapter` to bind the probe to the shared
    adapter (and therefore to its pooled Ollama client), and by tests to inject
    a probe with a fake clock. Pass ``None`` to remove the override.
    """
    global _probe
    with _probe_lock:
        _probe = probe
