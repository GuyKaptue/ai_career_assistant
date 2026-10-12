from __future__ import annotations

import logging
import os
import time
from dataclasses import replace
from typing import Iterable, Sequence

from app.application.services.ai_profiles import get_task_profile
from app.application.services.ai_registry import (
    ModelApprovalPolicy,
    ModelMetadata,
    normalize_task,
)
from app.application.services.ai_scoring import (
    EliminationOutcome,
    RankedModel,
    RoutingRequest,
    RoutingWeights,
    eliminate,
    rank,
)
from app.application.services.ai_tokenizer import ContextRequirement, TokenizerService
from app.application.services.model_catalog import build_model_pool
from app.core.config import settings
from app.core.errors import AIProviderError
from app.core.metrics import METRICS

# ModelMetadata (DYNAMIC_HF_PROMPT §4) is defined in ai_registry so the
# registry, approval policy, discovery and routing share one definition;
# it is re-exported here for backwards-compatible imports.
__all__ = [
    "CONTEXT_LENGTH_EXCEEDED",
    "MODEL_UNAVAILABLE",
    "QUOTA_EXCEEDED",
    "RATE_LIMITED",
    "RESOURCE_EXHAUSTED",
    "SCHEMA_VALIDATION_FAILED",
    "TIMEOUT",
    "CircuitBreaker",
    "HuggingFaceInferenceAdapter",
    "HuggingFaceModelRouter",
    "ModelMetadata",
    "TYPED_FAILURES",
    "classify_failure",
]

logger = logging.getLogger(__name__)


# Typed failure taxonomy (DYNAMIC_HF_PROMPT §14). Each failure maps to a
# deterministic action instead of blind `use_next_model()`.
CONTEXT_LENGTH_EXCEEDED = "CONTEXT_LENGTH_EXCEEDED"
RATE_LIMITED = "RATE_LIMITED"
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
TIMEOUT = "TIMEOUT"
RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"


# Deterministic action per failure (DYNAMIC_HF_PROMPT §14): only transient
# failures are retried on the SAME model with backoff; every other typed
# failure switches to the next candidate instead of retrying blindly.
RETRYABLE_FAILURES = frozenset({RATE_LIMITED, TIMEOUT, SCHEMA_VALIDATION_FAILED})

TYPED_FAILURES = (
    CONTEXT_LENGTH_EXCEEDED,
    RATE_LIMITED,
    QUOTA_EXCEEDED,
    TIMEOUT,
    RESOURCE_EXHAUSTED,
    SCHEMA_VALIDATION_FAILED,
    MODEL_UNAVAILABLE,
)


def classify_failure(exc: Exception) -> str:
    """Map an exception onto the typed failure taxonomy (§14).

    Exceptions that already carry a taxonomy prefix pass through unchanged;
    raw provider errors are matched by keyword. Unknown errors are treated
    as MODEL_UNAVAILABLE (fail closed, never fail open).
    """
    message = str(exc)
    for failure_type in TYPED_FAILURES:
        if message.startswith(failure_type):
            return failure_type
    lowered = message.lower()
    if "429" in lowered or "rate limit" in lowered:
        return RATE_LIMITED
    if "quota" in lowered or "403" in lowered or "payment" in lowered:
        return QUOTA_EXCEEDED
    if "timeout" in lowered or "timed out" in lowered:
        return TIMEOUT
    if "context" in lowered and ("length" in lowered or "window" in lowered or "too long" in lowered):
        return CONTEXT_LENGTH_EXCEEDED
    if "memory" in lowered or "cuda out" in lowered or "oom" in lowered:
        return RESOURCE_EXHAUSTED
    return MODEL_UNAVAILABLE


def _health_gauge(health_status: str) -> float:
    """Map health_status onto the §28 ``ai_model_health`` gauge (1.0/0.5/0.0)."""
    return {"healthy": 1.0, "degraded": 0.5, "unhealthy": 0.0}.get(health_status, 0.25)


class CircuitBreaker:
    """Protect a remote call site from repeated failures.

    States: CLOSED (normal) -> OPEN (fail fast) -> HALF_OPEN (probe) ->
    back to CLOSED on success or back to OPEN on failure.
    """

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._state: str = "CLOSED"
        self._failure_count = 0
        self._last_failure_time = 0.0
        # Observability fields required by DYNAMIC_HF_PROMPT §17.
        self.last_failure_type: str | None = None
        self.success_count = 0

    @property
    def state(self) -> str:
        return self._state

    def allow_request(self) -> bool:
        if self._state == "CLOSED":
            return True
        if self._state == "HALF_OPEN":
            return True
        # OPEN: fail fast unless reset_timeout has elapsed
        return time.monotonic() - self._last_failure_time >= self.reset_timeout

    def mark_success(self) -> None:
        self.success_count += 1
        if self._state == "OPEN":
            self._state = "HALF_OPEN"
            self._failure_count = 0
            logger.info("ai.circuitbreaker half_open")
        elif self._state == "HALF_OPEN":
            self._state = "CLOSED"
            self._failure_count = 0
            logger.info("ai.circuitbreaker closed")

    def mark_failure(self, failure_type: str | None = None) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if failure_type is not None:
            self.last_failure_type = failure_type
        if self._state == "HALF_OPEN":
            self._state = "OPEN"
            logger.warning("ai.circuitbreaker open failures=%d", self._failure_count)
        elif self._state == "CLOSED" and self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning("ai.circuitbreaker open failures=%d", self._failure_count)

    def force_open(self) -> None:
        """Trip the breaker without waiting for the failure threshold.

        Used for deterministic per-class actions (§14: MODEL_UNAVAILABLE →
        mark unhealthy, open circuit, select another model). Callers must
        have recorded the failure via ``mark_failure`` first.
        """
        self._state = "OPEN"
        self._last_failure_time = time.monotonic()
        logger.warning("ai.circuitbreaker open (forced) failures=%d", self._failure_count)

    def was_open(self) -> bool:
        return self._state == "OPEN"


def _explain(
    task: str,
    best: RankedModel,
    ranked: list[RankedModel],
    outcome: EliminationOutcome,
    request: RoutingRequest,
) -> list[str]:
    """§26 human-readable selection reasons (for structured logs/audit data)."""
    model = best.model
    normalized = normalize_task(task)
    profile = get_task_profile(normalized)
    reasons: list[str] = []
    if profile is not None:
        reasons.append(f"task {normalized} compatible (profile: {', '.join(profile.required_capabilities)})")
    else:
        reasons.append(f"task {normalized} supported")
    if request.preferred_languages:
        reasons.append(f"language {', '.join(request.preferred_languages)} supported")
    if model.context_window is None:
        reasons.append("context window unknown — fit not verifiable, not fabricated")
    else:
        reasons.append(f"required context {request.requirement.total} fits window {model.context_window}")
    reasons.append(f"license {model.license_policy_status or 'unknown'}")
    reasons.append(f"health {model.health_status}")
    if model.quality_score is not None:
        reasons.append(f"quality benchmark {model.quality_score}")
    else:
        reasons.append("quality score unavailable (no empirical benchmark)")
    alternatives = len(ranked) - 1
    if alternatives:
        reasons.append(f"routing score {best.score} higher than {alternatives} alternative(s)")
    else:
        reasons.append(f"routing score {best.score} (only eligible candidate)")
    if outcome.notes:
        reasons.append(f"soft filters relaxed: {', '.join(outcome.notes)}")
    return reasons


class HuggingFaceModelRouter:
    """Choose the best candidate model for a task with deterministic failover.

    Selection pipeline (DYNAMIC_HF_PROMPT §9/§11/§12):
    token-aware pre-check → eliminate-then-rank weighted Score(m, r) →
    dynamically generated fallback chain → bounded, taxonomy-driven failover.
    """

    def __init__(
        self,
        models: Iterable[ModelMetadata] | None = None,
        *,
        policy: ModelApprovalPolicy | None = None,
        tokenizer: TokenizerService | None = None,
        weights: RoutingWeights | None = None,
    ) -> None:
        registered = build_model_pool()
        default_models = tuple(registered)
        resolved = tuple(models or default_models)
        self._policy = policy or ModelApprovalPolicy.from_settings()
        self._tokenizer = tokenizer or TokenizerService()
        self._weights = weights or self._load_weights()
        self._max_depth = max(1, settings.ai_max_fallback_depth)
        # Stamp the §6 approval status on every registered model (§4 field).
        self._models = tuple(replace(model, license_policy_status=self._policy.evaluate(model)) for model in resolved)
        self._circuit_breakers: dict[str, CircuitBreaker] = {model.model_id: CircuitBreaker() for model in self._models}
        for model in self._models:
            METRICS.set_gauge("ai_model_health", _health_gauge(model.health_status), model=model.model_id)

    @staticmethod
    def _load_weights() -> RoutingWeights:
        """ROUTING_WEIGHTS config with a logged fallback to defaults (§11)."""
        try:
            return RoutingWeights.from_string(settings.routing_weights)
        except ValueError as exc:
            logger.warning("ai.routing invalid ROUTING_WEIGHTS (%s); using defaults", exc)
            return RoutingWeights()

    def add_models(self, models: Iterable[ModelMetadata]) -> None:
        """Register additional (e.g. discovered) models at runtime (§5)."""
        known = {model.model_id for model in self._models}
        for model in models:
            if model.model_id in known:
                continue
            stamped = replace(model, license_policy_status=self._policy.evaluate(model))
            self._models = (*self._models, stamped)
            self._circuit_breakers[stamped.model_id] = CircuitBreaker()
            METRICS.set_gauge("ai_model_health", _health_gauge(stamped.health_status), model=stamped.model_id)
            known.add(stamped.model_id)

    def set_model_enabled(self, model_id: str, enabled: bool) -> bool:
        """Enable/disable a registered model (operator override). Returns False if unknown."""
        found = False
        updated = []
        for model in self._models:
            if model.model_id == model_id:
                found = True
                model = replace(model, enabled=enabled)
            updated.append(model)
        self._models = tuple(updated)
        return found

    def _circuit_breaker(self, model: ModelMetadata) -> CircuitBreaker:
        return self._circuit_breakers.get(model.model_id, CircuitBreaker())

    @property
    def models(self) -> tuple[ModelMetadata, ...]:
        return self._models

    def list_models(self, task: str | None = None) -> list[ModelMetadata]:
        candidates = list(self._models)
        if task is not None:
            candidates = [model for model in candidates if model.supports_task(task) and model.enabled]
        return sorted(
            candidates,
            key=lambda model: (
                -float(model.quality_score if model.quality_score is not None else 0.0),
                -(model.context_window or 0),
            ),
        )

    # ------------------------------------------------------------------ #
    # Token-aware selection (§9) + eliminate-then-rank scoring (§11)
    # ------------------------------------------------------------------ #
    def _build_request(
        self,
        task: str,
        token_budget: int,
        preferred_languages: Sequence[str] = (),
        *,
        system_prompt: str = "",
        user_input: str = "",
    ) -> RoutingRequest:
        if system_prompt or user_input:
            # Full §9 formula: input + reserved output + system + safety margin.
            requirement = self._tokenizer.required_context(
                system_prompt=system_prompt,
                user_input=user_input,
                reserved_output_tokens=token_budget,
            )
        else:
            # select_model()/route() callers pass their context budget directly.
            requirement = ContextRequirement(
                input_tokens=max(0, int(token_budget)),
                system_tokens=0,
                reserved_output_tokens=0,
                safety_margin=0,
                exact=False,
            )
        return RoutingRequest(
            task=task,
            requirement=requirement,
            preferred_languages=tuple(preferred_languages),
            weights=self._weights,
        )

    def _evaluate(self, request: RoutingRequest) -> tuple[EliminationOutcome, list[RankedModel]]:
        """Eliminate incompatible models (recording why), then rank the rest."""
        outcome = eliminate(self._models, request, self._policy)
        for _model, reason in outcome.eliminated:
            if reason.startswith("context_limit_exceeded"):
                METRICS.inc("ai_context_limit_total", task=request.task)
        return outcome, rank(outcome.eligible, request)

    def rank_candidates(
        self,
        task: str,
        token_budget: int = 4096,
        preferred_languages: Sequence[str] = (),
    ) -> tuple[RoutingRequest, EliminationOutcome, list[RankedModel]]:
        """Eliminate + rank for a context budget; raises when nothing fits."""
        request = self._build_request(task, token_budget, preferred_languages)
        outcome, ranked = self._evaluate(request)
        if not ranked:
            detail = "; ".join(f"{model.model_id}: {reason}" for model, reason in outcome.eliminated)
            raise ValueError(
                f"No compatible Hugging Face model is enabled for task '{task}'" + (f" ({detail})" if detail else ".")
            )
        METRICS.inc("ai_model_selected_total", model=ranked[0].model.model_id, task=task)
        return request, outcome, ranked

    def select_model(
        self,
        task: str,
        token_budget: int = 4096,
        preferred_languages: Sequence[str] = (),
    ) -> ModelMetadata:
        """Best eligible model after eliminate-then-rank (§11)."""
        _request, _outcome, ranked = self.rank_candidates(
            task, token_budget=token_budget, preferred_languages=preferred_languages
        )
        return ranked[0].model

    def fallback_chain(
        self,
        task: str,
        token_budget: int = 4096,
        preferred_languages: Sequence[str] = (),
    ) -> list[ModelMetadata]:
        """Dynamically generated per-task fallback chain (§12).

        The order comes from the live ranking over task, language, token
        requirement, license, health and capabilities, and is bounded by
        ``AI_MAX_FALLBACK_DEPTH`` — the spec's example chains are never
        hard-coded as universal truth.
        """
        _request, _outcome, ranked = self.rank_candidates(
            task, token_budget=token_budget, preferred_languages=preferred_languages
        )
        return [item.model for item in ranked[: self._max_depth]]

    def route(
        self,
        task: str,
        token_budget: int = 4096,
        preferred_languages: Sequence[str] = (),
    ) -> dict:
        """Explainable routing decision — why this model was selected (§26)."""
        request, outcome, ranked = self.rank_candidates(
            task, token_budget=token_budget, preferred_languages=preferred_languages
        )
        best = ranked[0]
        selected = best.model
        return {
            "task": task,
            "model_id": selected.model_id,
            "reason": "highest routing score among eligible candidates",
            "context_window": selected.context_window,
            "health_status": selected.health_status,
            "routing_score": best.score,
            "components": dict(best.components),
            "weights": dict(best.weights_used),
            "eligible": [item.model.model_id for item in ranked],
            "eliminated": [{"model_id": model.model_id, "reason": reason} for model, reason in outcome.eliminated],
            "notes": list(outcome.notes),
            "license_policy_status": selected.license_policy_status,
            "required_context": request.requirement.total,
            "explanation": _explain(task, best, ranked, outcome, request),
        }

    def _call_model(self, model: ModelMetadata, prompt: str, max_new_tokens: int) -> str:
        """Execute the actual model call. Subclasses (adapters) override this."""
        raise NotImplementedError("Subclasses must implement _call_model")

    def _mark_model_unhealthy(self, model_id: str) -> None:
        """§14 action for MODEL_UNAVAILABLE: mark the model unhealthy.

        ``ModelMetadata`` is frozen, so the entry is replaced in place; the
        circuit breaker keeps rejecting traffic until the cooldown elapses.
        """
        for index, model in enumerate(self._models):
            if model.model_id == model_id and model.health_status != "unhealthy":
                self._models = (
                    *self._models[:index],
                    replace(model, health_status="unhealthy"),
                    *self._models[index + 1 :],
                )
                METRICS.set_gauge("ai_model_health", 0.0, model=model_id)
                logger.warning("ai.model marked unhealthy model=%s", model_id)
                return

    def generate_with_fallback(
        self,
        task: str,
        prompt: str,
        token_budget: int = 4096,
        preferred_languages: Sequence[str] = (),
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
        system_prompt: str = "",
        preferred_model_id: str | None = None,
    ) -> dict:
        """Run the dynamically generated fallback chain (§9/§12/§14).

        Uses the real §9 ``required_context`` formula for the pre-check,
        walks the ranked chain with taxonomy-driven bounded retries, and
        emits §28 metrics plus a content-free §27 fallback audit record.

        ``preferred_model_id`` pins a user-selected model (chat model picker)
        to the front of the chain. The pin only reorders the *already
        eliminated + ranked* candidates, so a pinned model that fails context,
        license or health elimination is silently skipped and the next eligible
        model is used — the deterministic fallback guarantees of §12/§14 are
        never weakened.
        """
        started = time.monotonic()
        METRICS.inc("ai_requests_total", task=task)
        request = self._build_request(
            task,
            token_budget,
            preferred_languages,
            system_prompt=system_prompt,
            user_input=prompt,
        )
        outcome, ranked = self._evaluate(request)
        chain = [item.model for item in ranked[: self._max_depth]]
        if preferred_model_id:
            pinned = [model for model in chain if model.model_id == preferred_model_id]
            if pinned:
                chain = pinned + [model for model in chain if model.model_id != preferred_model_id]
                logger.debug("ai.inference model pinned task=%s model=%s", task, preferred_model_id)
        if not chain:
            METRICS.inc("ai_requests_failed_total", task=task)
            detail = "; ".join(f"{model.model_id}: {reason}" for model, reason in outcome.eliminated)
            raise ValueError(
                f"No model candidates are available for task '{task}'" + (f" ({detail})" if detail else ".")
            )

        scores = {item.model.model_id: item.score for item in ranked}
        initial_model = chain[0].model_id
        failures: list[str] = []
        attempted: list[str] = []
        last_error: Exception | None = None
        for model in chain:
            breaker = self._circuit_breaker(model)
            if not breaker.allow_request():
                failures.append(f"{model.model_id}: circuit_breaker_open")
                METRICS.set_gauge("ai_model_circuit_open", 1, model=model.model_id)
                logger.warning(
                    "ai.inference skipped task=%s model=%s reason=circuit_breaker_open",
                    task,
                    model.model_id,
                )
                continue

            attempted.append(model.model_id)
            for attempt in range(max_retries):
                try:
                    text = self._call_model(model, prompt, max_new_tokens=token_budget)
                    breaker.mark_success()
                    METRICS.set_gauge("ai_model_circuit_open", 0, model=model.model_id)
                    latency_ms = int((time.monotonic() - started) * 1000)
                    METRICS.inc("ai_requests_success_total", task=task)
                    METRICS.inc("ai_model_selected_total", model=model.model_id, task=task)
                    METRICS.inc(
                        "ai_tokens_input_total",
                        request.requirement.input_tokens + request.requirement.system_tokens,
                    )
                    METRICS.inc("ai_tokens_output_total", self._tokenizer.count(text, model.model_id).value)
                    METRICS.observe("ai_latency_seconds", latency_ms / 1000.0, task=task)
                    if failures:
                        METRICS.inc("ai_model_fallback_total", task=task)
                    fallback_reason = "; ".join(failures) if failures else None
                    logger.info(
                        "ai.route task=%s model=%s score=%s attempt=%d fallback=%s",
                        task,
                        model.model_id,
                        scores.get(model.model_id),
                        attempt + 1,
                        bool(fallback_reason),
                    )
                    self._log_audit(
                        task=task,
                        initial_model=initial_model,
                        attempted=attempted,
                        final_model=model.model_id,
                        failures=failures,
                        success=True,
                        latency_ms=latency_ms,
                        requirement=request.requirement,
                    )
                    return {
                        "model_id": model.model_id,
                        "task": task,
                        "content": text,
                        "health_status": model.health_status,
                        "fallback_reason": fallback_reason,
                        "fallback_chain": list(attempted),
                        "routing_score": scores.get(model.model_id),
                        "required_context": request.requirement.total,
                        "required_context_exact": request.requirement.exact,
                    }
                except NotImplementedError:
                    # Base router used without an adapter: fail fast instead
                    # of marking every model unhealthy.
                    raise
                except Exception as exc:
                    last_error = exc
                    reason = str(exc)
                    failure_type = classify_failure(exc)
                    failures.append(f"{model.model_id}: {reason}")
                    breaker.mark_failure(failure_type)
                    self._record_failure_metrics(task, failure_type)
                    logger.warning(
                        "ai.inference failed task=%s model=%s attempt=%d type=%s reason=%s",
                        task,
                        model.model_id,
                        attempt + 1,
                        failure_type,
                        reason,
                    )
                    if failure_type == MODEL_UNAVAILABLE:
                        # §14 action: mark unhealthy, open circuit, select another model.
                        breaker.force_open()
                        self._mark_model_unhealthy(model.model_id)
                    if failure_type not in RETRYABLE_FAILURES:
                        # §14 action: switch model now instead of retrying blind.
                        logger.warning(
                            "ai.inference failover task=%s model=%s type=%s action=switch_model",
                            task,
                            model.model_id,
                            failure_type,
                        )
                        break
                    if attempt < max_retries - 1:
                        # §14 action for RATE_LIMITED/TIMEOUT/SCHEMA: bounded retry with backoff.
                        sleep_seconds = base_backoff_seconds * (2**attempt)
                        logger.debug(
                            "ai.inference retry task=%s model=%s in=%ss attempt=%d",
                            task,
                            model.model_id,
                            sleep_seconds,
                            attempt + 1,
                        )
                        time.sleep(sleep_seconds)

        latency_ms = int((time.monotonic() - started) * 1000)
        METRICS.inc("ai_requests_failed_total", task=task)
        self._log_audit(
            task=task,
            initial_model=initial_model,
            attempted=attempted,
            final_model=None,
            failures=failures,
            success=False,
            latency_ms=latency_ms,
            requirement=request.requirement,
        )
        message = f"All Hugging Face model candidates failed for task '{task}': " + "; ".join(failures)
        if last_error is not None:
            raise AIProviderError(message) from last_error
        raise AIProviderError(message)

    @staticmethod
    def _record_failure_metrics(task: str, failure_type: str) -> None:
        """Map typed failures onto the §28 metric families."""
        if failure_type == RATE_LIMITED:
            METRICS.inc("ai_rate_limit_total", task=task)
        elif failure_type == TIMEOUT:
            METRICS.inc("ai_timeout_total", task=task)
        elif failure_type == CONTEXT_LENGTH_EXCEEDED:
            METRICS.inc("ai_context_limit_total", task=task)
        else:
            METRICS.inc("ai_provider_failure_total", failure_type=failure_type, task=task)

    @staticmethod
    def _log_audit(
        *,
        task: str,
        initial_model: str,
        attempted: list[str],
        final_model: str | None,
        failures: list[str],
        success: bool,
        latency_ms: int,
        requirement: ContextRequirement,
    ) -> None:
        """§27 fallback audit trail — never includes prompts or user content."""
        logger.info(
            "ai.fallback_audit task=%s initial_model=%s candidate_models=%s final_model=%s "
            "input_token_estimate=%d reserved_output=%d required_context=%d context_exact=%s "
            "failure_count=%d fallback_reason=%s success=%s latency_ms=%d",
            task,
            initial_model,
            ",".join(attempted),
            final_model or "-",
            requirement.input_tokens + requirement.system_tokens,
            requirement.reserved_output_tokens,
            requirement.total,
            requirement.exact,
            len(failures),
            "; ".join(failures)[:500] if failures else "-",
            success,
            latency_ms,
        )


class HuggingFaceInferenceAdapter(HuggingFaceModelRouter):
    """Call Hugging Face Inference API with deterministic per-task fallback.

    - Selects candidates via the router (task + context + language + health).
    - Calls each candidate in order; maps provider errors to the typed
      failure taxonomy and continues to the next compatible model.
    - Never fabricates: if no candidate succeeds, raises AIProviderError
      with the last failure reason (caller decides fallback to local
      templates).

    ``generate_with_fallback`` (circuit breaker + taxonomy-driven bounded
    retry) is inherited from ``HuggingFaceModelRouter``; only the model
    call itself is overridden here.
    """

    def __init__(self, router: HuggingFaceModelRouter | None = None) -> None:
        resolved = router if router is not None else HuggingFaceModelRouter()
        super().__init__(models=resolved.models)
        # Share the caller's breaker state so model health survives across instances.
        self._circuit_breakers = resolved._circuit_breakers
        self.router = resolved

    def _call_model(self, model: ModelMetadata, prompt: str, max_new_tokens: int) -> str:
        token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
        if not token:
            raise AIProviderError(f"{MODEL_UNAVAILABLE}: HF_TOKEN is not configured.")
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise AIProviderError(f"{MODEL_UNAVAILABLE}: huggingface_hub is not installed.") from exc

        client = InferenceClient(model=model.model_id, token=token, timeout=60.0)
        try:
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=min(max_new_tokens, model.max_output_tokens),
                temperature=0.7,
            )
            text = (completion.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception as chat_exc:
            # Fall through to text_generation for models that only support it.
            try:
                output = client.text_generation(
                    prompt,
                    max_new_tokens=min(max_new_tokens, model.max_output_tokens),
                    temperature=0.7,
                )
            except Exception:
                raise self._classify_error(chat_exc) from chat_exc
            text = output.strip() if isinstance(output, str) else str(output).strip()
            if text:
                return text
            raise self._classify_error(chat_exc) from chat_exc
        raise AIProviderError(f"{SCHEMA_VALIDATION_FAILED}: model returned empty output.")

    @staticmethod
    def _classify_error(exc: Exception) -> AIProviderError:
        message = str(exc)
        failure_type = classify_failure(exc)
        if message.startswith(failure_type):
            return AIProviderError(message)
        return AIProviderError(f"{failure_type}: {message}")
