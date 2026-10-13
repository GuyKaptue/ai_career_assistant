"""Informational status probe contract (Sub-step 5 → committed 7a).

The probe must be cheap (TTT-cached), thread-safe, never raise, never mutate the
breaker, and never carry the base URL or any content into its result.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import json
import threading

import httpx
import pytest
from ollama_helpers import (
    FakeOllamaServer,
    RecordingClock,
    connect_refused,
    http,
    make_wrapper,
    non_json_body,
    tags_response,
)

import app.application.services.ollama_status_probe as probe_module
import app.application.services.shared_router as shared_router_module
from app.infrastructure.ai.ollama_adapter import OllamaConfigError

#: Exactly the keys the readiness payload publishes (no base URL, no content).
CHECK_KEYS = {"enabled", "reachable", "model", "model_installed", "circuit", "latency_ms"}


class _FakeSettings:
    """Minimal settings stand-in; only the fields the probe reads are set."""

    def __init__(self, *, use_ollama: bool = True, model: str | None = "llama3.2:3b") -> None:
        self.use_ollama = use_ollama
        self.ollama_model = model


class _DeadServer:
    """An adapter-shaped object whose listing always fails."""

    def list_models(self):
        raise httpx.ConnectError("no server")

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _clean_probe():
    """Drop any cached probe so each test builds its own."""
    probe_module.reset_probe_cache()
    yield
    probe_module.reset_probe_cache()
    shared_router_module.reset_shared_state()


def _make_probe(server, *, use_ollama: bool = True, clock=None, ttl: float = 5.0, model: str = "llama3.2:3b"):
    """A probe bound to a wrapper around the scripted server."""
    wrapper = make_wrapper(server)

    class _Settings:
        pass

    st = _Settings()
    st.use_ollama = use_ollama  # type: ignore[attr-defined]
    st.ollama_model = model  # type: ignore[attr-defined]

    return probe_module.OllamaStatusProbe(
        settings_obj=st,  # type: ignore[arg-type]
        adapter_getter=lambda: wrapper,
        circuit_state=lambda: wrapper.circuit_state,
        cache_ttl_seconds=ttl,
        clock=clock or RecordingClock(),
    )


# ---------------------------------------------------------------------------
# Disabled
# ---------------------------------------------------------------------------
class TestDisabled:
    def _probe(self):
        """A probe with Ollama off; no adapter is ever built."""

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = False  # type: ignore[attr-defined]
        st.ollama_model = "llama3.2:3b"  # type: ignore[attr-defined]
        return probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: (_ for _ in ()).throw(AssertionError("must not build")),
            circuit_state=lambda: None,
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
        )

    def test_no_adapter_is_built_and_all_fields_none(self):
        # adapter_getter raises, so any attempt to build one fails the test.
        probe = self._probe()
        status = probe.current()
        assert status.enabled is False
        assert status.reachable is None
        assert status.model is None
        assert status.model_installed is None
        assert status.circuit is None
        assert status.latency_ms is None

    def test_as_check_has_exactly_the_documented_keys(self):
        assert set(self._probe().current().as_check()) == CHECK_KEYS


# ---------------------------------------------------------------------------
# Up / reachable states
# ---------------------------------------------------------------------------
class TestReachable:
    def test_up_and_model_installed(self):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        probe = _make_probe(server)

        status = probe.current()

        assert (status.enabled, status.reachable, status.model_installed) == (True, True, True)
        assert status.model == "llama3.2:3b"
        assert status.circuit == "closed"
        assert status.latency_ms == 0 or isinstance(status.latency_ms, int)
        assert len(server.tags_requests) == 1

    def test_up_but_model_missing(self):
        server = FakeOllamaServer(tags_script=[tags_response(["mistral:7b"])])
        probe = _make_probe(server)

        status = probe.current()

        assert status.reachable is True
        assert status.model_installed is False
        assert status.circuit == "closed"

    def test_tag_alias_matches(self):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:latest"])])
        probe = _make_probe(server, model="llama3.2")
        assert probe.current().model_installed is True

    def test_connect_error(self):
        server = FakeOllamaServer(tags_script=[connect_refused()])
        probe = _make_probe(server)

        status = probe.current()

        assert status.enabled is True
        assert status.reachable is False
        assert status.model_installed is None
        assert status.latency_ms is None
        # The pre-flight contract: circuit is null ONLY when disabled.
        assert status.circuit == "closed"

    def test_circuit_is_reported_even_when_unreachable_and_open(self):
        """Breaker state is observable regardless of reachability."""

        server = FakeOllamaServer(tags_script=[connect_refused()])
        probe = _make_probe(server)
        # Trip the wrapper's breaker behind the probe's back.
        probe._adapter_getter()._breaker._state = "OPEN"

        status = probe.current()

        assert status.reachable is False
        assert status.circuit == "open"

    def test_circuit_is_reported_when_no_model_is_configured(self):
        server = FakeOllamaServer(tags_script=[connect_refused()])
        wrapper = make_wrapper(server)

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = ""  # type: ignore[attr-defined]
        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: wrapper,
            circuit_state=lambda: wrapper.circuit_state,
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
        )

        status = probe.current()

        assert status.model is None
        assert status.circuit == "closed"
        assert status.reachable is False

    def test_reachable_with_no_configured_model_is_reported(self):
        """Reachable but nothing to compare: installed stays unknown, circuit is set."""
        wrapper = make_wrapper(FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])]))

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = ""  # type: ignore[attr-defined]
        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: wrapper,
            circuit_state=lambda: wrapper.circuit_state,
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
        )

        status = probe.current()

        assert status.reachable is True
        assert status.model is None
        assert status.model_installed is None
        assert status.circuit == "closed"

    def test_absent_circuit_getter_reports_none(self):
        probe = probe_module.OllamaStatusProbe(
            settings_obj=_FakeSettings(use_ollama=True),  # type: ignore[arg-type]
            adapter_getter=lambda: object(),
            circuit_state=None,
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
            adapter_factory=lambda **kw: _DeadServer(),
        )
        assert probe._read_circuit_state() is None
        assert probe.current().circuit is None

    @pytest.mark.parametrize("script", [connect_refused(), httpx.ReadTimeout("x"), http(500)])
    def test_circuit_is_present_for_every_failure_mode(self, script):
        server = FakeOllamaServer(tags_script=[script])
        probe = _make_probe(server)
        status = probe.current()
        assert status.enabled is True
        assert status.circuit in {"closed", "open", "half_open"}

    def test_read_timeout(self):
        server = FakeOllamaServer(tags_script=[httpx.ReadTimeout("x")])
        probe = _make_probe(server)
        assert probe.current().reachable is False

    def test_invalid_json(self):
        server = FakeOllamaServer(tags_script=[non_json_body()])
        probe = _make_probe(server)
        assert probe.current().reachable is False

    def test_wrong_shape(self):
        server = FakeOllamaServer(tags_script=[http(200, {"nope": True})])
        probe = _make_probe(server)
        status = probe.current()
        assert status.reachable is False
        assert status.model_installed is None

    def test_does_not_mutate_breaker_state(self):
        from ollama_helpers import FakeHfAdapter, make_adapter

        from app.application.services.ollama_first_adapter import OllamaFirstAdapter

        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        wrapper = OllamaFirstAdapter(FakeHfAdapter(), make_adapter(server))
        # Trip the breaker by hand, then probe.
        wrapper._breaker._state = "OPEN"
        wrapper._breaker._failure_count = 7

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = "llama3.2:3b"  # type: ignore[attr-defined]
        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: wrapper,
            circuit_state=lambda: wrapper.circuit_state,
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
        )

        status = probe.current()

        # The probe reports the open breaker but does not change it.
        assert status.circuit == "open"
        assert wrapper.circuit_state == "OPEN"
        assert wrapper._breaker._failure_count == 7


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
class TestCache:
    def test_two_calls_inside_the_ttl_make_one_request(self):
        clock = RecordingClock()
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        probe = _make_probe(server, clock=clock)

        first = probe.current()
        second = probe.current()

        assert first is second  # the same frozen dataclass instance
        assert len(server.tags_requests) == 1

    def test_re_probes_after_the_ttl(self):
        clock = RecordingClock()
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        probe = _make_probe(server, clock=clock)

        probe.current()
        clock.advance(4.0)
        probe.current()
        assert len(server.tags_requests) == 1

        clock.advance(2.0)  # 6 s total, past the 5 s TTL
        probe.current()
        assert len(server.tags_requests) == 2

    def test_invalidate_forces_a_re_probe(self):
        clock = RecordingClock()
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        probe = _make_probe(server, clock=clock)

        probe.current()
        probe.invalidate()
        probe.current()
        assert len(server.tags_requests) == 2

    def test_cache_is_thread_safe(self):
        clock = RecordingClock()
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        probe = _make_probe(server, clock=clock)
        workers = 16
        barrier = threading.Barrier(workers)
        results = []

        def call():
            barrier.wait()
            results.append(probe.current())

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda _: call(), range(workers)))

        assert len(results) == workers
        assert len(server.tags_requests) == 1

    def test_reset_shared_state_clears_the_module_probe(self):
        assert probe_module._probe is None
        shared_router_module.reset_shared_state()
        assert probe_module._probe is None
        # after the fixture, get_ollama_status() rebuilds lazily; make sure the
        # public helper does not raise when nothing has been configured.
        status = probe_module.get_ollama_status()
        assert isinstance(status, probe_module.OllamaStatus)


# ---------------------------------------------------------------------------
# Invalid config
# ---------------------------------------------------------------------------
class TestInvalidConfig:
    def test_enabled_false_and_one_error_log(self, caplog):
        """A misconfigured channel logs exactly once, then stays quiet."""

        def bad_factory(**kwargs):
            raise OllamaConfigError("ollama base url must use http or https")

        shared_router_module.set_adapter_for_testing(object())  # a non-wrapper

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = "llama3.2:3b"  # type: ignore[attr-defined]

        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: object(),
            circuit_state=lambda: None,
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
            adapter_factory=bad_factory,
        )

        with caplog.at_level("ERROR", logger="app.application.services.ollama_status_probe"):
            status = None
            for _ in range(4):
                status = probe.current()
                probe.invalidate()

        assert status.enabled is False
        assert status.reachable is None
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(errors) == 1, "a misconfigured channel must log exactly once"

    def test_config_error_message_does_not_leak_the_url(self, caplog):
        def bad_factory(**kwargs):
            raise OllamaConfigError("ollama base url must use http or https")

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = "x"  # type: ignore[attr-defined]

        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: object(),
            circuit_state=lambda: None,
            adapter_factory=bad_factory,
            clock=RecordingClock(),
        )
        with caplog.at_level("ERROR", logger="app.application.services.ollama_status_probe"):
            probe.current()
        message = caplog.records[0].getMessage()
        # The reason is reported, but never an actual URL or host.
        assert "must use http or https" in message
        assert "://" not in message
        assert "ollama.test" not in message


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------
class TestNeverRaises:
    @pytest.mark.parametrize(
        ("label", "script"),
        [
            ("connect_error", [connect_refused()]),
            ("http_500", [http(500)]),
            ("timeout", [httpx.ReadTimeout("x")]),
            ("protocol_error", [httpx.RemoteProtocolError("x")]),
            ("pool_timeout", [httpx.PoolTimeout("x")]),
            ("http_404", [http(404)]),
            ("bad_json", [non_json_body()]),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_any_failure_returns_a_status(self, label, script):
        server = FakeOllamaServer(tags_script=script)
        probe = _make_probe(server)
        status = probe.current()
        assert isinstance(status, probe_module.OllamaStatus)
        assert status.enabled is True

    def test_as_check_is_json_serialisable_and_leak_free(self):
        server = FakeOllamaServer(tags_script=[connect_refused()])
        probe = _make_probe(server)
        blob = json.dumps(probe.current().as_check())
        assert "ollama.test" not in blob
        assert "localhost" not in blob
        assert "11434" not in blob
        assert set(json.loads(blob)) == CHECK_KEYS

    def test_no_prompt_or_content_in_the_payload(self):
        server = FakeOllamaServer(tags_script=[tags_response(["secret-model-name-xyz"])])
        probe = _make_probe(server)
        payload = probe.current().as_check()
        # Only the configured model name is reported, never a completion.
        assert payload["model"] == "llama3.2:3b"


# ---------------------------------------------------------------------------
# Cached instance identity / dataclass contract
# ---------------------------------------------------------------------------
class TestStatusDataclass:
    def test_is_frozen_and_hashable(self):
        status = probe_module.OllamaStatus(enabled=False)
        with pytest.raises(dataclasses.FrozenInstanceError):
            status.enabled = True  # type: ignore[misc]
        assert hash(status) is not None

    def test_cold_start_reports_a_closed_circuit(self):
        """The pre-flight contract: circuit is null only when disabled."""
        probe = _make_probe(FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])]))
        status = probe.current()
        assert status.circuit is not None
        assert status.circuit in {"closed", "open", "half_open"}


class TestConstructionAndAccessors:
    def test_negative_ttl_is_rejected(self):
        with pytest.raises(ValueError, match="must not be negative"):
            probe_module._StatusCache(-1.0, RecordingClock())

    def test_cache_ttl_is_readable(self):
        probe = _make_probe(FakeOllamaServer(), ttl=7.5)
        assert probe.cache_ttl_seconds == 7.5

    def test_configure_probe_none_removes_an_installed_probe(self):
        probe = _make_probe(FakeOllamaServer())
        probe_module.configure_probe(probe)
        assert probe_module._probe is probe
        probe_module.configure_probe(None)
        assert probe_module._probe is None

    def test_get_ollama_status_works_with_no_probe_configured(self):
        """The public helper must work without anything ever being configured."""
        probe_module.reset_probe_cache()
        assert probe_module._probe is None
        status = probe_module.get_ollama_status()
        assert isinstance(status, probe_module.OllamaStatus)
        # a probe instance is now installed for later callers
        assert isinstance(probe_module._probe, probe_module.OllamaStatusProbe)

    def test_get_ollama_status_reuses_an_installed_probe(self):
        probe = _make_probe(FakeOllamaServer(), ttl=9.0)
        probe_module.configure_probe(probe)
        try:
            status = probe_module.get_ollama_status()
            assert isinstance(status, probe_module.OllamaStatus)
            assert probe_module._probe is probe
        finally:
            probe_module.configure_probe(None)

    def test_cold_start_probes_ollama_once_per_ttl(self, monkeypatch):
        """Regression: a cold start must still honour the TTL cache.

        On a cold start the probe's *first* run resolves the shared generation
        adapter. Building that adapter calls ``reset_probe_cache``, which
        dropped the probe installed a moment earlier, so every call rebuilt a
        probe with a fresh cache and hammered Ollama once per health check.

        This walks the real ``get_ollama_status()`` path with an adapter that
        behaves exactly like the one the cold start builds.
        """
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        wrapper = make_wrapper(server)
        monkeypatch.setattr(probe_module, "_settings", lambda: _FakeSettings())

        def fake_build(hf_adapter):
            # What the real build_generation_adapter does before returning.
            probe_module.reset_probe_cache()
            return wrapper

        monkeypatch.setattr(shared_router_module, "build_generation_adapter", fake_build)
        monkeypatch.setattr(shared_router_module, "_adapter", None, raising=False)

        probe_module.reset_probe_cache()
        assert probe_module._probe is None

        first = probe_module.get_ollama_status()
        upstream_after_first = len(server.tags_requests)
        second = probe_module.get_ollama_status()

        # Both calls returned a usable status...
        assert isinstance(first, probe_module.OllamaStatus)
        assert isinstance(second, probe_module.OllamaStatus)
        # ...and reached Ollama exactly once, not once per call.
        assert upstream_after_first == 1
        assert len(server.tags_requests) == 1
        assert probe_module._probe is probe_module._probe

    def test_configured_model_reports_none_when_absent(self):
        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = None  # type: ignore[attr-defined]
        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: object(),
            circuit_state=lambda: None,
            clock=RecordingClock(),
        )
        assert probe._configured_model() is None

    def test_whitespace_model_is_returned_verbatim(self):
        """A whitespace-only model is truthy, so it is reported as configured.

        The adapter itself rejects it at construction time, so the probe never
        has to guess what a blank model means."""

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = "   "  # type: ignore[attr-defined]
        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: object(),
            circuit_state=lambda: None,
            clock=RecordingClock(),
        )
        assert probe._configured_model() == "   "


class TestCircuitGetterForms:
    def test_callable_and_value_forms_are_both_accepted(self):
        """A wrapper exposes a property (value); a test may pass a callable."""
        for state, expected in (("CLOSED", "closed"), ("OPEN", "open"), ("HALF_OPEN", "half_open")):
            assert probe_module._circuit_name(state) == expected
        assert probe_module._circuit_name("nonsense") is None
        assert probe_module._circuit_name(None) is None

    def test_default_probe_reads_a_property_not_a_callable(self, monkeypatch):
        """A wrapper exposes `circuit_state` as a *property*: a plain string."""
        monkeypatch.setattr(probe_module, "_settings", lambda: _FakeSettings())

        class Wrapper:
            circuit_state = "OPEN"

        shared_router_module.set_adapter_for_testing(Wrapper())  # type: ignore[arg-type]
        probe = probe_module._default_probe()
        assert probe._read_circuit_state() == "OPEN"
        status = probe.current()
        assert status.circuit == "open"


class TestProbeResilience:
    def test_adapter_getter_raising_is_survived(self):
        """A broken shared adapter must not crash readiness."""

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = "llama3.2:3b"  # type: ignore[attr-defined]

        def boom():
            raise RuntimeError("adapter is half-initialised")

        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=boom,
            circuit_state=lambda: "CLOSED",
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
        )
        status = probe.current()
        assert status.enabled is True
        assert status.reachable is False
        assert status.circuit == "closed"

    def test_circuit_getter_raising_is_survived(self):
        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = "llama3.2:3b"  # type: ignore[attr-defined]

        def boom():
            raise RuntimeError("breaker unreadable")

        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: object(),  # not a wrapper -> factory path
            circuit_state=boom,
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
            adapter_factory=lambda **kw: _DeadAdapter(),
        )

        def _DeadAdapter():
            class _A:
                def list_models(self):
                    raise httpx.ConnectError("down")

            return _A()

        status = probe.current()
        assert status.reachable is False
        # an unreadable breaker is reported as unknown rather than crashing
        assert status.circuit is None

    def test_late_config_error_after_connect(self):
        """A config error surfacing during the probe disables the channel."""

        class _Settings:
            pass

        st = _Settings()
        st.use_ollama = True  # type: ignore[attr-defined]
        st.ollama_model = "llama3.2:3b"  # type: ignore[attr-defined]

        from app.infrastructure.ai.ollama_adapter import OllamaConfigError

        class LateError:
            def list_models(self):
                raise OllamaConfigError("ollama base url must use http or https")

            def close(self):
                pass

        probe = probe_module.OllamaStatusProbe(
            settings_obj=st,  # type: ignore[arg-type]
            adapter_getter=lambda: object(),
            circuit_state=lambda: None,
            cache_ttl_seconds=5.0,
            clock=RecordingClock(),
            adapter_factory=lambda **kw: LateError(),
        )
        status = probe.current()
        assert status.enabled is False
        assert status.reachable is None
