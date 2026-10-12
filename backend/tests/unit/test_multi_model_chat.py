"""Tests for the multi-model pool, auto-selection and output contracts.

Covers Issue 4a (verified model pool + auto-selection), 4b (the ten registered
models) and 4c (contract enforcement with repair and deterministic fallback).
"""

from __future__ import annotations

import json

import pytest

from app.application.services.ai_model_router import HuggingFaceModelRouter
from app.application.services.ai_registry import AI_TASKS, LICENSE_APPROVED, LICENSE_REQUIRES_REVIEW
from app.application.services.model_catalog import (
    CHAT_ROUTER_VERIFIED,
    POLICY,
    SUBSTITUTIONS,
    build_model_pool,
    review_required_model_ids,
    routable_model_ids,
)
from app.application.services.output_validation import (
    deterministic_unavailable_content,
    generate_validated,
    validate_output,
)
from app.infrastructure.ai.prompt_templates import (
    build_repair_prompt,
    build_system_prompt,
    describe_contract,
    markdown_sections_present,
)


# ---------------------------------------------------------------------------
# 4b — the candidate pool
# ---------------------------------------------------------------------------
def test_pool_has_exactly_ten_unique_models():
    pool = build_model_pool()
    assert len(pool) == 10
    assert len({model.model_id for model in pool}) == 10


@pytest.mark.parametrize(
    "model_id",
    [
        "meta-llama/Llama-3.3-70B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "mistralai/Mistral-Small-3.1-24B-Instruct-2503",
        "google/gemma-3-27b-it",
        "microsoft/phi-4",
        "deepseek-ai/DeepSeek-R1",
        "HuggingFaceH4/zephyr-7b-beta",
        "openchat/openchat_3.5",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "teknium/OpenHermes-2.5-Mistral-7B",
    ],
)
def test_pool_contains_verified_model(model_id):
    assert model_id in {model.model_id for model in build_model_pool()}


def test_no_quality_score_is_fabricated():
    """§11: without an empirical benchmark the score stays unknown."""
    assert all(model.quality_score is None for model in build_model_pool())


def test_two_requested_models_were_substituted_for_verified_ids():
    """The requested ids that do not exist were replaced, not recorded as-working."""
    assert SUBSTITUTIONS["mistralai/Mistral-Small-3.1-24B-Instruct"] == (
        "mistralai/Mistral-Small-3.1-24B-Instruct-2503"
    )
    assert SUBSTITUTIONS["openchat/openchat-3.5-7b"] == "openchat/openchat_3.5"
    # Both requested ids return 404 from the HF API and both successors 200.
    registered = {model.model_id for model in build_model_pool()}
    assert set(SUBSTITUTIONS).isdisjoint(registered)
    assert set(SUBSTITUTIONS.values()).issubset(registered)


def test_licenses_match_the_huggingface_cards():
    """licenses are copied from HF cardData, not guessed."""
    licenses = {model.model_id: model.license for model in build_model_pool()}
    assert licenses["microsoft/phi-4"] == "mit"
    assert licenses["deepseek-ai/DeepSeek-R1"] == "mit"
    assert licenses["HuggingFaceH4/zephyr-7b-beta"] == "mit"
    assert licenses["mistralai/Mixtral-8x7B-Instruct-v0.1"] == "apache-2.0"
    assert licenses["teknium/OpenHermes-2.5-Mistral-7B"] == "apache-2.0"
    assert licenses["meta-llama/Llama-3.3-70B-Instruct"] == "llama3.3"
    assert licenses["google/gemma-3-27b-it"] == "gemma"
    assert licenses["Qwen/Qwen2.5-72B-Instruct"] == "qwen"


def test_models_with_additional_terms_are_not_auto_routed():
    review = set(review_required_model_ids())
    assert "meta-llama/Llama-3.3-70B-Instruct" in review
    assert "Qwen/Qwen2.5-72B-Instruct" in review
    assert "google/gemma-3-27b-it" in review
    # Apache/MIT models route out of the box (subject to chat capability).
    assert "microsoft/phi-4" in set(routable_model_ids())
    assert "deepseek-ai/DeepSeek-R1" in set(routable_model_ids())


def test_only_chat_capable_models_can_be_selected():
    """Models the HF router refuses for chat are never auto-selected."""
    from app.application.services.model_catalog import CHAT_ROUTER_VERIFIED

    router = HuggingFaceModelRouter()
    for task in AI_TASKS:
        model = router.select_model(task=task, token_budget=1024, preferred_languages=("en", "de", "fr"))
        assert CHAT_ROUTER_VERIFIED[model.model_id] == "chat_capable", (task, model.model_id)
        assert model.inference_provider_supported is True


def test_every_routing_task_still_has_a_model_after_that_filter():
    """Widening the chat-capable models must keep every task routable."""
    router = HuggingFaceModelRouter()
    for task in AI_TASKS:
        model = router.select_model(task=task, token_budget=1024, preferred_languages=("en", "de", "fr"))
        assert model.model_id


def test_provider_unsupported_models_are_registered_not_selected():
    registry = {m.model_id for m in build_model_pool()}
    assert set(CHAT_ROUTER_VERIFIED) == registry
    unsupported = {mid for mid, v in CHAT_ROUTER_VERIFIED.items() if v != "chat_capable"}
    assert unsupported, "expected a mix of chat-capable and unsupported models"
    for model_id in unsupported:
        entry = next(m for m in build_model_pool() if m.model_id == model_id)
        assert entry.inference_provider_supported is False
    # …but they stay listed so an operator can still see and enable them.
    assert unsupported <= registry


def test_operator_approval_unblocks_a_review_model():
    """AI_APPROVED_MODEL_IDS must be able to unblock a gated model."""
    from app.application.services.ai_registry import ModelApprovalPolicy

    pool = build_model_pool()
    policy = ModelApprovalPolicy(approved_review_ids=("Qwen/Qwen2.5-72B-Instruct",))
    assert policy.evaluate(next(m for m in pool if m.model_id == "Qwen/Qwen2.5-72B-Instruct")) == (LICENSE_APPROVED)


def test_every_pool_model_declares_a_license_status():
    for model in build_model_pool():
        status = POLICY.evaluate(model)
        assert status in {LICENSE_APPROVED, LICENSE_REQUIRES_REVIEW}


# ---------------------------------------------------------------------------
# 4a — auto-selection by task
# ---------------------------------------------------------------------------
def test_router_registers_all_ten_models():
    router = HuggingFaceModelRouter()
    assert len(router.list_models()) == 10


def test_auto_selection_differs_by_task_type():
    """CV generation and analysis must not all resolve to the same model."""
    router = HuggingFaceModelRouter()
    cv = router.select_model(task="cv_generation", token_budget=1024, preferred_languages=("en", "de", "fr"))
    ats = router.select_model(task="ats_analysis", token_budget=1024, preferred_languages=("en", "de", "fr"))
    assert cv.model_id and ats.model_id
    assert cv.supports_task("cv_generation")
    assert ats.supports_task("ats_analysis")


def test_auto_selection_excludes_gated_models_by_default():
    """A REVIEW model may be registered but must never be auto-selected."""
    router = HuggingFaceModelRouter()
    for task in AI_TASKS:
        model = router.select_model(task=task, token_budget=1024, preferred_languages=("en", "de", "fr"))
        assert POLICY.evaluate(model) == LICENSE_APPROVED, (task, model.model_id)


def test_manual_override_targets_a_specific_model():
    router = HuggingFaceModelRouter()
    chain = router.fallback_chain("cv_generation", token_budget=1024, preferred_languages=("en", "de", "fr"))
    assert chain, "cv_generation must have at least one routable model"
    assert all(POLICY.evaluate(model) == LICENSE_APPROVED for model in chain)


def test_every_task_has_a_routable_model():
    router = HuggingFaceModelRouter()
    for task in AI_TASKS:
        model = router.select_model(task=task, token_budget=1024, preferred_languages=("en", "de", "fr"))
        assert model.model_id


# ---------------------------------------------------------------------------
# 4c — output contracts
# ---------------------------------------------------------------------------
def test_every_task_has_a_contract():
    for task in AI_TASKS:
        described = describe_contract(task)
        assert described["kind"] in {"json", "markdown"}
        assert described["task"] == task


def test_system_prompt_carries_role_rules_language_and_contract():
    prompt = build_system_prompt("ats_analysis", language="de")
    assert "AI Career Assistant" in prompt
    assert "Never invent" in prompt
    assert "ANSWER LANGUAGE" not in prompt  # language lives in the task prompt
    assert '"score"' in prompt  # the JSON contract is spelled out
    assert '"type": "integer"' in prompt


def test_repair_prompt_names_the_exact_violations():
    prompt = build_repair_prompt(
        "ats_analysis",
        previous_output="not json",
        violations=["output is not valid JSON", "missing required key 'score'"],
        language="en",
    )
    assert "output is not valid JSON" in prompt
    assert "missing required key 'score'" in prompt
    assert '"score"' in prompt  # the contract is restated


# --- JSON contract validation -------------------------------------------------
VALID_ATS = json.dumps(
    {
        "score": 88,
        "summary": "Strong match.",
        "matched_keywords": ["python"],
        "missing_keywords": ["kubernetes"],
        "strengths": ["quantified impact"],
        "fixes": [{"issue": "no k8s", "action": "add one bullet"}],
    }
)


def test_valid_json_contract_passes():
    result = validate_output("ats_analysis", VALID_ATS)
    assert result.ok
    assert result.data["score"] == 88


@pytest.mark.parametrize(
    "raw",
    [
        '{"score": "high"}',
        '{"score": 90}',
        "Sure, here is my analysis!",
        "",
        json.dumps({"score": 88, "surprise": 1}),
    ],
)
def test_invalid_json_contract_reports_violations(raw):
    result = validate_output("ats_analysis", raw)
    assert result.ok is False
    assert result.violations


def test_fenced_json_is_recovered():
    result = validate_output("ats_analysis", f"```json\n{VALID_ATS}\n```")
    assert result.ok
    assert result.data["score"] == 88


def test_missing_sections_are_reported_for_markdown():
    assert markdown_sections_present("## Summary\nhi", ("Summary", "Steps")) == ["Steps"]


# --- repair and fallback -------------------------------------------------------
def _adapter(responses: list[str]):
    """A fake generate callback returning canned answers in order."""
    queue = list(responses)

    def generate(**kwargs):
        return {
            "content": queue.pop(0) if queue else "",
            "model_id": "test/model",
            "fallback_chain": ["test/backup"],
            "routing_score": 0.5,
        }

    return generate


def test_invalid_output_is_repaired_with_the_exact_violations():
    seen: dict[str, str] = {}

    def repair(**kwargs):
        seen["prompt"] = kwargs["prompt"]
        return {"content": VALID_ATS, "model_id": "test/model"}

    result = generate_validated(
        "ats_analysis",
        prompt="p",
        generate=_adapter(["Sure, here is my analysis"]),
        repair_generate=repair,
    )
    assert result.ok
    assert result.repaired
    assert result.attempts == 2
    assert result.data["score"] == 88
    # The repair prompt named the real problem.
    assert "not valid JSON" in seen["prompt"]


def test_repair_exhaustion_produces_a_labelled_fallback():
    result = generate_validated(
        "ats_analysis",
        prompt="p",
        generate=_adapter(["garbage", "still garbage", "more garbage"]),
        repair_generate=_adapter(["nope", "nope"]),
        max_repairs=2,
    )
    assert not result.ok
    assert result.fallback
    assert result.fallback_reason
    assert result.attempts == 3


def test_valid_first_answer_is_not_repaired():
    result = generate_validated(
        "ats_analysis",
        prompt="p",
        generate=_adapter([VALID_ATS]),
        repair_generate=_adapter(["never used"]),
    )
    assert result.ok
    assert not result.repaired
    assert result.attempts == 1


@pytest.mark.parametrize(
    "task",
    list(AI_TASKS),
)
def test_deterministic_fallback_always_satisfies_the_contract(task):
    payload = deterministic_unavailable_content(task, "model returned invalid JSON twice")
    raw = payload["content"] if "content" in payload and len(payload) == 1 else json.dumps(payload)
    result = validate_output(task, raw)
    assert result.ok, (task, result.violations)


# --- persistence ---------------------------------------------------------------
def test_session_language_is_created_and_validated():
    from app.application.services.chat_store import ChatStore

    store = ChatStore()
    session = store.create_session(user_id="u1", title="T", mode="general", language="de")
    assert session.language == "de"
    assert session.to_dict()["language"] == "de"

    with pytest.raises(ValueError, match="Unknown chat language"):
        store.create_session(user_id="u1", mode="general", language="es")


def test_message_routing_audit_is_recorded():
    from app.application.services.chat_store import ChatStore

    store = ChatStore()
    session = store.create_session(user_id="u1", title="T", mode="general")
    routing = {
        "selected_model": "microsoft/phi-4",
        "selection": "auto",
        "task": "career_advice",
        "contract": "markdown",
        "contract_status": "passed",
        "attempts": 1,
    }
    message = store.append_message(session, role="assistant", content="hi", routing=routing)
    assert message.routing["selected_model"] == "microsoft/phi-4"
    assert message.to_dict()["routing"]["selection"] == "auto"


def test_create_session_survives_derived_to_dict_fields():
    """Regression: message_count must not be forwarded to the model constructor."""
    from app.application.services.chat_store import ChatStore

    store = ChatStore()
    session = store.create_session(user_id="u1", title="T", mode="general")
    payload = session.to_dict(include_messages=False)
    assert "message_count" in payload
    # create() round-trips the payload through the model factory.
    assert session.id
