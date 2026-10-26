"""RAG enrichment (RD-08 §2, stage 2).

The validated candidate analysis supplies the retrieval keys (role archetype,
skill clusters, domain keywords, location signals). The user's own indexed
documents (CV history, templates, saved job descriptions, earlier generations)
are retrieved with those keys and returned as a bounded, sanitized *data* block.
Retrieved text is never an instruction: it is neutralized like any untrusted
input and wrapped in ``<retrieved>`` tags. Retrieval is fail-soft: on error the
caller gets an empty block and ``used_fallback=True``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final, Protocol

from app.application.services.candidate_analysis import CandidateAnalysis
from app.application.services.career_prompts import sanitize_untrusted, truncate_text
from app.core.errors import AppError
from app.domain.users.user_core import UserCore

logger = logging.getLogger(__name__)

MAX_QUERIES: Final = 4
MAX_CHUNKS: Final = 6
MAX_CONTEXT_CHARS: Final = 2400
MIN_SIMILARITY: Final = 0.25
ALLOWED_TYPES: Final = frozenset({"cv", "cover_letter", "resume_analysis", "template", "job_description"})


class Retriever(Protocol):
    """The slice of ``DocumentRetrievalService`` used here."""

    def retrieve(self, user_id: str, query: str, top_k: int = ..., min_similarity: float = ...) -> list[dict]: ...


@dataclass(frozen=True)
class RagContext:
    """Retrieved context block plus audit data (ids and scores only, never content)."""

    block: str
    sources: tuple[dict[str, Any], ...]
    used_fallback: bool
    queries_run: int


def build_retrieval_queries(core: UserCore, analysis: CandidateAnalysis) -> list[str]:
    """Retrieval keys from the analysis (and the user's stated targets), deduplicated."""
    candidates: list[str] = []
    title = core.target_titles[0] if core.target_titles else analysis.role_archetype
    if title:
        candidates.append(" ".join(filter(None, [title, " ".join(analysis.domain_keywords[:3])])))
    for cluster in analysis.skill_clusters[:3]:
        candidates.append(" ".join([cluster.name, *cluster.skills[:4]]))
    if analysis.skills:
        candidates.append(" ".join(analysis.skills[:8]))
    if analysis.location_signals or core.preferred_locations:
        place = (list(core.preferred_locations) + analysis.location_signals)[0]
        candidates.append(f"{title} {place}".strip())
    seen: dict[str, str] = {}
    for query in candidates:
        cleaned = " ".join(query.split())
        if cleaned:
            seen.setdefault(cleaned.casefold(), cleaned)
    return list(seen.values())[:MAX_QUERIES]


def enrich(core: UserCore, analysis: CandidateAnalysis, retriever: Retriever) -> RagContext:
    """Retrieve, merge by best similarity, sanitize and bound the context."""
    queries = build_retrieval_queries(core, analysis)
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for query in queries:
        try:
            rows = retriever.retrieve(core.user_id, query, top_k=MAX_CHUNKS, min_similarity=MIN_SIMILARITY)
        except (AppError, RuntimeError, ValueError, OSError):
            logger.info("rag.retrieval_failed")
            return RagContext("", (), True, len(queries))
        for row in rows:
            if row.get("document_type") not in ALLOWED_TYPES:
                continue
            key = (str(row.get("document_id", "")), str(row.get("content", ""))[:80])
            if key not in best or row["similarity"] > best[key]["similarity"]:
                best[key] = row
    ranked = sorted(best.values(), key=lambda r: r["similarity"], reverse=True)[:MAX_CHUNKS]
    lines: list[str] = []
    used = 0
    sources: list[dict[str, Any]] = []
    for row in ranked:
        text = sanitize_untrusted(str(row["content"])).strip()
        remaining = MAX_CONTEXT_CHARS - used
        if remaining <= 0:
            break
        text, _ = truncate_text(text, remaining)
        lines.append(f"[{row['document_type']}] {text}")
        used += len(text)
        sources.append(
            {
                "document_id": row.get("document_id"),
                "document_type": row["document_type"],
                "similarity": row["similarity"],
            }
        )
    block = "<retrieved>\n" + "\n".join(lines) + "\n</retrieved>" if lines else ""
    return RagContext(block, tuple(sources), False, len(queries))
