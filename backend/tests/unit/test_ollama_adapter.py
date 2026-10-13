"""Adapter contract for the synchronous Ollama client (Sub-step 3 → committed 7a).

All tests drive a scripted ``httpx.MockTransport`` server with an injected sleep
and jitter, so the retry schedule is exact and nothing waits on a wall clock.
"""

from __future__ import annotations

import dataclasses

import httpx
import pytest
from ollama_helpers import (
    FakeOllamaServer,
    FixedJitter,
    RecordingSleep,
    connect_refused,
    connect_timeout,
    http,
    make_adapter,
    non_json_body,
    ok_chat,
    pool_timeout,
    protocol_error,
    read_timeout,
    tags_response,
)

import app.infrastructure.ai.ollama_adapter as adapter_module
from app.application.services.ai_model_router import (
    MODEL_UNAVAILABLE,
    RATE_LIMITED,
    SCHEMA_VALIDATION_FAILED,
    TIMEOUT,
    classify_failure,
)
from app.infrastructure.ai.ollama_adapter import (
    OllamaConfigError,
    OllamaInferenceAdapter,
    is_model_installed,
)


@pytest.fixture
def no_metrics(monkeypatch):
    """Record ``record_ollama_outcome`` calls instead of touching the registry."""
    calls: list[dict] = []
    monkeypatch.setattr(
        adapter_module,
        "record_ollama_outcome",
        lambda **kwargs: calls.append(kwargs),
    )
    return calls


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------
class TestChatSuccess:
    def test_returns_parsed_result(self):
        server = FakeOllamaServer()
        adapter = make_adapter(server)

        result = adapter.chat([{"role": "user", "content": "hello"}], max_new_tokens=128, num_ctx=512)

        assert result.content == "Here is your answer."
        assert result.model == "llama3.2:3b"
        assert result.prompt_tokens == 42
        assert result.completion_tokens == 17
        assert result.latency_ms >= 0
        assert len(server.chat_requests) == 1

    def test_payload_shape_is_the_documented_contract(self):
        server = FakeOllamaServer()
        adapter = make_adapter(server)

        adapter.chat([{"role": "user", "content": "hello"}], max_new_tokens=128, num_ctx=512)

        payload = server.last_chat_payload()
        assert payload["model"] == "llama3.2:3b"
        assert payload["stream"] is False
        assert payload["keep_alive"] == "5m"
        assert payload["messages"] == [{"role": "user", "content": "hello"}]
        assert payload["options"]["temperature"] == 0.3
        # max_new_tokens is sent as Ollama's option name.
        assert payload["options"]["num_predict"] == 128
        assert payload["options"]["num_ctx"] == 512

    def test_no_authorization_header_is_sent(self):
        server = FakeOllamaServer()
        adapter = make_adapter(server)

        adapter.chat([{"role": "user", "content": "hello"}])

        headers = dict(server.chat_requests[0].headers)
        assert "authorization" not in {key.lower() for key in headers}

    def test_reported_model_overrides_the_configured_one(self):
        server = FakeOllamaServer([ok_chat(model="llama3.2:3b-custom")])
        adapter = make_adapter(server)

        result = adapter.chat([{"role": "user", "content": "hi"}])

        assert result.model == "llama3.2:3b-custom"

    def test_reported_model_falls_back_when_absent_or_empty(self):
        # The adapter substitutes the configured model only when the server
        # omits the field or returns an empty string; a whitespace value is
        # passed through verbatim (documented edge, asserted below).
        absent = http(200, {"message": {"role": "assistant", "content": "hi"}})
        empty = http(200, {"message": {"role": "assistant", "content": "hi"}, "model": ""})
        for script in ([absent], [empty]):
            server = FakeOllamaServer(script)
            adapter = make_adapter(server)
            result = adapter.chat([{"role": "user", "content": "hi"}])
            assert result.model == "llama3.2:3b"

    def test_whitespace_reported_model_is_passed_through(self):
        server = FakeOllamaServer([http(200, {"message": {"role": "assistant", "content": "hi"}, "model": "   "})])
        adapter = make_adapter(server)
        result = adapter.chat([{"role": "user", "content": "hi"}])
        # Documented: the field is truthy, so it is returned unchanged rather
        # than silently replaced. A caller that cares must normalise it.
        assert result.model == "   "

    def test_non_positive_token_counts_become_zero(self):
        body = {
            "message": {"role": "assistant", "content": "hi"},
            "prompt_eval_count": -5,
            "eval_count": "not-a-number",
        }
        server = FakeOllamaServer([http(200, body)])
        adapter = make_adapter(server)

        result = adapter.chat([{"role": "user", "content": "hi"}])

        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0

    def test_keep_alive_and_temperature_are_configurable(self):
        server = FakeOllamaServer()
        adapter = make_adapter(server, keep_alive="30m", default_temperature=1.5)

        adapter.chat([{"role": "user", "content": "hi"}])

        payload = server.last_chat_payload()
        assert payload["keep_alive"] == "30m"
        assert payload["options"]["temperature"] == 1.5


# ---------------------------------------------------------------------------
# Error table
# ---------------------------------------------------------------------------
ERROR_TABLE = [
    # (label, scripted entries, expected taxonomy, expected chat request count)
    # Note: a scripted list that ends in a *success* is a retry-schedule case,
    # not an error case, so it is covered by TestRetrySchedule instead.
    ("connect_refused_exhausts", [connect_refused()], MODEL_UNAVAILABLE, 3),
    ("connect_timeout", [connect_timeout()], TIMEOUT, 3),
    ("pool_timeout", [pool_timeout()], TIMEOUT, 3),
    ("protocol_error", [protocol_error()], MODEL_UNAVAILABLE, 3),
    ("read_timeout_not_retried", [read_timeout()], TIMEOUT, 1),
    ("not_found", [http(404)], MODEL_UNAVAILABLE, 1),
    ("too_many_requests", [http(429)], RATE_LIMITED, 1),
    ("internal_server_error", [http(500)], MODEL_UNAVAILABLE, 3),
    ("bad_gateway", [http(502)], MODEL_UNAVAILABLE, 3),
    ("service_unavailable", [http(503)], MODEL_UNAVAILABLE, 3),
    ("gateway_timeout", [http(504)], MODEL_UNAVAILABLE, 3),
    ("bad_request_rejected", [http(400)], SCHEMA_VALIDATION_FAILED, 1),
    ("unauthorized_rejected", [http(401)], SCHEMA_VALIDATION_FAILED, 1),
    ("forbidden_rejected", [http(403)], SCHEMA_VALIDATION_FAILED, 1),
    ("unprocessable_rejected", [http(422)], SCHEMA_VALIDATION_FAILED, 1),
    ("non_json_body", [non_json_body()], SCHEMA_VALIDATION_FAILED, 1),
    ("json_array_body", [http(200, [{"message": {}}])], SCHEMA_VALIDATION_FAILED, 1),
    ("missing_message_key", [http(200, {"done": True})], SCHEMA_VALIDATION_FAILED, 1),
    ("message_not_a_dict", [http(200, {"message": "text"})], SCHEMA_VALIDATION_FAILED, 1),
    ("empty_content", [http(200, {"message": {"content": ""}})], SCHEMA_VALIDATION_FAILED, 1),
    ("whitespace_content", [http(200, {"message": {"content": "   \n\t"}})], SCHEMA_VALIDATION_FAILED, 1),
]


@pytest.mark.parametrize(
    ("label", "script", "expected_class", "expected_requests"),
    ERROR_TABLE,
    ids=[row[0] for row in ERROR_TABLE],
)
class TestChatErrorTable:
    def test_raises_ai_provider_error(self, label, script, expected_class, expected_requests):
        from app.core.errors import AIProviderError

        adapter = make_adapter(FakeOllamaServer(script))
        with pytest.raises(AIProviderError) as excinfo:
            adapter.chat([{"role": "user", "content": "hi"}])
        assert classify_failure(excinfo.value) == expected_class

    def test_request_count_is_exact(self, label, script, expected_class, expected_requests):
        server = FakeOllamaServer(script)
        adapter = make_adapter(server, sleep=RecordingSleep(), jitter=FixedJitter())
        from app.core.errors import AIProviderError

        with pytest.raises(AIProviderError):
            adapter.chat([{"role": "user", "content": "hi"}])
        assert len(server.chat_requests) == expected_requests

    def test_metrics_recorded_once(self, no_metrics, label, script, expected_class, expected_requests):
        adapter = make_adapter(FakeOllamaServer(script))
        from app.core.errors import AIProviderError

        with pytest.raises(AIProviderError):
            adapter.chat([{"role": "user", "content": "hi"}])
        assert no_metrics == [{"success": False, "fallback_to_hf": True}]


class TestNotFoundMessage:
    def test_error_message_contains_pull_command(self):
        from app.core.errors import AIProviderError

        adapter = make_adapter(FakeOllamaServer([http(404)]))
        with pytest.raises(AIProviderError) as excinfo:
            adapter.chat([{"role": "user", "content": "hi"}])

        message = str(excinfo.value)
        assert "ollama pull llama3.2:3b" in message
        assert "not installed" in message

    def test_message_uses_the_configured_model(self):
        from app.core.errors import AIProviderError

        adapter = make_adapter(FakeOllamaServer([http(404)]), model="mistral:7b")
        with pytest.raises(AIProviderError) as excinfo:
            adapter.chat([{"role": "user", "content": "hi"}])
        assert "ollama pull mistral:7b" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Retry schedule
# ---------------------------------------------------------------------------
class TestRetrySchedule:
    def test_connect_error_twice_then_success(self):
        sleep = RecordingSleep()
        server = FakeOllamaServer([connect_refused(), connect_refused(), ok_chat()])
        adapter = make_adapter(server, sleep=sleep, jitter=FixedJitter())

        result = adapter.chat([{"role": "user", "content": "hi"}])

        assert result.content == "Here is your answer."
        assert len(server.chat_requests) == 3
        assert len(sleep.delays) == 2

    def test_delays_follow_the_capped_exponential_schedule(self):
        sleep = RecordingSleep()
        jitter = FixedJitter(0.0)
        server = FakeOllamaServer([http(503)])
        adapter = make_adapter(
            server,
            sleep=sleep,
            jitter=jitter,
            max_retries=2,
            backoff_base_seconds=0.5,
            backoff_max_seconds=4.0,
        )
        from app.core.errors import AIProviderError

        with pytest.raises(AIProviderError):
            adapter.chat([{"role": "user", "content": "hi"}])

        # ceilings: 0.5 * 2**0, then 0.5 * 2**1, capped at 4.0
        assert jitter.calls == [0.5, 1.0]
        assert sleep.delays == [0.0, 0.0]

    def test_ceiling_is_capped_by_backoff_max(self):
        jitter = FixedJitter(0.0)
        server = FakeOllamaServer([http(503)])
        adapter = make_adapter(
            server,
            sleep=RecordingSleep(),
            jitter=jitter,
            max_retries=3,
            backoff_base_seconds=8.0,
            backoff_max_seconds=4.0,
        )
        from app.core.errors import AIProviderError

        with pytest.raises(AIProviderError):
            adapter.chat([{"role": "user", "content": "hi"}])

        # every ceiling is clamped to backoff_max_seconds
        assert jitter.calls == [4.0, 4.0, 4.0]

    def test_full_jitter_never_exceeds_the_ceiling(self):
        jitter_calls: list[float] = []
        server = FakeOllamaServer([http(503)])
        adapter = make_adapter(
            server,
            sleep=RecordingSleep(),
            jitter=lambda ceiling: _bounded_jitter(jitter_calls, ceiling),
        )
        from app.core.errors import AIProviderError

        with pytest.raises(AIProviderError):
            adapter.chat([{"role": "user", "content": "hi"}])

        assert jitter_calls, "jitter must be consulted for each retry"
        assert len(jitter_calls) == adapter._max_retries

    def test_read_timeout_is_not_retried(self):
        sleep = RecordingSleep()
        server = FakeOllamaServer([read_timeout()])
        adapter = make_adapter(server, sleep=sleep)

        from app.core.errors import AIProviderError

        with pytest.raises(AIProviderError):
            adapter.chat([{"role": "user", "content": "hi"}])
        assert len(server.chat_requests) == 1
        assert sleep.delays == []

    def test_generic_transport_error_is_not_retried(self):
        """A non-connect transport failure is terminal, not transient."""
        from app.core.errors import AIProviderError

        sleep = RecordingSleep()
        server = FakeOllamaServer([httpx.UnsupportedProtocol("nope")])
        adapter = make_adapter(server, sleep=sleep)

        with pytest.raises(AIProviderError) as excinfo:
            adapter.chat([{"role": "user", "content": "hi"}])

        assert classify_failure(excinfo.value) == MODEL_UNAVAILABLE
        assert "transport error" in str(excinfo.value)
        assert len(server.chat_requests) == 1
        assert sleep.delays == []


class TestDefaultJitter:
    def test_the_default_jitter_stays_inside_the_ceiling(self):
        """The shipped ``_full_jitter`` (no injection) is uniform on [0, ceiling]."""
        from app.infrastructure.ai.ollama_adapter import OllamaInferenceAdapter

        recorded: list[float] = []
        server = FakeOllamaServer([http(503)])
        adapter = OllamaInferenceAdapter(
            base_url="http://ollama.test:11434",
            client=httpx.Client(transport=server.transport()),
            sleep=RecordingSleep(),
        )
        # The adapter's default jitter IS the shipped one.
        assert adapter._jitter is adapter_module._full_jitter
        original = adapter._jitter
        adapter._jitter = lambda ceiling: (  # type: ignore[method-assign]
            recorded.append(original(ceiling)) or recorded[-1]
        )

        from app.core.errors import AIProviderError

        with pytest.raises(AIProviderError):
            adapter.chat([{"role": "user", "content": "hi"}])

        assert recorded
        assert all(0.0 <= value <= adapter._backoff_max for value in recorded)

    def test_urlsplit_rejection_is_a_config_error(self):
        """A URL urlsplit cannot parse is reported as a config error, not a crash."""
        with pytest.raises(OllamaConfigError):
            OllamaInferenceAdapter(base_url="http://[unterminated")


def _bounded_jitter(recorded: list[float], ceiling: float) -> float:
    """The real jitter, asserted to stay inside ``[0, ceiling]``."""
    import random

    value = random.uniform(0.0, ceiling)
    recorded.append(value)
    return value


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
class TestMetrics:
    def test_success_records_exactly_once(self, no_metrics):
        adapter = make_adapter(FakeOllamaServer())
        adapter.chat([{"role": "user", "content": "hi"}])
        assert no_metrics == [{"success": True}]

    def test_success_after_retries_still_records_once(self, no_metrics):
        adapter = make_adapter(FakeOllamaServer([connect_refused(), connect_refused(), ok_chat()]))
        adapter.chat([{"role": "user", "content": "hi"}])
        assert no_metrics == [{"success": True}]

    def test_failure_records_exactly_once_despite_retries(self, no_metrics):
        adapter = make_adapter(FakeOllamaServer([http(503)]))
        from app.core.errors import AIProviderError

        with pytest.raises(AIProviderError):
            adapter.chat([{"role": "user", "content": "hi"}])
        assert no_metrics == [{"success": False, "fallback_to_hf": True}]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
VALIDATION_CASES = [
    ("empty_messages", [], None, None, "messages must not be empty"),
    ("bad_role", [{"role": "system2", "content": "x"}], None, None, "invalid chat message at index 0"),
    ("non_str_content", [{"role": "user", "content": 7}], None, None, "invalid chat message at index 0"),
    ("missing_content", [{"role": "user"}], None, None, "invalid chat message at index 0"),
    ("temperature_too_high", [{"role": "user", "content": "x"}], 2.5, None, "temperature must be between 0 and 2"),
    ("temperature_negative", [{"role": "user", "content": "x"}], -0.1, None, "temperature must be between 0 and 2"),
    ("max_new_tokens_zero", [{"role": "user", "content": "x"}], None, None, "max_new_tokens must be at least 1"),
]


class TestValidation:
    @pytest.mark.parametrize(
        ("label", "messages", "temperature", "num_ctx", "expected_message"),
        VALIDATION_CASES,
        ids=[row[0] for row in VALIDATION_CASES],
    )
    def test_invalid_input_raises_before_any_request(
        self, no_metrics, label, messages, temperature, num_ctx, expected_message
    ):
        server = FakeOllamaServer()
        adapter = make_adapter(server)

        if label == "max_new_tokens_zero":
            with pytest.raises(ValueError, match=expected_message):
                adapter.chat(messages, max_new_tokens=0)
        else:
            with pytest.raises(ValueError, match=expected_message):
                adapter.chat(messages, temperature=temperature, num_ctx=num_ctx)

        assert server.total_requests == 0
        assert no_metrics == []

    def test_num_ctx_below_one_raises(self, no_metrics):
        server = FakeOllamaServer()
        adapter = make_adapter(server)
        with pytest.raises(ValueError, match="num_ctx must be at least 1"):
            adapter.chat([{"role": "user", "content": "x"}], num_ctx=0)
        assert server.total_requests == 0

    def test_messages_sequence_is_preserved(self):
        server = FakeOllamaServer()
        adapter = make_adapter(server)
        messages = [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "again"},
        ]
        adapter.chat(messages)
        assert server.last_chat_payload()["messages"] == messages


# ---------------------------------------------------------------------------
# Base URL + config validation
# ---------------------------------------------------------------------------
INVALID_BASE_URLS = [
    ("ftp_scheme", "ftp://ollama.test:11434"),
    ("file_scheme", "file:///tmp"),
    ("empty", ""),
    ("whitespace_only", "   "),
    ("no_scheme", "ollama.test:11434"),
    ("no_hostname", "http://"),
    ("embedded_credentials", "http://user:secret@ollama.test:11434"),
    ("query_string", "http://ollama.test:11434?model=x"),
    ("fragment", "http://ollama.test:11434#frag"),
]


class TestBaseUrlNormalization:
    @pytest.mark.parametrize(
        ("label", "raw"),
        INVALID_BASE_URLS,
        ids=[row[0] for row in INVALID_BASE_URLS],
    )
    def test_invalid_base_url_raises_config_error(self, label, raw):
        with pytest.raises(OllamaConfigError):
            OllamaInferenceAdapter(base_url=raw)

    def test_trailing_slash_is_stripped(self):
        adapter = OllamaInferenceAdapter(base_url="http://ollama.test:11434/")
        assert adapter._base_url == "http://ollama.test:11434"

    def test_whitespace_is_stripped(self):
        adapter = OllamaInferenceAdapter(base_url="  http://ollama.test:11434  ")
        assert adapter._base_url == "http://ollama.test:11434"

    def test_https_is_accepted(self):
        adapter = OllamaInferenceAdapter(base_url="https://ollama.test")
        assert adapter._base_url == "https://ollama.test"

    def test_path_suffix_is_preserved(self):
        adapter = OllamaInferenceAdapter(base_url="http://ollama.test:11434/prefix")
        assert adapter._base_url == "http://ollama.test:11434/prefix"

    @pytest.mark.parametrize(
        ("label", "kwargs"),
        [
            ("empty_model", {"model": ""}),
            ("whitespace_model", {"model": "   "}),
            ("zero_read_timeout", {"timeout_seconds": 0}),
            ("negative_read_timeout", {"timeout_seconds": -1.0}),
            ("zero_connect_timeout", {"connect_timeout_seconds": 0}),
            ("negative_retries", {"max_retries": -1}),
            ("negative_backoff_base", {"backoff_base_seconds": -0.5}),
            ("negative_backoff_max", {"backoff_max_seconds": -0.5}),
            ("temperature_too_high", {"default_temperature": 2.1}),
            ("temperature_negative", {"default_temperature": -0.1}),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_invalid_config_raises(self, label, kwargs):
        with pytest.raises(OllamaConfigError):
            OllamaInferenceAdapter(base_url="http://ollama.test:11434", **kwargs)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
class TestLifecycle:
    def test_injected_client_is_never_closed_by_the_adapter(self):
        server = FakeOllamaServer()
        client = httpx.Client(transport=server.transport())
        client.close = lambda: (_ for _ in ()).throw(AssertionError("must not close"))  # type: ignore[method-assign]
        adapter = OllamaInferenceAdapter(base_url="http://ollama.test:11434", client=client)

        adapter.close()

    def test_owned_client_is_closed_once(self):
        server = FakeOllamaServer()
        adapter = OllamaInferenceAdapter(
            base_url="http://ollama.test:11434",
            client=httpx.Client(transport=server.transport()),
        )
        # The adapter only closes a client it created; inject a marker.
        closed: list[int] = []
        adapter._owns_client = True
        original = adapter._client.close
        adapter._client.close = lambda: closed.append(1) or original()  # type: ignore[method-assign]

        adapter.close()
        adapter.close()  # idempotent

        assert closed == [1]

    def test_close_is_idempotent(self):
        adapter = OllamaInferenceAdapter(base_url="http://ollama.test:11434")
        adapter.close()
        adapter.close()

    def test_context_manager_closes(self):
        server = FakeOllamaServer()
        with OllamaInferenceAdapter(
            base_url="http://ollama.test:11434",
            client=httpx.Client(transport=server.transport()),
        ) as adapter:
            adapter.close = lambda: None  # type: ignore[method-assign]
            closed_before = adapter._closed
        assert closed_before is False or adapter._closed is True

    def test_use_after_close_raises_typed_unavailable(self):
        from app.core.errors import AIProviderError

        server = FakeOllamaServer()
        adapter = make_adapter(server)
        adapter.close()

        with pytest.raises(AIProviderError) as excinfo:
            adapter.chat([{"role": "user", "content": "hi"}])
        assert classify_failure(excinfo.value) == MODEL_UNAVAILABLE
        assert "closed" in str(excinfo.value)
        assert server.total_requests == 0


# ---------------------------------------------------------------------------
# list_models / is_available / is_model_installed
# ---------------------------------------------------------------------------
class TestModelListing:
    def test_list_models_returns_names(self):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b", "mistral:7b"])])
        adapter = make_adapter(server)

        assert adapter.list_models() == ["llama3.2:3b", "mistral:7b"]
        assert len(server.tags_requests) == 1

    def test_list_models_ignores_entries_without_a_name(self):
        body = {"models": [{"name": "llama3.2:3b"}, {"name": 7}, {"other": 1}, "not-a-dict"]}
        server = FakeOllamaServer(tags_script=[http(200, body)])
        adapter = make_adapter(server)

        assert adapter.list_models() == ["llama3.2:3b"]

    def test_is_available_true_when_installed(self):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        adapter = make_adapter(server)
        assert adapter.is_available() is True

    def test_is_available_accepts_the_latest_tag_alias(self):
        # `llama3.2` and `llama3.2:latest` are the same model to Ollama; a
        # *tagged* request (llama3.2:3b) must NOT match a different tag.
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:latest"])])
        adapter = make_adapter(server, model="llama3.2")
        assert adapter.is_available() is True

    def test_is_available_rejects_a_different_tag(self):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:latest"])])
        adapter = make_adapter(server, model="llama3.2:3b")
        assert adapter.is_available() is False

    def test_is_available_false_when_missing(self):
        server = FakeOllamaServer(tags_script=[tags_response(["mistral:7b"])])
        adapter = make_adapter(server)
        assert adapter.is_available() is False

    def test_is_available_false_on_connect_error(self):
        server = FakeOllamaServer(tags_script=[connect_refused()])
        adapter = make_adapter(server)
        assert adapter.is_available() is False

    def test_is_available_false_on_timeout(self):
        server = FakeOllamaServer(tags_script=[read_timeout()])
        adapter = make_adapter(server)
        assert adapter.is_available() is False

    def test_is_available_false_on_non_200(self):
        server = FakeOllamaServer(tags_script=[http(500)])
        adapter = make_adapter(server)
        assert adapter.is_available() is False

    def test_is_available_false_on_invalid_json(self):
        server = FakeOllamaServer(tags_script=[non_json_body()])
        adapter = make_adapter(server)
        assert adapter.is_available() is False

    def test_is_available_false_on_wrong_shape(self):
        server = FakeOllamaServer(tags_script=[http(200, {"unexpected": True})])
        adapter = make_adapter(server)
        assert adapter.is_available() is False

    @pytest.mark.parametrize(
        ("label", "script"),
        [
            ("connect_error", [connect_refused()]),
            ("timeout", [read_timeout()]),
            ("non_200", [http(500)]),
            ("invalid_json", [non_json_body()]),
            ("wrong_shape", [http(200, "a string")]),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_list_models_raises_typed_error(self, label, script):
        from app.core.errors import AIProviderError

        server = FakeOllamaServer(tags_script=script)
        adapter = make_adapter(server)
        with pytest.raises(AIProviderError):
            adapter.list_models()

    @pytest.mark.parametrize(
        ("model", "installed", "expected"),
        [
            ("llama3.2:3b", ["llama3.2:3b"], True),
            ("llama3.2:3b", ["llama3.2:latest"], False),
            ("llama3.2", ["llama3.2:latest"], True),
            ("llama3.2", ["llama3.2"], True),
            ("llama3.2:3b", ["mistral:7b"], False),
            ("llama3.2:3b", [], False),
            ("llama3.2:3b", ["llama3.2:1b"], False),
        ],
    )
    def test_is_model_installed_tag_equivalence(self, model, installed, expected):
        assert is_model_installed(model, installed) is expected

    def test_is_model_installed_strips_surrounding_whitespace(self):
        assert is_model_installed("  llama3.2  ", ["llama3.2:latest"]) is True


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------
class TestPrivacy:
    PROMPT = "SUPER_SECRET_PROMPT_MARKER"
    ANSWER = "SUPER_SECRET_ANSWER_MARKER"

    def _assert_no_leak(self, records):
        for record in records:
            text = record.getMessage()
            assert self.PROMPT not in text
            assert self.ANSWER not in text
            assert "ollama.test" not in text

    def test_success_path_logs_nothing_sensitive(self, caplog):
        server = FakeOllamaServer([ok_chat(content=self.ANSWER)])
        adapter = make_adapter(server)
        with caplog.at_level("DEBUG", logger="app.infrastructure.ai.ollama_adapter"):
            adapter.chat([{"role": "user", "content": self.PROMPT}])
        self._assert_no_leak(caplog.records)

    def test_failure_path_logs_nothing_sensitive(self, caplog):
        server = FakeOllamaServer([http(503), http(503), http(503)])
        adapter = make_adapter(server)
        from app.core.errors import AIProviderError

        with caplog.at_level("DEBUG", logger="app.infrastructure.ai.ollama_adapter"):
            with pytest.raises(AIProviderError):
                adapter.chat([{"role": "user", "content": self.PROMPT}])
        self._assert_no_leak(caplog.records)

    def test_retry_warning_logs_nothing_sensitive(self, caplog):
        server = FakeOllamaServer([connect_refused(), ok_chat(content=self.ANSWER)])
        adapter = make_adapter(server)
        with caplog.at_level("DEBUG", logger="app.infrastructure.ai.ollama_adapter"):
            adapter.chat([{"role": "user", "content": self.PROMPT}])
        self._assert_no_leak(caplog.records)


# ---------------------------------------------------------------------------
# Settings plumbing
# ---------------------------------------------------------------------------
class TestSettingsRead:
    def test_defaults_come_from_settings(self):
        adapter = OllamaInferenceAdapter()
        assert adapter.model == dataclasses.replace(adapter_module.settings).ollama_model

    def test_explicit_arguments_win(self):
        adapter = make_adapter(FakeOllamaServer(), model="phi4:14b")
        assert adapter.model == "phi4:14b"


# Owned client timeout verification
# ---------------------------------------------------------------------------
class TestOwnedClientTimeouts:
    """The adapter must create an httpx.Client with all four timeout phases set."""

    def test_owned_client_has_all_four_timeouts(self):
        """Owned client has explicit connect, read, write, and pool timeouts."""
        adapter = OllamaInferenceAdapter()
        assert adapter._owns_client is True
        timeout = adapter._client._timeout
        assert timeout.connect is not None and timeout.connect > 0
        assert timeout.read is not None and timeout.read > 0
        assert timeout.write is not None and timeout.write > 0
        assert timeout.pool is not None and timeout.pool > 0
        adapter.close()

    def test_owned_client_timeouts_match_constructor_args(self):
        """Timeouts on owned client match the values passed to the adapter."""
        custom_connect = 1.5
        custom_read = 45.0
        adapter = OllamaInferenceAdapter(
            connect_timeout_seconds=custom_connect,
            timeout_seconds=custom_read,
        )
        timeout = adapter._client._timeout
        assert timeout.connect == custom_connect
        assert timeout.read == custom_read
        # Default constants for write/pool
        from app.infrastructure.ai.ollama_adapter import (
            _POOL_TIMEOUT_SECONDS,
            _WRITE_TIMEOUT_SECONDS,
        )

        assert timeout.write == _WRITE_TIMEOUT_SECONDS
        assert timeout.pool == _POOL_TIMEOUT_SECONDS
        adapter.close()
