"""Model registry: rich metadata, approval policy, task capability model.

Maps to DYNAMIC_HF_PROMPT §3 (``model_registry/``), §4 (ModelMetadata),
§6 (approval policy) and §7 (task capability model).

Nothing here is invented at runtime: curated registry entries declare
explicit, documented metadata; anything the system cannot know stays
``None`` ("unknown") and is handled as an unknown — never fabricated (§4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.config import settings

# ---------------------------------------------------------------------------
# §7 — the AI Career Assistant task capability model (20 tasks).
# ---------------------------------------------------------------------------
AI_TASKS: tuple[str, ...] = (
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

# Capability vocabulary referenced by the per-task profiles (§8). Profiles
# state which capabilities a task requires; models declare which they
# provide. This is configuration, not measured model performance.
CAPABILITIES: tuple[str, ...] = (
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


def normalize_task(task: str) -> str:
    """Canonical task spelling so ``cv-generation`` == ``cv_generation``."""
    return task.strip().lower().replace("-", "_")


# ---------------------------------------------------------------------------
# §6 — license approval statuses.
# ---------------------------------------------------------------------------
LICENSE_APPROVED = "APPROVED"
LICENSE_REQUIRES_REVIEW = "REQUIRES_REVIEW"
LICENSE_BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ModelMetadata:
    """Structured, non-fabricated metadata for one registered model (§4).

    ``None`` always means "unknown" — never "average" or "default".
    Field names follow the spec list; ``task_capabilities`` covers the
    spec's ``supported_tasks``. ``license_policy_status`` is filled in by
    :class:`ModelApprovalPolicy` when the router registers the model.
    """

    model_id: str
    task_capabilities: tuple[str, ...] = ()
    # Hand-registered text-generation models default to the registry's
    # documented conservative window; discovery marks unknown windows as None.
    context_window: int | None = 4096
    max_output_tokens: int = 512
    # None = no empirical benchmark exists (§11: mark unavailable, never
    # manufacture a score).
    quality_score: float | None = None
    health_status: str = "healthy"
    enabled: bool = True
    provider: str = "huggingface"
    supported_languages: tuple[str, ...] = ("en",)
    license: str = "unknown"
    # --- AI-01 rich metadata (unknown by default) ---
    revision: str | None = None
    architecture: str | None = None
    parameter_count: int | None = None
    tokenizer: str | None = None
    quantization: str | None = None
    license_policy_status: str | None = None  # APPROVED / REQUIRES_REVIEW / BLOCKED
    multimodal: bool | None = None
    structured_output_support: bool | None = None
    tool_calling_support: bool | None = None
    local_execution_supported: bool | None = None
    inference_provider_supported: bool | None = None
    estimated_memory_requirement: int | None = None  # megabytes
    estimated_latency: float | None = None  # milliseconds
    # §8 capability vocabulary covered by this model; empty = unknown.
    capabilities: tuple[str, ...] = ()

    def supports_task(self, task: str) -> bool:
        if not self.task_capabilities:
            return True
        normalized = normalize_task(task)
        return any(normalize_task(cap) == normalized for cap in self.task_capabilities)

    def covers_capabilities(self, required: Sequence[str]) -> bool | None:
        """True=all covered, False=gap, None=unknown (model declares none)."""
        if not self.capabilities:
            return None
        declared = {normalize_task(cap) for cap in self.capabilities}
        return all(normalize_task(cap) in declared for cap in required)

    @property
    def window_unknown(self) -> bool:
        return self.context_window is None

    def unknown_fields(self) -> tuple[str, ...]:
        """Names of §4 metadata fields whose value is unknown (§4 audit)."""
        return tuple(
            name
            for name in (
                "revision",
                "architecture",
                "parameter_count",
                "tokenizer",
                "quantization",
                "quality_score",
                "estimated_memory_requirement",
                "estimated_latency",
            )
            if getattr(self, name) is None
        )


@dataclass(frozen=True)
class ModelApprovalPolicy:
    """Explicit, configurable model approval policy (DYNAMIC_HF_PROMPT §6).

    * allowlisted licenses (apache-2.0/mit family) → ``APPROVED``
    * unknown licenses and models with additional terms (Gemma, Falcon,
      Llama families) → ``REQUIRES_REVIEW`` — gated for routing unless the
      operator explicitly lists the model id in ``AI_APPROVED_MODEL_IDS``
    * ``blocked_licenses`` / ``blocked_id_prefixes`` → ``BLOCKED`` always

    Discovery-time requirements (``require_model_card``,
    ``minimum_quality_score``, ``supported_languages``) are consumed by the
    discovery pipeline; they never fabricate a value that HF did not expose.
    """

    allowed_licenses: tuple[str, ...] = ("apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause", "isc")
    # Families with additional usage terms — never auto-approved (§6).
    review_id_prefixes: tuple[str, ...] = ("meta-llama/", "google/gemma", "tiiuae/falcon")
    review_license_keywords: tuple[str, ...] = ("llama", "gemma", "falcon", "openrail")
    blocked_licenses: tuple[str, ...] = ()
    blocked_id_prefixes: tuple[str, ...] = ()
    # Operator-approved exceptions to REQUIRES_REVIEW gating.
    approved_review_ids: tuple[str, ...] = ()
    # Discovery-time gates (§5/§6).
    allow_dynamic_discovery: bool = True
    require_model_card: bool = True
    require_supported_transformers: bool = True
    require_instruct_model: bool = True
    minimum_quality_score: float | None = None
    supported_languages: tuple[str, ...] = ("en", "de", "fr")

    @classmethod
    def from_settings(cls) -> "ModelApprovalPolicy":
        """Build the runtime policy from environment configuration (§41)."""
        return cls(approved_review_ids=settings.ai_approved_model_ids)

    def evaluate(self, model: ModelMetadata) -> str:
        """Decide the approval status of one model (§6). Deterministic."""
        license_key = (model.license or "").strip().lower()
        model_id = model.model_id.strip().lower()

        if license_key in {item.strip().lower() for item in self.blocked_licenses}:
            return LICENSE_BLOCKED
        if any(model_id.startswith(prefix.lower()) for prefix in self.blocked_id_prefixes):
            return LICENSE_BLOCKED

        needs_review = self._has_additional_terms(model_id, license_key)
        if not needs_review:
            if license_key in {item.strip().lower() for item in self.allowed_licenses}:
                status = LICENSE_APPROVED
            else:
                # Unknown or non-allowlisted license: never auto-trust (§5).
                status = LICENSE_REQUIRES_REVIEW
        else:
            status = LICENSE_REQUIRES_REVIEW

        if status == LICENSE_REQUIRES_REVIEW and model.model_id in self.approved_review_ids:
            return LICENSE_APPROVED
        return status

    def _has_additional_terms(self, model_id: str, license_key: str) -> bool:
        """Gemma/Falcon/Llama-style families requiring explicit acceptance."""
        if any(model_id.startswith(prefix.lower()) for prefix in self.review_id_prefixes):
            return True
        return any(keyword in license_key for keyword in self.review_license_keywords)
