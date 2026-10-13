"""Shared builders for the Ollama test matrix (Sub-step 7a).

Everything here is deterministic and offline: a scripted Ollama server backed by
``httpx.MockTransport``, an injected sleep that *records* delays instead of
waiting, a fixed jitter, and a clock the tests advance by hand. No test in this
package opens a socket, sleeps on a wall clock, or binds a port.
"""

from __future__ import annotations

import dataclasses
import json
import threading
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import httpx
import pytest

from app.core.config import AppSettings, settings

__all__ = [
    "FakeHfAdapter",
    "FakeOllamaServer",
    "FixedJitter",
    "RecordingClock",
    "RecordingSleep",
    "connect_refused",
    "connect_timeout",
    "enable_ollama",
    "fake_ollama_settings",
    "http",
    "make_adapter",
    "make_wrapper",
    "non_json_body",
    "ok_chat",
    "pool_timeout",
    "protocol_error",
    "read_timeout",
    "tags_response",
]


class RecordingSleep:
    """Injected ``sleep``: records the requested delay and returns immediately."""

    def __init__(self) -> None:
        self.delays: list[float] = []
        self._lock = threading.Lock()

    def __call__(self, seconds: float) -> None:
        with self._lock:
            self.delays.append(seconds)

    @property
    def total(self) -> float:
        return sum(self.delays)


class FixedJitter:
    """Injected jitter returning a constant, so retry schedules are exact."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value
        self.calls: list[float] = []

    def __call__(self, ceiling: float) -> float:
        self.calls.append(ceiling)
        return self.value


class RecordingClock:
    """Monotonic clock the test advances by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now += seconds


class FakeOllamaServer:
    """A scripted Ollama server over ``httpx.MockTransport``.

    ``chat_script`` / ``tags_script`` are consumed one entry per request; an
    entry is either an ``httpx.Response`` to return or an ``Exception`` to
    raise. Exhausting a script repeats the last entry, so "always 503" needs a
    single-item script. Every inbound request is recorded in ``requests``.
    """

    def __init__(
        self,
        chat_script: Sequence[Any] | None = None,
        tags_script: Sequence[Any] | None = None,
    ) -> None:
        self.chat_script: list[Any] = list(chat_script) if chat_script else [ok_chat()]
        self.tags_script: list[Any] = list(tags_script) if tags_script else []
        self.requests: list[httpx.Request] = []
        self._chat_index = 0
        self._tags_index = 0
        self._lock = threading.Lock()

    # -- request accounting ----------------------------------------------------
    @property
    def chat_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith("/api/chat")]

    @property
    def tags_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith("/api/tags")]

    @property
    def total_requests(self) -> int:
        return len(self.requests)

    def last_chat_payload(self) -> dict[str, Any]:
        """The JSON body of the most recent chat request."""
        return json.loads(self.chat_requests[-1].content.decode())

    # -- transport -------------------------------------------------------------
    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            with self._lock:
                self.requests.append(request)
                if request.url.path.endswith("/api/chat"):
                    index, script, attr = self._chat_index, self.chat_script, "_chat_index"
                    self._chat_index += 1
                elif request.url.path.endswith("/api/tags"):
                    index, script, attr = self._tags_index, self.tags_script, "_tags_index"
                    self._tags_index += 1
                else:  # pragma: no cover - only reachable via a wiring bug
                    return httpx.Response(404, json={"error": "unexpected path"})
                del attr
            entry = script[min(index, len(script) - 1)]
            if isinstance(entry, BaseException):
                raise entry
            return entry

        return httpx.MockTransport(handler)


def ok_chat(
    content: str = "Here is your answer.",
    model: str = "llama3.2:3b",
    prompt_eval_count: int = 42,
    eval_count: int = 17,
) -> httpx.Response:
    """A 200 chat response with every documented field populated."""
    return httpx.Response(
        200,
        json={
            "model": model,
            "message": {"role": "assistant", "content": content},
            "done": True,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": eval_count,
        },
    )


def tags_response(models: Iterable[str]) -> httpx.Response:
    """A 200 ``/api/tags`` response listing ``models``."""
    return httpx.Response(200, json={"models": [{"name": name} for name in models]})


def connect_refused() -> httpx.ConnectError:
    return httpx.ConnectError("connection refused")


def connect_timeout() -> httpx.ConnectTimeout:
    return httpx.ConnectTimeout("connect timed out")


def read_timeout() -> httpx.ReadTimeout:
    return httpx.ReadTimeout("read timed out")


def pool_timeout() -> httpx.PoolTimeout:
    return httpx.PoolTimeout("pool timed out")


def protocol_error() -> httpx.RemoteProtocolError:
    return httpx.RemoteProtocolError("server disconnected")


def http(status: int, body: Any = None) -> httpx.Response:
    """An Ollama-style HTTP response with the given status."""
    return httpx.Response(status, json=body if body is not None else {"error": "boom"})


def non_json_body() -> httpx.Response:
    """A 200 whose body is not JSON."""
    return httpx.Response(200, text="this is not json")


def fake_ollama_settings(**overrides: Any) -> AppSettings:
    """Process settings with Ollama enabled, aimed at the fake host."""
    base = {
        "use_ollama": True,
        "ollama_base_url": "http://ollama.test:11434",
        "ollama_model": "llama3.2:3b",
        "supabase_jwt_secret": "x" * 40,
        "huggingface_token": "hf_test",
    }
    base.update(overrides)
    return dataclasses.replace(settings, **base)


def enable_ollama(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> AppSettings:
    """Opt this test into Ollama: re-point every module's settings.

    The autouse ``disable_ollama_by_default`` fixture turns Ollama off for the
    whole suite; Ollama tests call this to turn it back on with a fake host.

    Two modules are patched because they each read their own module-level
    ``settings``: ``ollama_first_adapter`` gates on ``use_ollama``, while
    ``ollama_adapter`` reads the base URL/model/timeouts when it constructs.
    Patching only one would leave the other reading the real configuration.
    """
    import app.application.services.ollama_first_adapter as ollama_first_module
    import app.infrastructure.ai.ollama_adapter as ollama_adapter_module

    replacement = fake_ollama_settings(**overrides)
    monkeypatch.setattr(ollama_first_module, "settings", replacement)
    monkeypatch.setattr(ollama_adapter_module, "settings", replacement)
    return replacement


def make_adapter(
    server: FakeOllamaServer,
    *,
    sleep: Callable[[float], None] | None = None,
    jitter: Callable[[float], float] | None = None,
    max_retries: int = 2,
    backoff_base_seconds: float = 0.5,
    backoff_max_seconds: float = 4.0,
    **adapter_kwargs: Any,
):
    """An ``OllamaInferenceAdapter`` wired to the scripted server.

    The client is injected (never owned), so closing it is the caller's
    decision and lifecycle assertions stay exact.
    """
    from app.infrastructure.ai.ollama_adapter import OllamaInferenceAdapter

    client = httpx.Client(transport=server.transport())
    return OllamaInferenceAdapter(
        base_url="http://ollama.test:11434",
        client=client,
        sleep=sleep if sleep is not None else RecordingSleep(),
        jitter=jitter if jitter is not None else FixedJitter(),
        max_retries=max_retries,
        backoff_base_seconds=backoff_base_seconds,
        backoff_max_seconds=backoff_max_seconds,
        **adapter_kwargs,
    )


class FakeHfAdapter:
    """Minimal Hugging Face adapter recording every call."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result or {
            "content": "hf answer",
            "model_id": "fake/hf-model",
            "fallback_reason": None,
            "fallback_chain": ["fake/hf-model"],
            "routing_score": 0.5,
            "required_context": 64,
        }

    def generate_with_fallback(self, task: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"task": task, "prompt": prompt, **kwargs})
        return dict(self._result)

    @property
    def call_count(self) -> int:
        return len(self.calls)


def make_wrapper(
    server: FakeOllamaServer,
    hf: FakeHfAdapter | None = None,
    **adapter_kwargs: Any,
):
    """An ``OllamaFirstAdapter`` around the scripted server and a fake HF."""
    from app.application.services.ollama_first_adapter import OllamaFirstAdapter

    return OllamaFirstAdapter(hf or FakeHfAdapter(), make_adapter(server, **adapter_kwargs))


class FailingHfAdapter:
    """A Hugging Face adapter whose only behaviour is to fail, like a real one.

    ``content`` is preserved so privacy tests can assert it never leaks.
    """

    def __init__(self, message: str = "hf is down", marker: str = "HF_ANSWER_MARKER") -> None:
        self.message = message
        self.marker = marker
        self.calls = 0

    def generate_with_fallback(self, task, prompt, **kwargs: Any) -> dict[str, Any]:
        from app.core.errors import AIProviderError

        self.calls += 1
        raise AIProviderError(f"MODEL_UNAVAILABLE: {self.message}")


def install_adapter(
    monkeypatch: pytest.MonkeyPatch,
    server: FakeOllamaServer,
    hf: Any,
    *,
    breaker: Any = None,
) -> Any:
    """Point the shared-adapter singleton at a wrapper over ``server``.

    Also resets the probe cache, so a test's probe is rebuilt against this
    adapter rather than a previous test's.
    """
    import app.application.services.ollama_first_adapter as ollama_first_module
    import app.application.services.ollama_status_probe as probe_module
    import app.application.services.shared_router as shared_router_module

    wrapper = ollama_first_module.OllamaFirstAdapter(hf, make_adapter(server), breaker)
    monkeypatch.setattr(shared_router_module, "build_generation_adapter", lambda _: wrapper)
    shared_router_module.set_adapter_for_testing(wrapper)
    probe_module.reset_probe_cache()
    return wrapper


def reset_shared_state() -> None:
    """Reset both the shared adapter singleton and the probe cache."""
    import app.application.services.ollama_status_probe as probe_module
    import app.application.services.shared_router as shared_router_module

    shared_router_module.reset_shared_state()
    probe_module.reset_probe_cache()


def make_settings(**overrides: Any) -> AppSettings:
    """Settings suitable for an Ollama test: fake host, no real credentials."""
    base = {
        "use_ollama": True,
        "ollama_base_url": "http://ollama.test:11434",
        "ollama_model": "llama3.2:3b",
        "supabase_jwt_secret": "x" * 40,
        "huggingface_token": "hf_test",
        "supabase_url": "",
        "supabase_service_role_key": "",
    }
    base.update(overrides)
    return dataclasses.replace(settings, **base)
