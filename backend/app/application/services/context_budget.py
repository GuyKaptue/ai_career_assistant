"""Bounded context assembly (shared retrieval safeguard).

Both the career knowledge base (RD-03) and personal
document retrieval (RD-05) inject retrieved material
into generation prompts under a hard character budget
so retrieved context can never overflow the prompt.
This module is the single implementation of that
safeguard.
"""

from __future__ import annotations

from typing import Any, Callable


def build_bounded_context(
    results: list[dict[str, Any]],
    budget: int,
    attribution: Callable[[dict[str, Any]], str],
) -> str:
    """Assemble retrieved results into a bounded context.

    Each result renders as ``- {content} {attribution}``.
    Results are appended in rank order until one would
    exceed the remaining budget (overflow safeguard), so
    the returned context never exceeds ``budget``
    characters.
    """
    lines: list[str] = []
    remaining = budget
    for item in results:
        line = f"- {item['content']} {attribution(item)}"
        if len(line) > remaining:
            break
        lines.append(line)
        remaining -= len(line) + 1
    return "\n".join(lines)
