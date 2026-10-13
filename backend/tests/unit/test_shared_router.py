"""Shared generation-adapter singleton contract (Sub-step 5 → committed 7a).

The process keeps one router and one adapter so connection pools, the circuit
breaker and the status probe are shared rather than rebuilt per call.
"""

from __future__ import annotations

import httpx
import pytest
from ollama_helpers import FakeHfAdapter, FakeOllamaServer, enable_ollama, make_adapter

import app.application.services.ollama_status_probe as probe_module
import app.application.services.shared_router as shared_router_module
from app.application.services.ollama_first_adapter import OllamaFirstAdapter


@pytest.fixture(autouse=True)
def _reset():
    shared_router_module.reset_shared_state()
    yield
    shared_router_module.reset_shared_state()


class TestUseOllamaDisabled:
    def test_get_adapter_returns_the_plain_hf_adapter(self, monkeypatch):
        hf = FakeHfAdapter()
        monkeypatch.setattr(shared_router_module, "build_generation_adapter", lambda _: hf)

        assert shared_router_module.get_adapter() is hf

    def test_adapter_is_cached(self, monkeypatch):
        hf = FakeHfAdapter()
        monkeypatch.setattr(shared_router_module, "build_generation_adapter", lambda _: hf)
        assert shared_router_module.get_adapter() is shared_router_module.get_adapter() is hf


class TestUseOllamaEnabled:
    def test_get_adapter_returns_the_wrapper(self, monkeypatch):
        enable_ollama(monkeypatch)
        server = FakeOllamaServer()
        monkeypatch.setattr(
            shared_router_module,
            "build_generation_adapter",
            lambda hf: OllamaFirstAdapter(hf, make_adapter(server)),
        )
        adapter = shared_router_module.get_adapter()
        assert isinstance(adapter, OllamaFirstAdapter)
        adapter.close()

    def test_get_router_is_shared(self, monkeypatch):
        """The router is built once and reused, so discovery is not repeated."""
        built: list[int] = []
        original = shared_router_module.get_router

        def counting_router():
            built.append(1)
            return original()

        monkeypatch.setattr(shared_router_module, "get_router", counting_router)
        # No caching: the wrapper is a thin accessor over module state.
        first = shared_router_module.get_router()
        second = shared_router_module.get_router()
        assert first is second


class TestSetAdapterForTesting:
    def test_installs_the_adapter(self):
        sentinel = FakeHfAdapter()
        result = shared_router_module.set_adapter_for_testing(sentinel)
        assert shared_router_module.get_adapter() is sentinel
        assert result is None  # a setter, not a builder

    def test_overrides_the_cached_adapter(self):
        shared_router_module.get_adapter()
        fake = FakeHfAdapter()
        shared_router_module.set_adapter_for_testing(fake)
        assert shared_router_module.get_adapter() is fake

    def test_none_removes_the_override(self):
        fake = FakeHfAdapter()
        shared_router_module.set_adapter_for_testing(fake)
        shared_router_module.set_adapter_for_testing(None)
        # get_adapter() now builds lazily from settings.
        assert shared_router_module.get_adapter() is not fake

    def test_set_router_for_testing_installs_and_clears(self):
        from app.application.services.ai_model_router import HuggingFaceModelRouter

        sentinel = HuggingFaceModelRouter()
        shared_router_module.set_router_for_testing(sentinel)
        assert shared_router_module.get_router() is sentinel
        shared_router_module.set_router_for_testing(None)
        assert shared_router_module.get_router() is not sentinel


class TestResetSharedState:
    def test_clears_adapter_and_router(self, monkeypatch):
        fake = FakeHfAdapter()
        shared_router_module.set_adapter_for_testing(fake)
        shared_router_module._router = object()  # noqa: SLF001 - seeding state for the test
        shared_router_module.reset_shared_state()
        assert shared_router_module._adapter is None
        assert shared_router_module._router is None

    def test_closes_a_wrapper_adapter(self, monkeypatch):
        enable_ollama(monkeypatch)
        closed: list[int] = []
        wrapper = OllamaFirstAdapter(FakeHfAdapter(), make_adapter(FakeOllamaServer()))
        monkeypatch.setattr(wrapper, "close", lambda: closed.append(1))
        shared_router_module.set_adapter_for_testing(wrapper)

        shared_router_module.reset_shared_state()

        assert closed == [1]

    def test_does_not_fail_on_a_non_wrapper_adapter(self):
        shared_router_module.set_adapter_for_testing(FakeHfAdapter())
        shared_router_module.reset_shared_state()  # must not raise

    def test_resets_the_probe_cache(self):
        shared_router_module.reset_shared_state()
        assert probe_module._probe is None

    def test_is_safe_to_call_twice(self):
        shared_router_module.reset_shared_state()
        shared_router_module.reset_shared_state()
        assert shared_router_module._adapter is None

    def test_close_failure_does_not_propagate(self, monkeypatch):
        def boom():
            raise RuntimeError("client already closed")

        wrapper = OllamaFirstAdapter(FakeHfAdapter(), make_adapter(FakeOllamaServer()))
        monkeypatch.setattr(wrapper, "close", boom)
        shared_router_module.set_adapter_for_testing(wrapper)

        shared_router_module.reset_shared_state()

        assert shared_router_module._adapter is None


class TestInjectedClientIsReused:
    def test_the_shared_wrapper_reuses_one_connection(self, monkeypatch):
        """The probe and the adapter see the same wrapper, hence one client."""
        enable_ollama(monkeypatch)
        server = FakeOllamaServer()
        wrapper = OllamaFirstAdapter(FakeHfAdapter(), make_adapter(server))
        shared_router_module.set_adapter_for_testing(wrapper)

        assert shared_router_module.get_adapter().ollama_adapter is wrapper.ollama_adapter
        assert isinstance(wrapper.ollama_adapter._client, httpx.Client)
        wrapper.close()
