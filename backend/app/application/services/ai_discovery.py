"""Dynamic Hugging Face model discovery (DYNAMIC_HF_PROMPT §5).

Controlled pipeline — never blind trust:

    Hugging Face Hub → discovery → compatibility → license → task
                     → language → resource → ranking → approved registry

Discovered models must pass policy validation before they become eligible
for production inference, and metadata Hugging Face does not expose stays
``None`` — context windows and quality scores are never invented (§4/§5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

from app.application.services.ai_registry import (
    LICENSE_APPROVED,
    ModelApprovalPolicy,
    ModelMetadata,
    normalize_task,
)
from app.core.errors import AIProviderError

logger = logging.getLogger(__name__)

_DEFAULT_PIPELINE_TAGS = frozenset({"text-generation", "text2text-generation"})

# Which HF pipeline tags can serve each app task (§5 task filter).
TASK_PIPELINE_TAGS: dict[str, frozenset[str]] = {
    "cv_generation": _DEFAULT_PIPELINE_TAGS,
    "cv_rewriting": _DEFAULT_PIPELINE_TAGS,
    "cv_summarization": _DEFAULT_PIPELINE_TAGS,
    "cv_section_generation": _DEFAULT_PIPELINE_TAGS,
    "cover_letter_generation": _DEFAULT_PIPELINE_TAGS,
    "cover_letter_rewriting": _DEFAULT_PIPELINE_TAGS,
    "resume_analysis": _DEFAULT_PIPELINE_TAGS,
    "ats_analysis": _DEFAULT_PIPELINE_TAGS,
    "job_description_analysis": _DEFAULT_PIPELINE_TAGS,
    "keyword_extraction": _DEFAULT_PIPELINE_TAGS,
    "skill_extraction": _DEFAULT_PIPELINE_TAGS,
    "job_matching": _DEFAULT_PIPELINE_TAGS,
    "career_advice": _DEFAULT_PIPELINE_TAGS,
    "career_gap_analysis": _DEFAULT_PIPELINE_TAGS,
    "document_summarization": frozenset({"summarization", *_DEFAULT_PIPELINE_TAGS}),
    "document_extraction": _DEFAULT_PIPELINE_TAGS,
    "translation": frozenset({"translation", *_DEFAULT_PIPELINE_TAGS}),
    "proofreading": _DEFAULT_PIPELINE_TAGS,
    "language_correction": _DEFAULT_PIPELINE_TAGS,
    "resignation_letter_generation": _DEFAULT_PIPELINE_TAGS,
}


@dataclass(frozen=True)
class DiscoveryReport:
    """Stage-by-stage audit of one discovery run (§5 pipeline)."""

    total_discovered: int
    compatible: int
    license_approved: int
    task_matched: int
    language_matched: int
    resource_passed: int
    approved: tuple[ModelMetadata, ...]
    rejected: tuple[tuple[str, str], ...]  # (model_id, reason)

    @property
    def ranked_count(self) -> int:
        return len(self.approved)


def _card_data(model: Any) -> dict[str, Any]:
    data = getattr(model, "cardData", None)
    return data if isinstance(data, dict) else {}


def _tags(model: Any) -> list[str]:
    tags = getattr(model, "tags", None)
    return [str(tag) for tag in tags] if isinstance(tags, (list, tuple)) else []


def _license_of(model: Any) -> str:
    license_value = _card_data(model).get("license")
    if isinstance(license_value, str) and license_value.strip():
        return license_value.strip().lower()
    return "unknown"


def _languages_of(model: Any) -> tuple[str, ...]:
    value = _card_data(model).get("language")
    if isinstance(value, str) and value.strip():
        return (value.strip().lower(),)
    if isinstance(value, (list, tuple)):
        languages = tuple(str(item).strip().lower() for item in value if str(item).strip())
        return languages
    return ()


def _parameter_count_of(model: Any) -> int | None:
    """Parameter count only when the model card exposes it (never guessed)."""
    data = _card_data(model)
    safetensors_meta = data.get("safetensors")
    if isinstance(safetensors_meta, dict):
        total = safetensors_meta.get("total")
        if isinstance(total, int) and total > 0:
            return total
    params = data.get("params")
    if isinstance(params, int) and params > 0:
        return params
    return None


def _is_instruct_model(model: Any) -> bool:
    model_id = str(getattr(model, "id", "")).lower()
    return "instruction-tuned" in _tags(model) or "instruct" in model_id or "chat" in model_id


class ModelDiscoveryService:
    """Run the §5 discovery pipeline against the Hugging Face Hub.

    ``api`` is injectable so tests run hermetically against a fake Hub; the
    real ``huggingface_hub.HfApi`` is only imported when none is provided.
    """

    def __init__(
        self,
        api: Any | None = None,
        policy: ModelApprovalPolicy | None = None,
        max_parameters: int | None = None,
    ) -> None:
        self._api = api
        self.policy = policy or ModelApprovalPolicy.from_settings()
        self.max_parameters = max_parameters

    def discover(
        self,
        task: str,
        *,
        query: str = "instruct",
        languages: tuple[str, ...] = (),
        limit: int = 20,
    ) -> DiscoveryReport:
        """Run discover → compatibility → license → task → language → resource → rank."""
        if not self.policy.allow_dynamic_discovery:
            raise AIProviderError("Model discovery is disabled by the approval policy.")
        normalized_task = normalize_task(task)
        if normalized_task not in TASK_PIPELINE_TAGS:
            raise AIProviderError(f"Task '{task}' is not part of the task capability model.")

        rejected: list[tuple[str, str]] = []
        raw_models = list(self._list_models(query=query, limit=limit))

        compatible = [m for m in raw_models if self._keep(self._compatibility_check(m), m, rejected)]
        licensed = [m for m in compatible if self._keep(self._license_check(m), m, rejected)]
        task_matched = [m for m in licensed if self._keep(self._task_check(m, normalized_task), m, rejected)]
        language_matched = [m for m in task_matched if self._keep(self._language_check(m, languages), m, rejected)]
        resource_passed = [m for m in language_matched if self._keep(self._resource_check(m), m, rejected)]

        approved = tuple(
            sorted(
                (self._to_metadata(model, normalized_task) for model in resource_passed),
                # Resource-aware ranking: smaller known models first, unknown
                # parameter counts last. No fabricated quality ordering (§11).
                key=lambda meta: (
                    meta.parameter_count is None,
                    meta.parameter_count or 0,
                    meta.model_id,
                ),
            )
        )
        report = DiscoveryReport(
            total_discovered=len(raw_models),
            compatible=len(compatible),
            license_approved=len(licensed),
            task_matched=len(task_matched),
            language_matched=len(language_matched),
            resource_passed=len(resource_passed),
            approved=approved,
            rejected=tuple(rejected),
        )
        logger.info(
            "ai.discovery task=%s discovered=%d approved=%d rejected=%d",
            normalized_task,
            report.total_discovered,
            len(approved),
            len(rejected),
        )
        return report

    # ------------------------------------------------------------------ #
    # Stage checks — return rejection reason or None
    # ------------------------------------------------------------------ #
    def _compatibility_check(self, model: Any) -> str | None:
        model_id = str(getattr(model, "id", "") or "")
        if not model_id:
            return "compatibility:no_model_id"
        pipeline = getattr(model, "pipeline_tag", None)
        if pipeline not in _DEFAULT_PIPELINE_TAGS and pipeline not in {"summarization", "translation"}:
            return "compatibility:unsupported_pipeline"
        if self.policy.require_model_card and not _card_data(model):
            return "compatibility:model_card_required"
        if self.policy.require_supported_transformers and "transformers" not in _tags(model):
            return "compatibility:transformers_not_supported"
        if self.policy.require_instruct_model and not _is_instruct_model(model):
            return "compatibility:not_instruction_tuned"
        return None

    def _license_check(self, model: Any) -> str | None:
        shell = ModelMetadata(model_id=str(getattr(model, "id", "")), license=_license_of(model))
        status = self.policy.evaluate(shell)
        if status == LICENSE_APPROVED:
            return None
        if shell.model_id in self.policy.approved_review_ids:
            return None
        return f"license:{status}"

    def _task_check(self, model: Any, task: str) -> str | None:
        pipeline = getattr(model, "pipeline_tag", None)
        if pipeline in TASK_PIPELINE_TAGS[task]:
            return None
        return f"task:pipeline_{pipeline}_cannot_serve_{task}"

    def _language_check(self, model: Any, languages: tuple[str, ...]) -> str | None:
        wanted = {lang.strip().lower() for lang in languages if lang and lang.strip()}
        if not wanted:
            return None
        known = _languages_of(model)
        if not known:
            return None  # unknown languages are kept — never fabricated
        if wanted & set(known) or "multilingual" in set(known):
            return None
        return f"language:no_match_{','.join(sorted(known))}"

    def _resource_check(self, model: Any) -> str | None:
        if self.max_parameters is None:
            return None
        params = _parameter_count_of(model)
        if params is None:
            return None  # unknown size is not proof of being too large
        if params > self.max_parameters:
            return f"resource:parameter_count_{params}_exceeds_{self.max_parameters}"
        return None

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _keep(reason: str | None, model: Any, rejected: list[tuple[str, str]]) -> bool:
        if reason is None:
            return True
        rejected.append((str(getattr(model, "id", "")), reason))
        return False

    def _list_models(self, *, query: str, limit: int) -> Iterable[Any]:
        api = self._api
        if api is None:
            try:
                from huggingface_hub import HfApi
            except ImportError as exc:  # pragma: no cover - declared dependency
                raise AIProviderError("huggingface_hub is not installed.") from exc
            api = HfApi()
        try:
            return api.list_models(search=query, limit=limit)
        except Exception as exc:
            raise AIProviderError(f"Model discovery failed: {exc}") from exc

    @staticmethod
    def _to_metadata(model: Any, task: str) -> ModelMetadata:
        """Convert a filtered Hub result into registry metadata (§4/§5).

        Only values Hugging Face actually exposed are set; context window,
        quality score and latency stay unknown (None) by design.
        """
        model_id = str(getattr(model, "id", ""))
        card = _card_data(model)
        architecture = None
        raw_arch = card.get("architectures")
        if isinstance(raw_arch, (list, tuple)) and raw_arch:
            architecture = str(raw_arch[0])
        revision = getattr(model, "sha", None)
        return ModelMetadata(
            model_id=model_id,
            task_capabilities=(task,),  # validated for this task only
            context_window=None,  # unknown — never fabricated (§4)
            quality_score=None,  # no empirical benchmark (§11)
            provider="huggingface",
            supported_languages=_languages_of(model),
            license=_license_of(model),
            revision=str(revision) if revision else None,
            architecture=architecture,
            parameter_count=_parameter_count_of(model),
            license_policy_status=LICENSE_APPROVED,
            inference_provider_supported=True,
        )
