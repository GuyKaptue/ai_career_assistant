"""Token-aware routing helpers (DYNAMIC_HF_PROMPT §9/§10).

``TokenizerService`` counts tokens with the model's own tokenizer whenever
that tokenizer is available locally (exact count). Otherwise it falls back to
a documented conservative estimator which is ALWAYS marked as an estimate —
an estimate is never presented as an exact token count (§10), and
``len(text) / 4`` is never used as the production source of truth.

required_context = input_tokens + reserved_output_tokens + system_prompt_tokens
                  + safety_margin   (§9, configurable margin)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable

from app.core.config import settings

logger = logging.getLogger(__name__)

# Conservative estimator: ~3 characters per token overshoots typical English
# BPE (roughly 4 chars/token), so oversized prompts are rejected during the
# pre-check instead of at the provider. Versioned source string so logs and
# audit records can tell estimates apart from exact counts.
ESTIMATOR_SOURCE = "estimator:conservative-v1"
ESTIMATOR_CHARS_PER_TOKEN = 3


@dataclass(frozen=True)
class TokenCount:
    """A token count plus its provenance — ``exact`` vs documented estimate."""

    value: int
    exact: bool
    source: str  # "tokenizer:<model_id>" or ESTIMATOR_SOURCE


@dataclass(frozen=True)
class ContextRequirement:
    """required_context breakdown (§9) — every component is visible."""

    input_tokens: int
    system_tokens: int
    reserved_output_tokens: int
    safety_margin: int
    exact: bool

    @property
    def total(self) -> int:
        """required_context = input + system + reserved output + margin."""
        return self.input_tokens + self.system_tokens + self.reserved_output_tokens + self.safety_margin


class TokenizerService:
    """Count tokens and pre-check context fit before every model request.

    Modes:
      * ``auto`` — exact when the model's tokenizer.json is in the local HF
        cache (or a custom loader provides it), otherwise the estimator.
      * ``exact`` — prefer exact only; if unavailable, falls back to the
        estimator with a warning (the result stays marked ``exact=False``).
      * ``estimate`` — never touch tokenizers; always the documented
        estimator (deterministic, hermetic for tests).
    """

    def __init__(
        self,
        mode: str = "auto",
        safety_margin: int | None = None,
        tokenizer_loader: Callable[[str], object | None] | None = None,
    ) -> None:
        if mode not in {"auto", "exact", "estimate"}:
            raise ValueError(f"Unknown tokenizer mode '{mode}' (expected auto|exact|estimate)")
        self.mode = mode
        self.safety_margin = settings.context_safety_margin if safety_margin is None else safety_margin
        self._loader = tokenizer_loader
        self._tokenizers: dict[str, object] = {}

    # ------------------------------------------------------------------ #
    # Counting
    # ------------------------------------------------------------------ #
    def count(self, text: str, model_id: str | None = None) -> TokenCount:
        """Token count for ``text``; provenance says exact vs estimated."""
        if self.mode in {"auto", "exact"} and model_id:
            tokenizer = self._load_exact(model_id)
            if tokenizer is not None:
                encoded = tokenizer.encode(text, add_special_tokens=False)  # type: ignore[attr-defined]
                return TokenCount(value=len(encoded), exact=True, source=f"tokenizer:{model_id}")
        if self.mode == "exact":
            logger.warning(
                "ai.tokenizer exact count unavailable model=%s; using documented estimator (marked estimated)",
                model_id,
            )
        return self._estimate(text)

    @staticmethod
    def _estimate(text: str) -> TokenCount:
        """Documented conservative estimator — never presented as exact."""
        value = max(1, math.ceil(len(text) / ESTIMATOR_CHARS_PER_TOKEN))
        return TokenCount(value=value, exact=False, source=ESTIMATOR_SOURCE)

    def required_context(
        self,
        *,
        system_prompt: str,
        user_input: str,
        reserved_output_tokens: int,
        model_id: str | None = None,
        safety_margin: int | None = None,
    ) -> ContextRequirement:
        """Compute required_context per §9 before the model request."""
        margin = self.safety_margin if safety_margin is None else safety_margin
        system = self.count(system_prompt or "", model_id)
        user = self.count(user_input or "", model_id)
        return ContextRequirement(
            input_tokens=user.value,
            system_tokens=system.value,
            reserved_output_tokens=max(0, int(reserved_output_tokens)),
            safety_margin=max(0, int(margin)),
            exact=system.exact and user.exact,
        )

    @staticmethod
    def fits(requirement: ContextRequirement, context_window: int | None) -> bool | None:
        """Pre-check ``required_context <= window`` (§9).

        Returns ``None`` when the window is unknown — an unknown value can
        neither prove nor disprove fit, and unknown must stay unknown (§4).
        """
        if context_window is None:
            return None
        return requirement.total <= context_window

    # ------------------------------------------------------------------ #
    # Exact backend (local cache only — no implicit network access)
    # ------------------------------------------------------------------ #
    def _load_exact(self, model_id: str) -> object | None:
        if model_id in self._tokenizers:
            return self._tokenizers[model_id]
        tokenizer = self._load_via_cache(model_id)
        if tokenizer is not None:
            self._tokenizers[model_id] = tokenizer
        return tokenizer

    def _load_via_cache(self, model_id: str) -> object | None:
        if self._loader is not None:
            try:
                return self._loader(model_id)
            except Exception as exc:  # pragma: no cover - custom backends
                logger.warning("ai.tokenizer custom loader failed model=%s: %s", model_id, exc)
                return None
        try:
            from huggingface_hub import try_to_load_from_cache
            from tokenizers import Tokenizer
        except ImportError:
            return None
        path = try_to_load_from_cache(repo_id=model_id, filename="tokenizer.json")
        if not isinstance(path, str):  # missing or "cached no exist" sentinel
            return None
        try:
            return Tokenizer.from_file(path)
        except Exception as exc:
            logger.warning("ai.tokenizer could not load cached tokenizer model=%s: %s", model_id, exc)
            return None

    def warmup(self, model_id: str) -> bool:
        """Explicitly download ``tokenizer.json`` into the local HF cache.

        The only network-touching method; routing itself never triggers an
        implicit download. Returns True when the exact tokenizer is now
        available locally.
        """
        try:
            from huggingface_hub import hf_hub_download

            # nosec B615 - best-effort tokenizer warmup for a dynamic model id;
            # pinning an immutable revision per arbitrary model is infeasible here.
            # Call is exception-guarded and never touches model weights or user data.
            hf_hub_download(repo_id=model_id, filename="tokenizer.json")  # nosec B615
        except Exception as exc:
            logger.info("ai.tokenizer warmup unavailable model=%s: %s", model_id, exc)
            return False
        self._tokenizers.pop(model_id, None)
        return self._load_exact(model_id) is not None
