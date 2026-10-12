"""Unit tests for the shared bounded-context builder.

The context-overflow safeguard is shared by the
knowledge base (RD-03) and personal document
retrieval (RD-05); these tests pin its contract.
"""

from __future__ import annotations

from app.application.services.context_budget import (
    build_bounded_context,
)


def _attribution(item: dict) -> str:
    return f"[Source: {item['source']} | {item['similarity']:.2f}]"


def test_empty_results_render_empty_context():
    assert build_bounded_context([], 100, _attribution) == ""


def test_results_render_with_attribution():
    results = [
        {"content": "Quantify achievements.", "source": "cv.md", "similarity": 0.9},
    ]
    context = build_bounded_context(results, 1000, _attribution)
    assert context == "- Quantify achievements. [Source: cv.md | 0.90]"


def test_context_never_exceeds_budget():
    results = [{"content": f"Line {i} " + "x" * 50, "source": "s", "similarity": 0.9} for i in range(20)]
    context = build_bounded_context(results, 200, _attribution)
    assert len(context) <= 200


def test_budget_stops_at_first_overflowing_line():
    results = [
        {"content": "short", "source": "s", "similarity": 0.9},
        {"content": "y" * 500, "source": "s", "similarity": 0.9},
        {"content": "never included", "source": "s", "similarity": 0.9},
    ]
    context = build_bounded_context(results, 100, _attribution)
    assert "short" in context
    assert "never included" not in context


def test_results_are_joined_with_newlines():
    results = [
        {"content": "first", "source": "s", "similarity": 0.9},
        {"content": "second", "source": "s", "similarity": 0.9},
    ]
    context = build_bounded_context(results, 1000, _attribution)
    assert context.count("\n") == 1
    assert context.startswith("- first")
    assert "second" in context
