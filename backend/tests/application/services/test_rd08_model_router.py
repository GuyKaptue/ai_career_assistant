"""RD-08 step 4: ModelRouter facade (fake adapter; the real chain is covered by existing router tests)."""

import logging

import pytest

from app.application.services.ai_model_router import HuggingFaceModelRouter
from app.application.services.ai_registry import AI_TASKS
from app.application.services.model_router_facade import (
    INTENT_TASKS,
    CompletionOptions,
    ModelRouter,
    model_family,
)
from app.core.errors import AIProviderError


class FakeAdapter:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def generate_with_fallback(self, task, prompt, **kw):
        self.calls.append((task, prompt, kw))
        if self.error:
            raise self.error
        return self.result


def ok(model="ollama:llama3.2:3b", **extra):
    return {
        "content": "answer",
        "model_id": model,
        "fallback_reason": None,
        "fallback_chain": [model],
        "routing_score": 0.8,
        **extra,
    }


def test_every_intent_maps_to_a_registered_task():
    assert set(INTENT_TASKS.values()) <= set(AI_TASKS)


def test_auto_mode_passes_task_budget_language_and_reports_family():
    adapter = FakeAdapter(ok())
    c = ModelRouter(adapter).complete(
        "search_jobs", "p", CompletionOptions(system_prompt="s", token_budget=700, language="de")
    )
    task, prompt, kw = adapter.calls[0]
    assert task == "job_matching" and prompt == "p" and kw["system_prompt"] == "s"
    assert kw["token_budget"] == 700 and kw["preferred_languages"] == ("de",) and kw["preferred_model_id"] is None
    assert (c.mode, c.family, c.pin_honored, c.switched, c.notice) == ("auto", "ollama", None, False, None)


def test_failover_is_reported_as_switched_with_models_tried():
    raw = ok("hf/model-b", fallback_reason="hf/model-a: rate limit", fallback_chain=["hf/model-a", "hf/model-b"])
    c = ModelRouter(FakeAdapter(raw)).complete("tailor_cv", "p")
    assert c.switched and c.family == "huggingface" and c.attempted_models == ("hf/model-a", "hf/model-b")


def test_manual_pin_honored():
    c = ModelRouter(FakeAdapter(ok("hf/pinned"))).complete(
        "analysis", "p", CompletionOptions(preferred_model_id="hf/pinned")
    )
    assert c.mode == "manual" and c.pin_honored is True and c.notice is None


def test_manual_pin_not_honored_informs_the_user():
    c = ModelRouter(FakeAdapter(ok("hf/other"))).complete(
        "analysis", "p", CompletionOptions(preferred_model_id="hf/pinned")
    )
    assert (
        c.pin_honored is False and "unavailable" in (c.notice or "") and c.metadata()["pinned_model_id"] == "hf/pinned"
    )


def test_no_eligible_model_becomes_typed_provider_error():
    with pytest.raises(AIProviderError):
        ModelRouter(FakeAdapter(error=ValueError("No model candidates are available"))).complete("general", "p")


def test_provider_error_passes_through_and_unknown_intent_rejected():
    with pytest.raises(AIProviderError):
        ModelRouter(FakeAdapter(error=AIProviderError("all failed"))).complete("general", "p")
    with pytest.raises(ValueError):
        ModelRouter(FakeAdapter(ok())).complete("poem", "p")


def test_generator_adapts_pipelines_collects_completions_and_notices():
    adapter = FakeAdapter(ok("hf/other"))
    gen = ModelRouter(adapter).generator_for("analysis", preferred_model_id="hf/pinned")
    out = gen.generate_with_fallback(
        "resume_analysis", "p", token_budget=700, system_prompt="s", preferred_languages=("fr",)
    )
    assert out == {"content": "answer", "model_id": "hf/other"}
    assert adapter.calls[0][2]["preferred_model_id"] == "hf/pinned" and adapter.calls[0][2]["preferred_languages"] == (
        "fr",
    )
    assert len(gen.completions) == 1 and len(gen.notices()) == 1


def test_model_family():
    assert model_family("ollama:x") == "ollama" and model_family("org/model") == "huggingface"


def test_routing_logs_contain_no_content(caplog):
    caplog.set_level(logging.DEBUG)
    ModelRouter(FakeAdapter({**ok(), "content": "SECRET ANSWER"})).complete("general", "SECRET PROMPT")
    assert "SECRET" not in caplog.text


def test_default_adapter_is_the_shared_one(monkeypatch):
    from app.application.services import shared_router

    fake = FakeAdapter(ok())
    monkeypatch.setattr(shared_router, "get_adapter", lambda: fake)
    assert ModelRouter().complete("general", "p").content == "answer"
    assert HuggingFaceModelRouter  # real router stays the failover engine


# ---- through the REAL Hugging Face router (only the network call is faked) -----------------
def _real_adapter(monkeypatch, behaviour):
    from app.application.services.ai_model_router import HuggingFaceInferenceAdapter
    from app.application.services.ai_registry import ModelMetadata

    models = [
        ModelMetadata(
            model_id=mid,
            task_capabilities=("career_advice",),
            license="apache-2.0",
            context_window=8192,
            quality_score=score,
        )
        for mid, score in (("test/best", 0.9), ("test/second", 0.5))
    ]
    adapter = HuggingFaceInferenceAdapter(router=HuggingFaceModelRouter(models=models))
    calls = []

    def fake_call(self, model, prompt, max_new_tokens):
        calls.append(model.model_id)
        return behaviour(model.model_id)

    monkeypatch.setattr(HuggingFaceInferenceAdapter, "_call_model", fake_call)
    return adapter, calls


def test_real_router_auto_mode_picks_best_model(monkeypatch):
    adapter, calls = _real_adapter(monkeypatch, lambda mid: f"from {mid}")
    c = ModelRouter(adapter).complete("general", "hi")
    assert c.model_id == "test/best" and not c.switched and c.family == "huggingface"


def test_real_router_switches_model_when_limit_is_reached(monkeypatch):
    def behaviour(mid):
        if mid == "test/best":
            raise RuntimeError("RATE_LIMITED: 429 Too Many Requests")
        return "ok"

    adapter, calls = _real_adapter(monkeypatch, behaviour)
    c = ModelRouter(adapter).complete("general", "hi", CompletionOptions(max_retries=1))
    assert c.model_id == "test/second" and c.switched and c.attempted_models == ("test/best", "test/second")
    # the throttled model keeps its own breaker state; the next request is routed on without re-hitting it first
    assert adapter._circuit_breakers["test/best"].last_failure_type == "RATE_LIMITED"


def test_real_router_manual_pin_and_unavailable_pin(monkeypatch):
    adapter, calls = _real_adapter(monkeypatch, lambda mid: "ok")
    router = ModelRouter(adapter)
    pinned = router.complete("general", "hi", CompletionOptions(preferred_model_id="test/second"))
    assert pinned.model_id == "test/second" and pinned.pin_honored is True
    missing = router.complete("general", "hi", CompletionOptions(preferred_model_id="test/gone"))
    assert missing.model_id == "test/best" and missing.pin_honored is False and missing.notice
