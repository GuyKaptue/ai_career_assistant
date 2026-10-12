"""Weighted routing score with eliminate-then-rank (DYNAMIC_HF_PROMPT §11).

    Score(m, r) =
        w_task      × TaskCompatibility
      + w_language  × LanguageCompatibility
      + w_context   × ContextFit
      + w_quality   × QualityScore
      + w_latency   × PerformanceScore
      + w_resource  × ResourceFit
      + w_health    × HealthScore
      + w_cost      × CostScore

Weights are configurable (``ROUTING_WEIGHTS=task=0.3,language=0.2,...``).
Incompatible models are ELIMINATED first; only eligible candidates are
ranked. Components whose value is unknown for the whole cohort (for example
quality when no empirical benchmark exists) are excluded and their weight is
renormalized across the known components — an unknown is never imputed (§11).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.application.services.ai_profiles import get_task_profile
from app.application.services.ai_registry import (
    AI_TASKS,
    LICENSE_APPROVED,
    LICENSE_BLOCKED,
    ModelApprovalPolicy,
    ModelMetadata,
    normalize_task,
)
from app.application.services.ai_tokenizer import ContextRequirement

logger = logging.getLogger(__name__)

WEIGHT_NAMES = ("task", "language", "context", "quality", "latency", "resource", "health", "cost")

# Health degrades score but never eliminates on its own (§11 health component).
HEALTH_SCORES = {"healthy": 1.0, "degraded": 0.5, "unhealthy": 0.0}


@dataclass(frozen=True)
class RoutingWeights:
    """Configurable Score(m, r) weights (§11). Renormalized during rank()."""

    task: float = 0.25
    language: float = 0.15
    context: float = 0.15
    quality: float = 0.15
    latency: float = 0.05
    resource: float = 0.05
    health: float = 0.15
    cost: float = 0.05

    @classmethod
    def from_string(cls, raw: str) -> "RoutingWeights":
        """Parse ``task=0.3,language=0.2`` style config; empty -> defaults.

        Raises ``ValueError`` on unknown keys or invalid numbers so bad
        configuration surfaces instead of silently routing differently.
        """
        if not raw or not raw.strip():
            return cls()
        values = {name: getattr(cls(), name) for name in WEIGHT_NAMES}
        for pair in raw.split(","):
            item = pair.strip()
            if not item:
                continue
            if "=" not in item:
                raise ValueError(f"Invalid ROUTING_WEIGHTS entry '{item}' (expected name=value)")
            key, _, value = item.partition("=")
            key = key.strip()
            if key not in values:
                raise ValueError(f"Unknown routing weight '{key}' (expected one of {', '.join(WEIGHT_NAMES)})")
            try:
                weight = float(value.strip())
            except ValueError as exc:
                raise ValueError(f"Routing weight '{key}' must be a number") from exc
            if weight < 0:
                raise ValueError(f"Routing weight '{key}' must not be negative")
            values[key] = weight
        if sum(values.values()) <= 0:
            raise ValueError("ROUTING_WEIGHTS must contain at least one positive weight")
        return cls(**values)

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in WEIGHT_NAMES}


@dataclass(frozen=True)
class RoutingRequest:
    """Everything the selector needs to decide for one inference request."""

    task: str
    requirement: ContextRequirement
    preferred_languages: tuple[str, ...] = ()
    weights: RoutingWeights = RoutingWeights()


@dataclass(frozen=True)
class EliminationOutcome:
    """Hard-filter result: eligible models plus auditable eliminations (§11)."""

    eligible: tuple[ModelMetadata, ...]
    eliminated: tuple[tuple[ModelMetadata, str], ...]  # (model, reason)
    notes: tuple[str, ...]  # relaxation notes, e.g. "language_filter_relaxed"


def _capability_gap(model: ModelMetadata, task: str) -> str | None:
    profile = get_task_profile(task)
    if profile is None or not model.capabilities:
        return None  # unknown task or unknown capabilities: not incompatible
    covers = model.covers_capabilities(profile.required_capabilities)
    if covers is False:
        missing = sorted(set(profile.required_capabilities) - {normalize_task(cap) for cap in model.capabilities})
        return f"capability_gap:{','.join(missing)}"
    return None


def eliminate(
    models: tuple[ModelMetadata, ...],
    request: RoutingRequest,
    policy: ModelApprovalPolicy,
) -> EliminationOutcome:
    """Eliminate incompatible models, then relax soft filters only if empty.

    Permanent filters: disabled, task mismatch, capability gap, license
    policy, context pre-check. Soft filters (language, health) eliminate for
    ranking fairness but are relaxed stepwise when nothing survives, so a
    degraded model still beats no model at all.
    """
    task = normalize_task(request.task)
    eligible: list[ModelMetadata] = []
    eliminated: list[tuple[ModelMetadata, str]] = []
    language_miss: list[ModelMetadata] = []
    unhealthy: list[ModelMetadata] = []
    notes: list[str] = []
    preferred = tuple({normalize_task(lang) for lang in request.preferred_languages if lang})
    required_total = request.requirement.total

    for model in models:
        if not model.enabled:
            eliminated.append((model, "disabled"))
            continue
        if task not in AI_TASKS or not model.supports_task(task):
            eliminated.append((model, "task_mismatch"))
            continue
        if model.inference_provider_supported is False:
            # Verified by the provider as unable to serve this call: skip it
            # before ranking so auto-selection never picks a model that can
            # only fail. Unknown (None) is not treated as unsupported.
            eliminated.append((model, "not_supported_by_provider"))
            continue
        gap = _capability_gap(model, task)
        if gap is not None:
            eliminated.append((model, gap))
            continue
        status = policy.evaluate(model)
        if status == LICENSE_BLOCKED:
            eliminated.append((model, "license_blocked"))
            continue
        if status != LICENSE_APPROVED and model.model_id not in policy.approved_review_ids:
            eliminated.append((model, f"license_{status.lower()}"))
            continue
        window = model.context_window
        if window is not None and required_total > window:
            eliminated.append((model, f"context_limit_exceeded:required={required_total},window={window}"))
            continue
        if model.health_status == "unhealthy":
            unhealthy.append(model)
            continue
        preferred_set = set(preferred)
        if preferred_set and not (preferred_set & {normalize_task(lang) for lang in model.supported_languages}):
            language_miss.append(model)
            continue
        eligible.append(model)

    # Soft-filter relaxation: language first, then health — only when empty.
    if not eligible and language_miss:
        eligible = list(language_miss)
        notes.append("language_filter_relaxed")
    if not eligible and unhealthy:
        eligible = list(unhealthy)
        notes.append("health_filter_relaxed")

    return EliminationOutcome(
        eligible=tuple(eligible),
        eliminated=tuple(eliminated),
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class RankedModel:
    """One ranked candidate with its explainable score breakdown (§26)."""

    model: ModelMetadata
    score: float
    components: dict[str, float]  # component -> achieved value in [0, 1]
    weights_used: dict[str, float]  # component -> weight actually applied


def _cohort_components(
    eligible: tuple[ModelMetadata, ...],
    request: RoutingRequest,
) -> dict[str, bool]:
    """Decide cohort-wide which components have known values for ALL models.

    Comparing scores across different component sets would be unfair, so a
    component participates only when every candidate provides it. ``cost`` is
    never available: no cost metadata exists, and inventing it is forbidden.
    """
    windows_known = all(model.context_window is not None for model in eligible)
    quality_known = all(model.quality_score is not None for model in eligible)
    latency_known = all(model.estimated_latency is not None for model in eligible)
    memory_known = all(model.estimated_memory_requirement is not None for model in eligible)
    return {
        "task": True,
        "language": bool(request.preferred_languages),
        "context": windows_known,
        "quality": quality_known,
        "latency": latency_known,
        "resource": memory_known,
        "health": True,
        "cost": False,
    }


def _component_values(
    model: ModelMetadata,
    request: RoutingRequest,
    available: dict[str, bool],
    min_memory_mb: int,
) -> dict[str, float]:
    """Achieved value per available component, all within [0, 1]."""
    values: dict[str, float] = {}
    task = normalize_task(request.task)
    profile = get_task_profile(task)
    if available["task"]:
        if profile is None:
            values["task"] = 1.0
        else:
            declared = {normalize_task(cap) for cap in model.capabilities} or None
            if declared is None:
                values["task"] = 1.0  # capabilities unknown: not penalized
            else:
                covered = len(declared & set(profile.required_capabilities))
                values["task"] = covered / len(profile.required_capabilities)
    if available["language"]:
        preferred = {normalize_task(lang) for lang in request.preferred_languages}
        supported = {normalize_task(lang) for lang in model.supported_languages}
        values["language"] = 1.0 if preferred & supported else 0.0
    if available["context"]:
        window = model.context_window or 0
        required = max(request.requirement.total, 1)
        # Full score once the window holds 2x the required context; below
        # that, tighter fits score lower (headroom is a routing asset, §11).
        values["context"] = min(1.0, window / (2.0 * required))
    if available["quality"]:
        values["quality"] = min(1.0, max(0.0, float(model.quality_score or 0.0)))
    if available["latency"]:
        latency_ms = float(model.estimated_latency or 0.0)
        values["latency"] = 1.0 if latency_ms <= 0 else min(1.0, 1000.0 / latency_ms)
    if available["resource"]:
        memory_mb = int(model.estimated_memory_requirement or 0)
        values["resource"] = 1.0 if memory_mb <= 0 else min_memory_mb / memory_mb
    if available["health"]:
        values["health"] = HEALTH_SCORES.get(model.health_status, 0.25)
    return values


def rank(
    eligible: tuple[ModelMetadata, ...],
    request: RoutingRequest,
) -> list[RankedModel]:
    """Rank eligible candidates by weighted Score(m, r) (§11).

    Unknown cohort components drop out and the remaining weights are
    renormalized — quality of 0.5 is never invented to fill the gap.
    """
    if not eligible:
        return []
    available = _cohort_components(eligible, request)
    weights = request.weights
    min_memory = min((model.estimated_memory_requirement or 0) for model in eligible) if available["resource"] else 0

    ranked: list[RankedModel] = []
    for model in eligible:
        values = _component_values(model, request, available, max(min_memory, 1))
        used_weights = {name: getattr(weights, name) for name, on in available.items() if on}
        total_weight = sum(used_weights.values()) or 1.0
        score = sum(used_weights[name] * values[name] for name in used_weights) / total_weight
        ranked.append(RankedModel(model=model, score=round(score, 6), components=values, weights_used=used_weights))

    # Deterministic ordering: score first, then larger context window, then id.
    ranked.sort(
        key=lambda item: (
            -item.score,
            -(item.model.context_window or 0),
            item.model.model_id,
        )
    )
    return ranked
