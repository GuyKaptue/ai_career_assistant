"""Knowledge domain models (RD-03).

The knowledge base is a vectorized repository of career guidance
(CV best practices, cover-letter guidelines, career advice, HR
recommendations, country-specific application rules). Entries are
domain-tagged so new knowledge domains can be added as data
without touching the generation prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Embedding dimension. Matches sentence-transformers/all-MiniLM-L6-v2
# (the remote provider model) so remote and deterministic fallback
# vectors are interchangeable.
EMBEDDING_DIMENSION = 384

# Canonical knowledge domains. New domains are added here and to the
# seed corpus; retrieval and the API accept any of these values.
KNOWLEDGE_DOMAINS: tuple[str, ...] = (
    "cv_best_practices",
    "cover_letter_guidelines",
    "career_advice",
    "hr_recommendations",
    "country_rules",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class KnowledgeEntry:
    """One retrievable knowledge snippet with its embedding."""

    id: str
    domain: str
    content: str
    source: str
    embedding: list[float] | None = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain,
            "content": self.content,
            "source": self.source,
            "embedding": self.embedding,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    def to_public_dict(self) -> dict:
        """Client-facing view: never exposes the raw embedding."""
        return {
            "id": self.id,
            "domain": self.domain,
            "content": self.content,
            "source": self.source,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }
