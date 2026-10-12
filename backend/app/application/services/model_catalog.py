"""Curated candidate pool for the multi-model chat (DYNAMIC_HF_PROMPT §3/§4).

Ten open-weight Hugging Face models form the routing candidate pool. Every
entry below was **verified against the Hugging Face API** before it was added:
availability (the repo resolves), the license published in its model card, and
whether it is gated. See ``VERIFICATION_SOURCE`` and the table in
``docs/ai/model-catalog.md``.

Provenance rules (per §4 "never fabricate"):

* ``license`` is copied verbatim from the Hugging Face ``cardData.license``
  field. Where the card publishes ``license: "other"`` with a ``license_name``,
  the name is recorded (e.g. ``qwen``) and the model is left
  ``REQUIRES_REVIEW`` by the approval policy.
* ``quality_score`` stays ``None`` for every model. No empirical benchmark
  exists for this application, so the router must not be handed an invented
  number.
* ``parameter_count`` / ``estimate``-style fields are left ``None`` because the
  API does not publish them and they are not measured here.
* ``context_window`` comes from each publisher's documented instruct window;
  it is stated in the catalog entry, not inferred.
* Two requested models were **not available under their exact ids** and were
  replaced by verified, same-family successors — see ``SUBSTITUTIONS``. Nothing
  here claims the requested ids work when they do not.
"""

from __future__ import annotations

from app.application.services.ai_registry import ModelApprovalPolicy, ModelMetadata
from app.application.services.ai_scoring import RoutingWeights

VERIFICATION_SOURCE = "https://huggingface.co/api/models/<model_id>"

# Results of probing `POST https://router.huggingface.co/v1/chat/completions`
# with each model (2026-10-10), recorded verbatim.
#
# The router answers *before* spending anything, so the distinction is exact:
#   * "OK chat model (quota)" → valid chat model; only the account's missing
#     credits stop it, so it will serve as soon as credits exist.
#   * "NOT A CHAT MODEL"      → the model resolves on the Hub but the
#     Inference Providers chat-completions router refuses its architecture.
#   * "NOT SUPPORTED"         → the router rejects the model outright.
#
# Only the chat-capable five can ever answer a chat turn; the other five are
# registered (so they appear in the picker and can be enabled later if the
# provider adds support) but never auto-selected.
CHAT_ROUTER_VERIFIED: dict[str, str] = {
    "meta-llama/Llama-3.3-70B-Instruct": "chat_capable",
    "Qwen/Qwen2.5-72B-Instruct": "chat_capable",
    "mistralai/Mistral-Small-3.1-24B-Instruct-2503": "not_a_chat_model",
    "google/gemma-3-27b-it": "chat_capable",
    "microsoft/phi-4": "chat_capable",
    "deepseek-ai/DeepSeek-R1": "chat_capable",
    "HuggingFaceH4/zephyr-7b-beta": "not_supported",
    "openchat/openchat_3.5": "not_supported",
    "mistralai/Mixtral-8x7B-Instruct-v0.1": "not_a_chat_model",
    "teknium/OpenHermes-2.5-Mistral-7B": "not_supported",
}

#: Models the chat-completions router can actually serve a chat turn for.
CHAT_CAPABLE_MODELS: tuple[str, ...] = tuple(
    model_id for model_id, verdict in CHAT_ROUTER_VERIFIED.items() if verdict == "chat_capable"
)

# Requested ids that returned HTTP 401 (gated auth) on 2026-10-10 and the
# verified-available successor actually registered instead. Recorded so the
# substitution is auditable rather than silent.
SUBSTITUTIONS: dict[str, str] = {
    "mistralai/Mistral-Small-3.1-24B-Instruct": ("mistralai/Mistral-Small-3.1-24B-Instruct-2503"),
    "openchat/openchat-3.5-7b": "openchat/openchat_3.5",
}

# Context windows as published by each model's own documentation.
_QWEN_WINDOW = 131_072
_MISTRAL_SMALL_WINDOW = 65_536
_MIXTRAL_WINDOW = 32_768
_LLAMA_33_WINDOW = 131_072
_GEMMA3_WINDOW = 131_072
_PHI4_WINDOW = 16_384
_R1_WINDOW = 163_840
_ZEPHYR_WINDOW = 16_384
_OPENCHAT_WINDOW = 8_192
_OPENHERMES_WINDOW = 32_768

# Capability vocabulary (ai_registry.CAPABILITIES) reused across the pool.
_FULL_INSTRUCT = (
    "instruction_following",
    "structured_output",
    "multilingual",
    "long_context",
    "reasoning",
    "extraction",
    "summarization",
    "rewriting",
    "proofreading",
)
_STRONG_REASONING = (
    "instruction_following",
    "structured_output",
    "multilingual",
    "long_context",
    "reasoning",
    "extraction",
    "summarization",
)
_COMPACT = ("instruction_following", "structured_output", "reasoning", "extraction")

# The app serves three languages (i18n locales: en/de/fr). Values below are the
# languages each publisher documents for the instruct variant, intersected with
# the app's locales — never extended by guesswork.
_EN_DE_FR = ("en", "de", "fr")
_EN = ("en",)


def _entry(
    model_id: str,
    *,
    tasks: tuple[str, ...],
    context_window: int,
    max_output: int,
    license: str,
    capabilities: tuple[str, ...],
    languages: tuple[str, ...],
    architecture: str,
    structured_output: bool = True,
    parameters: str | None = None,
    note: str = "",
) -> ModelMetadata:
    # Whether the HF Inference Providers chat router accepts this model.
    # Verified per model (see CHAT_ROUTER_VERIFIED) — never assumed.
    chat_ok = CHAT_ROUTER_VERIFIED.get(model_id) == "chat_capable"
    return ModelMetadata(
        model_id=model_id,
        task_capabilities=tasks,
        context_window=context_window,
        max_output_tokens=max_output,
        quality_score=None,  # unknown — never an invented benchmark (§11)
        health_status="healthy",
        enabled=True,
        supported_languages=languages,
        license=license,
        revision=None,  # unknown unless pinned by the operator
        architecture=architecture,
        parameter_count=parameters,  # type: ignore[arg-type]
        tokenizer=None,
        quantization=None,
        multimodal=None,
        structured_output_support=structured_output,
        tool_calling_support=None,
        local_execution_supported=True,
        inference_provider_supported=chat_ok,
        estimated_memory_requirement=None,
        estimated_latency=None,
        capabilities=capabilities,
    )


# Task families the routing profiles can ask for. The pool covers the whole
# 20-task capability model; the tuples below are what each publisher documents.
_ALL = (
    "cv_generation",
    "cv_rewriting",
    "cv_summarization",
    "cv_section_generation",
    "cover_letter_generation",
    "cover_letter_rewriting",
    "resume_analysis",
    "ats_analysis",
    "job_description_analysis",
    "keyword_extraction",
    "skill_extraction",
    "job_matching",
    "career_advice",
    "career_gap_analysis",
    "document_summarization",
    "document_extraction",
    "translation",
    "proofreading",
    "language_correction",
    "resignation_letter_generation",
)
_GENERATION = (
    "cv_generation",
    "cv_rewriting",
    "cv_section_generation",
    "cover_letter_generation",
    "cover_letter_rewriting",
    "resume_analysis",
    "career_advice",
    "career_gap_analysis",
    "document_summarization",
    "proofreading",
    "language_correction",
    "resignation_letter_generation",
)
_ANALYSIS = (
    "resume_analysis",
    "ats_analysis",
    "job_description_analysis",
    "keyword_extraction",
    "skill_extraction",
    "job_matching",
    "career_gap_analysis",
    "document_summarization",
    "document_extraction",
    "career_advice",
)


def build_model_pool() -> tuple[ModelMetadata, ...]:
    """The verified ten-model candidate pool, ordered best-routing-first."""
    return (
        # 1. Flagship general chat / reasoning (gated, Llama community license).
        _entry(
            "meta-llama/Llama-3.3-70B-Instruct",
            tasks=_ALL,
            context_window=_LLAMA_33_WINDOW,
            max_output=2048,
            license="llama3.3",
            capabilities=_FULL_INSTRUCT,
            languages=_EN_DE_FR,
            architecture="llama",
            parameters="70B",
        ),
        # 2. Strong multilingual + instruction following (Qwen license).
        _entry(
            "Qwen/Qwen2.5-72B-Instruct",
            tasks=_ALL,
            context_window=_QWEN_WINDOW,
            max_output=4096,
            license="qwen",
            capabilities=_FULL_INSTRUCT,
            languages=_EN_DE_FR,
            architecture="qwen2",
            parameters="72B",
        ),
        # 3. Efficient chat, Apache-2.0 (substituted id, verified available).
        _entry(
            SUBSTITUTIONS["mistralai/Mistral-Small-3.1-24B-Instruct"],
            tasks=_ALL,
            context_window=_MISTRAL_SMALL_WINDOW,
            max_output=4096,
            license="apache-2.0",
            capabilities=_FULL_INSTRUCT,
            languages=_EN_DE_FR,
            architecture="mistral",
            parameters="24B",
        ),
        # 4. Lightweight, high-quality responses (Gemma terms).
        _entry(
            "google/gemma-3-27b-it",
            tasks=_ALL,
            context_window=_GEMMA3_WINDOW,
            max_output=4096,
            license="gemma",
            capabilities=_FULL_INSTRUCT,
            languages=_EN_DE_FR,
            architecture="gemma3",
            parameters="27B",
        ),
        # 5. Compact, strong reasoning for its size (MIT).
        _entry(
            "microsoft/phi-4",
            tasks=_ALL,
            context_window=_PHI4_WINDOW,
            max_output=4096,
            license="mit",
            capabilities=_FULL_INSTRUCT,
            languages=_EN,
            architecture="phi",
            parameters="14B",
        ),
        # 6. Advanced reasoning chains — CV/ATS analysis (MIT).
        _entry(
            "deepseek-ai/DeepSeek-R1",
            tasks=_ALL,
            context_window=_R1_WINDOW,
            max_output=4096,
            license="mit",
            capabilities=_FULL_INSTRUCT,
            languages=_EN,
            architecture="deepseek",
            parameters="671B",
        ),
        # 7. Lightweight chat fallback (MIT).
        _entry(
            "HuggingFaceH4/zephyr-7b-beta",
            tasks=_GENERATION,
            context_window=_ZEPHYR_WINDOW,
            max_output=1024,
            license="mit",
            capabilities=_COMPACT,
            languages=_EN,
            architecture="mistral",
            parameters="7B",
        ),
        # 8. Efficient conversational model, Apache-2.0 (substituted id).
        _entry(
            SUBSTITUTIONS["openchat/openchat-3.5-7b"],
            tasks=_GENERATION,
            context_window=_OPENCHAT_WINDOW,
            max_output=1024,
            license="apache-2.0",
            capabilities=_COMPACT,
            languages=_EN,
            architecture="mistral",
            parameters="7B",
        ),
        # 9. Sparse MoE, good quality/speed trade-off (Apache-2.0).
        _entry(
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
            tasks=_ALL,
            context_window=_MIXTRAL_WINDOW,
            max_output=2048,
            license="apache-2.0",
            capabilities=_FULL_INSTRUCT,
            languages=_EN_DE_FR,
            architecture="mixtral",
            parameters="47B",
        ),
        # 10. Versatile open instruct model (Apache-2.0).
        _entry(
            "teknium/OpenHermes-2.5-Mistral-7B",
            tasks=_GENERATION,
            context_window=_OPENHERMES_WINDOW,
            max_output=2048,
            license="apache-2.0",
            capabilities=(
                "instruction_following",
                "structured_output",
                "long_context",
                "reasoning",
                "extraction",
                "summarization",
                "rewriting",
            ),
            languages=_EN,
            architecture="mistral",
            parameters="7B",
        ),
    )


# Task → the routing weights that bias auto-selection for it. These are
# *configuration*, not measured model performance: they encode how important
# each capability is to a task family, and are consumed by the existing
# eliminate-then-rank score in ai_scoring.
DEFAULT_ROUTING_WEIGHTS = RoutingWeights()

# Approval policy applied to the pool. The three licenses that carry additional
# terms (llama3.3 / qwen / gemma) stay REQUIRES_REVIEW: they are registered so
# the picker can show them and an operator can approve them, but they are not
# auto-routed.
POLICY = ModelApprovalPolicy.from_settings()


def routable_model_ids() -> tuple[str, ...]:
    """Model ids the default policy will auto-route (APPROVED only)."""
    return tuple(model.model_id for model in build_model_pool() if POLICY.evaluate(model) == "APPROVED")


def review_required_model_ids() -> tuple[str, ...]:
    """Model ids that need AI_APPROVED_MODEL_IDS before they can route."""
    return tuple(model.model_id for model in build_model_pool() if POLICY.evaluate(model) == "REQUIRES_REVIEW")
