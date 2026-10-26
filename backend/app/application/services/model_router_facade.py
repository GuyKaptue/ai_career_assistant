"""Single model-call abstraction for every career intent (RD-08 §5).

``ModelRouter.complete(intent, prompt, options)`` is the only entry point intent
code needs. It sits ABOVE the existing Ollama-first adapter and the Hugging Face
router, which keep doing the real work: ranked fallback chain, bounded retries,
per-model circuit breakers (so recently throttled or failing models are skipped),
failover on rate limit / timeout / unavailable, and a content-free audit log.
Nothing below this module changed.

What the facade adds:

* intent -> task mapping (the registry's task capability model);
* **auto** mode (no pin): the adapter chooses and fails over transparently;
* **manual** mode (``preferred_model_id``): the pin is requested; if another model
  answered (pinned model unavailable, ineligible or failed), the result says so
  (``pin_honored=False`` plus a notice) instead of hiding it;
* typed result metadata (model, family, whether a switch happened, the models
  tried, the routing score), never any prompt or answer content in logs;
* conversion of "no eligible model" (``ValueError`` in the HF router) into
  ``AIProviderError`` so callers handle one typed error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Final

from app.application.services.ollama_first_adapter import OLLAMA_MODEL_ID_PREFIX, GenerationAdapter
from app.core.errors import AIProviderError

logger = logging.getLogger(__name__)

#: Career intent / pipeline stage -> registry task. Data, validated against AI_TASKS in tests.
INTENT_TASKS: Final[dict[str, str]] = {
    "analysis": "resume_analysis",
    "job_extraction": "job_description_analysis",
    "search_jobs": "job_matching",
    "summarize_cv": "cv_summarization",
    "improve_cv": "cv_rewriting",
    "tailor_cv": "cv_rewriting",
    "cover_letter": "cover_letter_generation",
    "skill_gap": "career_gap_analysis",
    "interview_prep": "career_advice",
    "clarify": "career_advice",
    "general": "career_advice",
}


@dataclass(frozen=True)
class CompletionOptions:
    """Per-call options. ``preferred_model_id`` pins a model (manual mode)."""

    system_prompt: str = ""
    token_budget: int = 1024
    language: str = "en"
    preferred_model_id: str | None = None
    max_retries: int = 3


@dataclass(frozen=True)
class Completion:
    """Model answer plus content-free routing metadata."""

    content: str
    model_id: str
    family: str
    task: str
    mode: str
    pinned_model_id: str | None
    pin_honored: bool | None
    switched: bool
    attempted_models: tuple[str, ...]
    routing_score: float | None
    notice: str | None

    def metadata(self) -> dict[str, Any]:
        """Safe to return to the client or log: no prompt, no answer, no failure text."""
        return {
            "model_id": self.model_id,
            "family": self.family,
            "task": self.task,
            "mode": self.mode,
            "pinned_model_id": self.pinned_model_id,
            "pin_honored": self.pin_honored,
            "switched": self.switched,
            "attempted_models": list(self.attempted_models),
            "routing_score": self.routing_score,
            "notice": self.notice,
        }


def model_family(model_id: str) -> str:
    """``ollama`` for local models, ``huggingface`` for everything else."""
    return "ollama" if model_id.startswith(OLLAMA_MODEL_ID_PREFIX) else "huggingface"


class ModelRouter:
    """Facade over the shared generation adapter (Ollama first, Hugging Face fallback)."""

    def __init__(self, adapter: GenerationAdapter | None = None) -> None:
        self._adapter = adapter

    def _resolve_adapter(self) -> GenerationAdapter:
        if self._adapter is not None:
            return self._adapter
        from app.application.services.shared_router import get_adapter

        return get_adapter()

    def complete(self, intent: str, prompt: str, options: CompletionOptions | None = None) -> Completion:
        """Run one completion for ``intent``. Raises :class:`AIProviderError` when no model can answer."""
        opts = options or CompletionOptions()
        task = INTENT_TASKS.get(intent)
        if task is None:
            raise ValueError(f"Unknown intent '{intent}'. Known: {sorted(INTENT_TASKS)}")
        try:
            raw = self._resolve_adapter().generate_with_fallback(
                task,
                prompt,
                token_budget=opts.token_budget,
                preferred_languages=(opts.language,),
                max_retries=opts.max_retries,
                system_prompt=opts.system_prompt,
                preferred_model_id=opts.preferred_model_id,
            )
        except ValueError as exc:  # HF router: no eligible model for this task/size
            raise AIProviderError("No eligible model is available for this request.") from exc

        model_id = str(raw.get("model_id") or "")
        attempted = tuple(str(m) for m in raw.get("fallback_chain") or ())
        switched = bool(raw.get("fallback_reason")) or len(attempted) > 1
        pinned = opts.preferred_model_id
        honored = None if pinned is None else model_id == pinned
        notice = None
        if honored is False:
            notice = f"The selected model was unavailable; '{model_id}' answered instead."
        completion = Completion(
            content=str(raw.get("content") or ""),
            model_id=model_id,
            family=model_family(model_id),
            task=task,
            mode="manual" if pinned else "auto",
            pinned_model_id=pinned,
            pin_honored=honored,
            switched=switched,
            attempted_models=attempted,
            routing_score=raw.get("routing_score"),
            notice=notice,
        )
        logger.info(
            "model_router.complete intent=%s task=%s mode=%s model=%s family=%s switched=%s pin_honored=%s",
            intent,
            task,
            completion.mode,
            model_id,
            completion.family,
            switched,
            honored,
        )
        return completion

    def generator_for(self, intent: str, *, preferred_model_id: str | None = None) -> IntentGenerator:
        """A ``generate_with_fallback``-shaped object the pipelines accept, bound to one intent."""
        return IntentGenerator(self, intent, preferred_model_id)


@dataclass
class IntentGenerator:
    """Adapts :class:`ModelRouter` to the generator protocol used by the pipelines.

    Collects every :class:`Completion` of a request (analysis, repair, intent stage)
    so the response can report the models used and any pin that was not honored.
    """

    router: ModelRouter
    intent: str
    preferred_model_id: str | None = None
    completions: list[Completion] = field(default_factory=list)

    def generate_with_fallback(self, task: str, prompt: str, **kwargs: Any) -> dict:
        languages = kwargs.get("preferred_languages") or ("en",)
        options = CompletionOptions(
            system_prompt=str(kwargs.get("system_prompt") or ""),
            token_budget=int(kwargs.get("token_budget") or 1024),
            language=str(languages[0]),
            preferred_model_id=kwargs.get("preferred_model_id") or self.preferred_model_id,
        )
        completion = self.router.complete(self.intent, prompt, options)
        self.completions.append(completion)
        return {"content": completion.content, "model_id": completion.model_id}

    def notices(self) -> list[str]:
        """Distinct user-facing notices (e.g. pinned model unavailable)."""
        return sorted({c.notice for c in self.completions if c.notice})
