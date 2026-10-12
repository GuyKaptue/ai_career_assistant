"""In-process metrics registry (DYNAMIC_HF_PROMPT §28, MASTER §28).

Thread-safe counters, gauges and summaries with label support and a
JSON-ready :meth:`MetricsRegistry.snapshot` for tests and future export.
Values live in-process only — no external metrics backend is faked (§38).
Keys render as ``name`` or ``name{label="value"}`` (Prometheus-style).
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

LabelValue = str


def _format_key(name: str, labels: dict[str, Any]) -> str:
    if not labels:
        return name
    rendered = ",".join(f'{key}="{labels[key]}"' for key in sorted(labels))
    return f"{name}{{{rendered}}}"


class MetricsRegistry:
    """Process-wide metric storage; duplicate names accumulate safely."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._summaries: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0.0, "sum": 0.0, "max": 0.0})

    def inc(self, name: str, value: float = 1.0, **labels: Any) -> None:
        """Monotonic counter (requests, fallbacks, failures, ...)."""
        key = _format_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, **labels: Any) -> None:
        """Point-in-time value (health, circuit state, depths)."""
        key = _format_key(name, labels)
        with self._lock:
            self._gauges[key] = float(value)

    def observe(self, name: str, value: float, **labels: Any) -> None:
        """Distribution summary (latency, token counts): count/sum/max."""
        key = _format_key(name, labels)
        with self._lock:
            entry = self._summaries[key]
            entry["count"] += 1.0
            entry["sum"] += float(value)
            entry["max"] = max(entry["max"], float(value))

    def get_counter(self, name: str, **labels: Any) -> float:
        key = _format_key(name, labels)
        with self._lock:
            return self._counters.get(key, 0.0)

    def snapshot(self) -> dict[str, Any]:
        """JSON-ready copy of every metric (tests, health/debug endpoints)."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "summaries": {key: dict(value) for key, value in self._summaries.items()},
            }

    def reset(self) -> None:
        """Testing hook: drop all recorded metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._summaries.clear()


# Process-wide registry used by the AI router (§28 metric names).
METRICS = MetricsRegistry()
