"""Operator overrides for the model registry (``models enable`` / ``models disable``).

Two small JSON files, both optional:

* overrides  — ``{"disabled": [model_id, ...], "enabled_discovered": [model_id, ...]}``
* discovered — metadata of models found by ``models refresh``, kept for review

A disabled model is never routed (the router's elimination stage honours
``ModelMetadata.enabled``). A *discovered* model only becomes routable after
an explicit ``models enable`` — and even then the license approval policy still
applies, so ``REQUIRES_REVIEW`` / ``BLOCKED`` models stay out.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from app.application.services.ai_registry import ModelMetadata

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path.home() / ".config" / "ai-career-assistant"


def overrides_path() -> Path:
    return Path(os.getenv("AI_MODEL_OVERRIDES_FILE") or _DEFAULT_DIR / "model_overrides.json")


def discovered_path() -> Path:
    return Path(os.getenv("AI_DISCOVERED_MODELS_FILE") or _DEFAULT_DIR / "discovered_models.json")


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("ai.overrides unreadable path=%s error=%s", path, type(exc).__name__)
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)  # atomic on POSIX: readers never see a half-written file


def load_overrides() -> dict[str, list[str]]:
    data = _read(overrides_path())
    return {
        "disabled": sorted({str(item) for item in data.get("disabled", []) if item}),
        "enabled_discovered": sorted({str(item) for item in data.get("enabled_discovered", []) if item}),
    }


def save_overrides(overrides: dict[str, list[str]]) -> None:
    _write(overrides_path(), {key: sorted(set(value)) for key, value in overrides.items()})


def set_disabled(model_id: str, disabled: bool) -> dict[str, list[str]]:
    overrides = load_overrides()
    current = set(overrides["disabled"])
    (current.add if disabled else current.discard)(model_id)
    overrides["disabled"] = sorted(current)
    save_overrides(overrides)
    return overrides


def enable_discovered(model_id: str) -> None:
    overrides = load_overrides()
    overrides["enabled_discovered"] = sorted({*overrides["enabled_discovered"], model_id})
    overrides["disabled"] = [item for item in overrides["disabled"] if item != model_id]
    save_overrides(overrides)


def save_discovered(models: list[ModelMetadata]) -> None:
    _write(discovered_path(), {"models": [asdict(model) for model in models]})


def load_discovered() -> list[ModelMetadata]:
    names = {field.name for field in fields(ModelMetadata)}
    result: list[ModelMetadata] = []
    for item in _read(discovered_path()).get("models", []):
        if not isinstance(item, dict) or not item.get("model_id"):
            continue
        values = {
            key: (tuple(value) if isinstance(value, list) else value) for key, value in item.items() if key in names
        }
        try:
            result.append(ModelMetadata(**values))  # type: ignore[arg-type]  # keys filtered to real fields above
        except TypeError:
            continue
    return result


def apply_overrides(router: Any) -> None:
    """Apply the operator's choices to ``router`` (call right after creating it)."""
    overrides = load_overrides()
    wanted = set(overrides["enabled_discovered"])
    if wanted:
        router.add_models([model for model in load_discovered() if model.model_id in wanted])
    for model_id in overrides["disabled"]:
        router.set_model_enabled(model_id, False)
