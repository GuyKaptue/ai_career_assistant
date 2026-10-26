"""Wrapper contract for the Ollama-first generation adapter (Sub-step 4 → committed 7a).

The wrapper must try Ollama, fall through to Hugging Face with the reason
annotated, and never let a schema failure trip the circuit breaker.
"""

from __future__ import annotations

import concurrent.futures
import json

import httpx
import pytest
from ollama_helpers import (
    FakeHfAdapter,
    FakeOllamaServer,
    FixedJitter,
    RecordingClock,
    RecordingSleep,
    connect_refused,
    enable_ollama,
    http,
    make_wrapper,
    ok_chat,
)

import app.application.services.ollama_first_adapter as first_module
from app.application.services.ai_model_router import (
    MODEL_UNAVAILABLE,
)
from app.core.errors import AIProviderError

PROMPT = "write my cv"
TASK = "cv_generation"
BUDGET = 512

#: The keys a Hugging Face result carries; the wrapper must not add or drop any.
HF_KEYS = {
    "content",
    "model_id",
    "fallback_reason",
    "fallback_chain",
    "routing_score",
    "required_context",
}


def _hf_result(**overrides):
    base = {
        "content": "hf answer",
        "model_id": "fake/hf-model",
        "fallback_reason": None,
        "fallback_chain": ["fake/hf-model"],
        "routing_score": 0.5,
        "required_context": 64,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Ollama answers
# ---------------------------------------------------------------------------
class TestOllamaSucceeds:
    def test_hf_is_never_called_and_result_shape_matches_hf(self, monkeypatch):
        enable_ollama(monkeypatch)
        hf = FakeHfAdapter()
        server = FakeOllamaServer()
        wrapper = make_wrapper(server, hf)

        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert hf.call_count == 0
        assert set(result) == HF_KEYS
        assert result["content"] == "Here is your answer."
        assert result["model_id"] == "ollama:llama3.2:3b"
        assert result["fallback_reason"] is None
        assert result["fallback_chain"] == ["ollama:llama3.2:3b"]
        # required_context comes from the reported prompt tokens; no score.
        assert result["required_context"] == 42
        assert result["routing_score"] is None

    def test_required_context_reports_the_servers_token_count(self, monkeypatch):
        # ``required_context`` is the prompt size the *server* reported: it is
        # observability, so a zero is passed through rather than hidden.
        enable_ollama(monkeypatch)
        server = FakeOllamaServer([ok_chat(prompt_eval_count=0)])
        wrapper = make_wrapper(server)

        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert result["required_context"] == 0

    def test_required_context_reflects_a_real_token_count(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer([ok_chat(prompt_eval_count=123)])
        wrapper = make_wrapper(server)

        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert result["required_context"] == 123

    def test_exactly_one_upstream_request(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer()
        wrapper = make_wrapper(server)
        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert len(server.chat_requests) == 1


# ---------------------------------------------------------------------------
# Ollama fails, HF takes over
# ---------------------------------------------------------------------------
class TestFallsBackToHuggingFace:
    def test_hf_called_once_with_identical_arguments(self, monkeypatch):
        enable_ollama(monkeypatch)
        hf = FakeHfAdapter()
        server = FakeOllamaServer([http(404)])
        wrapper = make_wrapper(server, hf)

        result = wrapper.generate_with_fallback(
            TASK, PROMPT, token_budget=BUDGET, preferred_languages=("en", "de", "fr")
        )

        assert hf.call_count == 1
        call = hf.calls[0]
        assert call["task"] == TASK
        assert call["prompt"] == PROMPT
        assert call["token_budget"] == BUDGET
        assert call["preferred_languages"] == ("en", "de", "fr")
        # the HF answer is returned, annotated
        assert result["content"] == "hf answer"
        assert result["model_id"] == "fake/hf-model"

    def test_fallback_reason_is_prefixed_with_the_ollama_class(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer([http(404)])
        wrapper = make_wrapper(server)

        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert result["fallback_reason"].startswith(f"{MODEL_UNAVAILABLE}:")
        assert "ollama pull llama3.2:3b" in result["fallback_reason"]

    def test_fallback_chain_is_prefixed_with_the_ollama_id(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer([http(404)])
        wrapper = make_wrapper(server)

        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert result["fallback_chain"][0] == "ollama:llama3.2:3b"
        assert result["fallback_chain"][1:] == ["fake/hf-model"]

    def test_reasons_are_joined_when_hf_also_reports_one(self, monkeypatch):
        enable_ollama(monkeypatch)
        hf = FakeHfAdapter(_hf_result(fallback_reason="hf degraded"))
        server = FakeOllamaServer([http(404)])
        wrapper = make_wrapper(server, hf)

        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert "; hf degraded" in result["fallback_reason"]
        assert result["fallback_reason"].startswith(f"{MODEL_UNAVAILABLE}:")

    def test_plain_hf_chain_is_replaced_rather_than_appended(self, monkeypatch):
        enable_ollama(monkeypatch)
        hf = FakeHfAdapter(_hf_result(fallback_chain="not-a-list"))
        server = FakeOllamaServer([http(404)])
        wrapper = make_wrapper(server, hf)

        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert result["fallback_chain"] == ["ollama:llama3.2:3b"]

    def test_router_state_is_untouched_on_fallback(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer([http(404)])
        wrapper = make_wrapper(server)
        assert wrapper.circuit_state == "CLOSED"
        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert wrapper.circuit_state == "CLOSED"


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
class TestCircuitBreaker:
    def _wrapper(self, script, **kwargs):
        return make_wrapper(FakeOllamaServer(script), **kwargs)

    def test_three_availability_failures_open_the_breaker(self, monkeypatch):
        enable_ollama(monkeypatch)
        wrapper = self._wrapper([connect_refused()], sleep=RecordingSleep())
        for _ in range(3):
            wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert wrapper.circuit_state == "OPEN"

    def test_open_breaker_makes_zero_ollama_requests_and_counts_a_skip(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer([connect_refused()])
        wrapper = make_wrapper(server, sleep=RecordingSleep())
        for _ in range(3):
            wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        requests_before = len(server.chat_requests)

        skips: list[int] = []
        monkeypatch.setattr(first_module, "record_ollama_skip", lambda: skips.append(1))

        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert len(server.chat_requests) == requests_before  # zero new Ollama calls
        assert skips == [1]
        assert result["fallback_reason"].startswith(f"{MODEL_UNAVAILABLE}:")
        assert "circuit breaker open" in result["fallback_reason"]

    def test_probe_request_is_made_after_the_reset_timeout(self, monkeypatch):
        enable_ollama(monkeypatch)
        # The breaker consults time.monotonic() directly, so the test drives it.
        import app.application.services.ai_model_router as router_module

        now = RecordingClock()
        monkeypatch.setattr(router_module.time, "monotonic", now)
        server = FakeOllamaServer([ok_chat()])
        wrapper = make_wrapper(server, sleep=RecordingSleep())

        wrapper._breaker._state = "OPEN"
        wrapper._breaker._last_failure_time = now()
        requests_before = len(server.chat_requests)

        # Inside the reset timeout (30 s): fail fast, no probe request at all.
        now.advance(10.0)
        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert len(server.chat_requests) == requests_before

        # Past it: exactly one probe request. A successful probe from OPEN
        # lands on HALF_OPEN (the documented half-open probe state); it takes a
        # second success to close the breaker fully.
        now.advance(40.0)
        result = wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert len(server.chat_requests) == requests_before + 1
        assert wrapper.circuit_state == "HALF_OPEN"
        assert result["fallback_reason"] is None

        # Second consecutive success closes it.
        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert wrapper.circuit_state == "CLOSED"

    def test_failed_probe_reopens_the_breaker(self, monkeypatch):
        enable_ollama(monkeypatch)
        import app.application.services.ai_model_router as router_module

        now = RecordingClock()
        monkeypatch.setattr(router_module.time, "monotonic", now)
        server = FakeOllamaServer([connect_refused()])
        wrapper = make_wrapper(server, sleep=RecordingSleep())

        wrapper._breaker._state = "OPEN"
        wrapper._breaker._last_failure_time = now()
        now.advance(40.0)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        # The probe was attempted (and retried) but failed, so it stays open.
        assert len(server.chat_requests) == wrapper._ollama._max_retries + 1
        assert wrapper.circuit_state == "OPEN"

    def test_schema_failure_does_not_open_the_breaker(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer([http(400)])
        wrapper = make_wrapper(server)
        for _ in range(3):
            wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert wrapper.circuit_state == "CLOSED"
        # and every call did reach Ollama
        assert len(server.chat_requests) == 3

    @pytest.mark.parametrize(
        "script", [connect_refused(), http(429), None], ids=["unavailable", "rate_limited", "timeout"]
    )
    def test_availability_classes_open_the_breaker(self, monkeypatch, script):
        enable_ollama(monkeypatch)
        entry = http(503) if script is None else script
        wrapper = make_wrapper(FakeOllamaServer([entry]), sleep=RecordingSleep())
        for _ in range(3):
            wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert wrapper.circuit_state == "OPEN"

    def test_value_error_propagates_and_leaves_the_breaker_alone(self, monkeypatch):
        enable_ollama(monkeypatch)
        wrapper = make_wrapper(FakeOllamaServer())

        def boom(*args, **kwargs):
            raise ValueError("bad payload")

        monkeypatch.setattr(wrapper._ollama, "chat", boom)

        with pytest.raises(ValueError, match="bad payload"):
            wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert wrapper.circuit_state == "CLOSED"

    def test_hf_error_propagates_unchanged(self, monkeypatch):
        enable_ollama(monkeypatch)
        hf_error = AIProviderError(f"{MODEL_UNAVAILABLE}: hf is down")

        class ExplodingHf:
            def generate_with_fallback(self, *args, **kwargs):
                raise hf_error

        wrapper = make_wrapper(FakeOllamaServer([http(404)]), ExplodingHf())
        with pytest.raises(AIProviderError) as excinfo:
            wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        assert excinfo.value is hf_error


# ---------------------------------------------------------------------------
# preferred_model_id
# ---------------------------------------------------------------------------
class TestPreferredModelId:
    def test_pinning_an_hf_model_skips_ollama_entirely(self, monkeypatch):
        enable_ollama(monkeypatch)
        hf = FakeHfAdapter()
        server = FakeOllamaServer()
        wrapper = make_wrapper(server, hf)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET, preferred_model_id="meta-llama/Llama-3.1-8B")

        assert server.total_requests == 0
        assert hf.calls[0]["preferred_model_id"] == "meta-llama/Llama-3.1-8B"

    def test_pinning_the_ollama_model_keeps_ollama_first(self, monkeypatch):
        enable_ollama(monkeypatch)
        hf = FakeHfAdapter()
        server = FakeOllamaServer()
        wrapper = make_wrapper(server, hf)

        result = wrapper.generate_with_fallback(
            TASK, PROMPT, token_budget=BUDGET, preferred_model_id="ollama:llama3.2:3b"
        )

        assert len(server.chat_requests) == 1
        assert result["model_id"] == "ollama:llama3.2:3b"
        assert hf.call_count == 0

    def test_ollama_pin_falls_back_with_the_pin_removed(self, monkeypatch):
        enable_ollama(monkeypatch)
        hf = FakeHfAdapter()
        server = FakeOllamaServer([http(404)])
        wrapper = make_wrapper(server, hf)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET, preferred_model_id="ollama:llama3.2:3b")

        assert hf.call_count == 1
        # HF must not be told to use a model id it cannot resolve.
        assert hf.calls[0]["preferred_model_id"] is None


# ---------------------------------------------------------------------------
# System prompt / payload
# ---------------------------------------------------------------------------
class TestSystemPrompt:
    def test_empty_system_prompt_sends_one_message(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer()
        wrapper = make_wrapper(server)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET, system_prompt="  ")

        assert server.last_chat_payload()["messages"] == [{"role": "user", "content": PROMPT}]

    def test_non_empty_system_prompt_prepends_the_system_message(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer()
        wrapper = make_wrapper(server)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET, system_prompt="Be concise.")

        assert server.last_chat_payload()["messages"] == [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": PROMPT},
        ]

    def test_num_ctx_comes_from_config_and_num_predict_from_the_budget(self, monkeypatch):
        # F1: num_ctx is the configured context window (never the request's
        # token budget); num_predict still mirrors the budget, so output-length
        # behaviour is unchanged.
        enable_ollama(monkeypatch)
        server = FakeOllamaServer()
        wrapper = make_wrapper(server)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        options = server.last_chat_payload()["options"]
        assert options["num_ctx"] == first_module.settings.ollama_num_ctx
        assert options["num_predict"] == BUDGET


# ---------------------------------------------------------------------------
# F1: num_ctx = configured window, clamped once against POST /api/show
# ---------------------------------------------------------------------------
class TestNumCtxContextWindow:
    """The request's token budget no longer decides num_ctx (finding F1)."""

    @staticmethod
    def _wrapper_with_show(server: FakeOllamaServer, show_response, show_calls: list):
        """A wrapper whose Ollama client also answers ``POST /api/show``."""
        from app.infrastructure.ai.ollama_adapter import OllamaInferenceAdapter

        inner = server.transport()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/api/show"):
                show_calls.append(request)
                if isinstance(show_response, BaseException):
                    raise show_response
                return show_response
            return inner.handle_request(request)

        adapter = OllamaInferenceAdapter(
            base_url="http://ollama.test:11434",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=RecordingSleep(),
            jitter=FixedJitter(),
        )
        return first_module.OllamaFirstAdapter(FakeHfAdapter(), adapter)

    def test_configured_window_is_sent_when_the_lookup_fails(self, monkeypatch):
        # The fake server 404s unknown paths, so the /api/show lookup fails and
        # the configured value must be used unchanged.
        enable_ollama(monkeypatch, ollama_num_ctx=4096)
        server = FakeOllamaServer()
        wrapper = make_wrapper(server)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        options = server.last_chat_payload()["options"]
        assert options["num_ctx"] == 4096
        assert options["num_predict"] == BUDGET

    @pytest.mark.parametrize(
        ("reported", "expected"),
        [(2048, 2048), (262144, 8192)],
        ids=["smaller_real_window_clamps_down", "larger_real_window_keeps_configured_ceiling"],
    )
    def test_num_ctx_is_clamped_to_the_real_window_but_never_inflated(self, monkeypatch, reported, expected):
        enable_ollama(monkeypatch, ollama_num_ctx=8192)
        server = FakeOllamaServer()
        show_calls: list = []
        show = httpx.Response(200, json={"model_info": {"llama.context_length": reported}})
        wrapper = self._wrapper_with_show(server, show, show_calls)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert len(show_calls) == 1
        assert server.last_chat_payload()["options"]["num_ctx"] == expected

    def test_context_lookup_happens_once_for_the_whole_adapter(self, monkeypatch):
        enable_ollama(monkeypatch, ollama_num_ctx=8192)
        server = FakeOllamaServer()
        show_calls: list = []
        show = httpx.Response(200, json={"model_info": {"llama.context_length": 4096}})
        wrapper = self._wrapper_with_show(server, show, show_calls)

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)
        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        # Exactly one /api/show for the adapter's lifetime; both chats carry
        # the clamped window.
        assert len(show_calls) == 1
        assert len(server.chat_requests) == 2
        body = json.loads(show_calls[0].content.decode())
        assert body["model"] == "llama3.2:3b"
        assert body["name"] == "llama3.2:3b"
        for request in server.chat_requests:
            assert json.loads(request.content.decode())["options"]["num_ctx"] == 4096

    @pytest.mark.parametrize(
        "failure",
        [
            httpx.ConnectError("connection refused"),
            httpx.Response(500, json={"error": "nope"}),
            httpx.Response(200, text="this is not json"),
            httpx.Response(200, json=["unexpected"]),
            httpx.Response(200, json={"model_info": {}}),
        ],
        ids=["connect-error", "http-500", "non-json", "wrong-type", "no-context-key"],
    )
    def test_lookup_failure_never_raises_and_configured_value_survives(self, monkeypatch, failure):
        enable_ollama(monkeypatch, ollama_num_ctx=3072)
        server = FakeOllamaServer()
        wrapper = self._wrapper_with_show(server, failure, [])

        wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET)

        assert server.last_chat_payload()["options"]["num_ctx"] == 3072


# ---------------------------------------------------------------------------
# Attribute forwarding
# ---------------------------------------------------------------------------
class TestAttributeForwarding:
    def test_public_attributes_are_forwarded_to_hf(self, monkeypatch):
        enable_ollama(monkeypatch)

        class HfWithAttr:
            sentinel = "hf-value"

            def generate_with_fallback(self, *args, **kwargs):
                return {}

        wrapper = make_wrapper(FakeOllamaServer(), HfWithAttr())
        assert wrapper.sentinel == "hf-value"

    def test_private_names_raise_attribute_error(self, monkeypatch):
        """``__getattr__`` is the fallback, so it only sees *missing* names."""
        enable_ollama(monkeypatch)
        wrapper = make_wrapper(FakeOllamaServer())
        with pytest.raises(AttributeError):
            wrapper._this_name_does_not_exist

    def test_dunder_and_own_attributes_are_resolved_normally(self, monkeypatch):
        enable_ollama(monkeypatch)
        wrapper = make_wrapper(FakeOllamaServer())
        # set in __init__, so normal lookup wins and __getattr__ never runs
        assert wrapper.ollama_adapter is not None
        assert wrapper.circuit_state in {"CLOSED", "OPEN", "HALF_OPEN"}

    def test_circuit_state_is_none_without_a_breaker(self, monkeypatch):
        """Defensive contract: a missing breaker yields None, never an error."""
        enable_ollama(monkeypatch)
        wrapper = make_wrapper(FakeOllamaServer())
        saved = wrapper._breaker
        wrapper._breaker = None
        try:
            assert wrapper.circuit_state is None
        finally:
            wrapper._breaker = saved


# ---------------------------------------------------------------------------
# build_generation_adapter
# ---------------------------------------------------------------------------
class TestBuildGenerationAdapter:
    def test_disabled_returns_the_identical_hf_adapter(self, monkeypatch, caplog):
        import app.application.services.shared_router as shared_router_module

        hf = FakeHfAdapter()
        result = first_module.build_generation_adapter(hf)
        assert result is hf
        shared_router_module.reset_shared_state()

    def test_invalid_base_url_returns_the_plain_hf_adapter_and_logs_one_error(self, monkeypatch, caplog):
        enable_ollama(monkeypatch, ollama_base_url="ftp://nope")
        hf = FakeHfAdapter()

        with caplog.at_level("ERROR", logger="app.application.services.ollama_first_adapter"):
            result = first_module.build_generation_adapter(hf)

        assert result is hf
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(errors) == 1
        # the failure never leaks the configured base URL or a prompt
        assert "ftp://nope" not in errors[0].getMessage()
        assert "nope" not in errors[0].getMessage()

    def test_valid_config_returns_the_wrapper(self, monkeypatch):
        enable_ollama(monkeypatch)
        result = first_module.build_generation_adapter(FakeHfAdapter())
        assert isinstance(result, first_module.OllamaFirstAdapter)
        result.close()

    @pytest.mark.parametrize(
        ("label", "overrides", "expected_message"),
        [
            ("bad_scheme", {"ollama_base_url": "ftp://nope"}, "must use http or https"),
            ("no_host", {"ollama_base_url": "http://"}, "must include a hostname"),
            ("credentials", {"ollama_base_url": "http://u:p@host"}, "must not embed credentials"),
            ("empty_model", {"ollama_model": "   "}, "must not be empty"),
            ("zero_timeout", {"ollama_timeout_seconds": 0.0}, "must be positive"),
            ("bad_temperature", {"ollama_temperature": 3.0}, "between 0 and 2"),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_every_invalid_config_falls_back_to_plain_hf(self, monkeypatch, caplog, label, overrides, expected_message):
        enable_ollama(monkeypatch, **overrides)
        hf = FakeHfAdapter()

        with caplog.at_level("ERROR", logger="app.application.services.ollama_first_adapter"):
            result = first_module.build_generation_adapter(hf)

        assert result is hf
        assert len([r for r in caplog.records if r.levelname == "ERROR"]) == 1
        assert expected_message in caplog.records[0].getMessage()


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------
class TestConcurrency:
    def test_sixteen_threads_against_a_dead_ollama(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer([connect_refused()])
        hf = FakeHfAdapter()
        wrapper = make_wrapper(server, hf, sleep=RecordingSleep())

        workers = 16
        start = concurrent.futures.ThreadPoolExecutor  # noqa: F841 - documentation anchor
        barrier = __import__("threading").Barrier(workers)
        results: list[object] = []
        errors: list[BaseException] = []

        def call():
            barrier.wait()
            try:
                results.append(wrapper.generate_with_fallback(TASK, PROMPT, token_budget=BUDGET))
            except BaseException as exc:  # noqa: BLE001 - recorded, then asserted below
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda _: call(), range(workers)))

        assert errors == []
        assert len(results) == workers
        assert wrapper.circuit_state == "OPEN"
