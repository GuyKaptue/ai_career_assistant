"""Per-task routing profiles (DYNAMIC_HF_PROMPT §8).

Profiles are loaded from ``task_profiles.yaml`` next to this module and
validated strictly: unknown tasks, unknown capabilities or empty requirement
lists fail fast instead of silently degrading routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from app.application.services.ai_registry import AI_TASKS, CAPABILITIES, normalize_task

PROFILES_PATH = Path(__file__).with_name("task_profiles.yaml")


@dataclass(frozen=True)
class TaskProfile:
    """Routing requirements for one task (§8)."""

    task: str
    required_capabilities: tuple[str, ...]
    description: str = ""


def parse_profiles(data: Any, *, source: str = "task_profiles") -> dict[str, TaskProfile]:
    """Validate raw YAML data and return profiles keyed by normalized task."""
    if not isinstance(data, Mapping) or "tasks" not in data:
        raise ValueError(f"{source}: top-level 'tasks' mapping is required")
    tasks = data["tasks"]
    if not isinstance(tasks, Mapping) or not tasks:
        raise ValueError(f"{source}: 'tasks' must be a non-empty mapping")

    known_tasks = set(AI_TASKS)
    known_capabilities = set(CAPABILITIES)
    profiles: dict[str, TaskProfile] = {}
    for raw_task, spec in tasks.items():
        task = normalize_task(str(raw_task))
        if task not in known_tasks:
            raise ValueError(f"{source}: unknown task '{task}' (not in the 20-task capability model)")
        if task in profiles:
            raise ValueError(f"{source}: duplicate profile for task '{task}'")
        if not isinstance(spec, Mapping):
            raise ValueError(f"{source}: profile for '{task}' must be a mapping")
        raw_caps = spec.get("required_capabilities")
        if not isinstance(raw_caps, (list, tuple)) or not raw_caps:
            raise ValueError(f"{source}: '{task}' must list required_capabilities")
        capabilities = tuple(normalize_task(str(cap)) for cap in raw_caps)
        unknown = sorted(set(capabilities) - known_capabilities)
        if unknown:
            raise ValueError(f"{source}: '{task}' uses capabilities outside the vocabulary: {unknown}")
        profiles[task] = TaskProfile(
            task=task,
            required_capabilities=capabilities,
            description=str(spec.get("description", "")),
        )

    missing = sorted(known_tasks - set(profiles))
    if missing:
        raise ValueError(f"{source}: missing profiles for tasks: {missing}")
    return profiles


@lru_cache(maxsize=1)
def load_task_profiles() -> dict[str, TaskProfile]:
    """Load and validate the shipped profile file (cached, fails fast)."""
    data = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8"))
    return parse_profiles(data, source=PROFILES_PATH.name)


def get_task_profile(task: str) -> TaskProfile | None:
    """Profile for ``task`` or ``None`` when the task has no profile yet."""
    return load_task_profiles().get(normalize_task(task))


def clear_profile_cache() -> None:
    """Testing hook: drop the cached profiles."""
    load_task_profiles.cache_clear()
