"""Knowledge infrastructure package (RD-03)."""

from app.infrastructure.knowledge.embeddings import (
    EmbeddingService,
    cosine_similarity,
    deterministic_embedding,
)
from app.infrastructure.knowledge.knowledge_store import KnowledgeStore

__all__ = [
    "EmbeddingService",
    "KnowledgeStore",
    "cosine_similarity",
    "deterministic_embedding",
]
