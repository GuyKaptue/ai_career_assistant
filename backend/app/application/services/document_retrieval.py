"""Personal document retrieval — lightweight RAG (RD-05).

Chunks, embeds, and retrieves the user's own
documents (previous CVs, cover letters, resume
analyses) so generated content can reuse relevant
personal history.

Design (RD-05 acceptance criteria):

- User-scoped: embeddings carry ``user_id`` and
  retrieval only ever returns the requesting
  user's documents (RLS-enforced at the store).
- Bounded: retrieved context is capped by a
  character budget so history can never flood a
  prompt (context-overflow safeguard).
- Relevant: a minimum-similarity threshold keeps
  irrelevant historical documents out of prompts.
- Transparent: every retrieved chunk carries its
  source document id, type, and similarity.
- Deterministic fallback: if retrieval fails, the
  caller gets an empty context with
  ``used_fallback=True`` — generation proceeds
  without personal history.
"""

from __future__ import annotations

import logging

from app.application.services.context_budget import build_bounded_context
from app.core.errors import ValidationError
from app.infrastructure.knowledge.embeddings import EmbeddingService
from app.infrastructure.knowledge.semantic_store import (
    SemanticEmbeddingStore,
)

logger = logging.getLogger(__name__)

# Chunking configuration.
CHUNK_SIZE = 800  # characters per chunk
CHUNK_OVERLAP = 100  # characters shared between chunks

# Retrieval safeguards (RD-05).
MAX_RETRIEVAL_TOP_K = 10
DEFAULT_RETRIEVAL_TOP_K = 3
DEFAULT_RETRIEVAL_MIN_SIMILARITY = 0.20
MAX_RETRIEVAL_CONTEXT_CHARS = 3000

# Document types eligible for personal retrieval.
DOCUMENT_ENTITY_TYPES = ("cv", "cover_letter", "resume_analysis")


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks.

    Chunks prefer breaking at paragraph or sentence
    boundaries so each chunk is a coherent unit.
    """
    if not text or not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Break at the last paragraph/sentence
            # boundary inside the chunk window.
            for boundary in ("\n\n", ". ", "\n"):
                position = text.rfind(boundary, start, end)
                if position > start:
                    end = position + len(boundary)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


class DocumentRetrievalService:
    """Chunk, embed, and retrieve personal documents."""

    def __init__(
        self,
        store: SemanticEmbeddingStore | None = None,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        self.store = store or SemanticEmbeddingStore()
        self.embeddings = embeddings or EmbeddingService()

    def index_document(
        self,
        user_id: str,
        document_type: str,
        document_id: str,
        content: str,
    ) -> dict:
        """Chunk, embed, and store one user document.

        Each chunk is stored as a separate embedding
        with the source document id in its metadata,
        so retrieval is auditable back to the
        originating document.
        """
        if document_type not in DOCUMENT_ENTITY_TYPES:
            raise ValidationError(f"document_type must be one of: " f"{', '.join(DOCUMENT_ENTITY_TYPES)}")
        if not str(user_id).strip():
            raise ValidationError("user_id is required.")
        if not str(document_id).strip():
            raise ValidationError("document_id is required.")

        chunks = chunk_text(content)
        for index, chunk in enumerate(chunks):
            self.store.save(
                entity_type=document_type,
                entity_id=f"{document_id}:chunk-{index}",
                content=chunk,
                embedding=self.embeddings.embed_one(chunk),
                user_id=user_id,
                metadata={"document_id": document_id, "chunk_index": index},
            )

        return {
            "document_id": document_id,
            "document_type": document_type,
            "user_id": user_id,
            "chunks": len(chunks),
        }

    def retrieve(
        self,
        user_id: str,
        query: str,
        top_k: int = DEFAULT_RETRIEVAL_TOP_K,
        min_similarity: float = DEFAULT_RETRIEVAL_MIN_SIMILARITY,
    ) -> list[dict]:
        """Retrieve the user's most relevant document chunks.

        User-scoped: only the requesting user's
        embeddings are searched. Results carry the
        source document id, type, and similarity so
        retrieval is transparent and auditable.
        """
        if not str(user_id).strip():
            raise ValidationError("user_id is required.")
        if not query.strip():
            raise ValidationError("query must not be empty.")

        capped_top_k = max(1, min(int(top_k), MAX_RETRIEVAL_TOP_K))
        query_embedding = self.embeddings.embed_one(query)
        matches = self.store.search(
            query_embedding,
            user_id=user_id,
            top_k=capped_top_k,
            min_similarity=min_similarity,
        )

        results: list[dict] = []
        for record, similarity in matches:
            metadata = record.get("metadata") or {}
            results.append(
                {
                    "content": record["content"],
                    "document_id": metadata.get("document_id", record.get("entity_id", "")),
                    "document_type": record["entity_type"],
                    "similarity": round(similarity, 4),
                }
            )
        return results

    def retrieve_for_generation(
        self,
        user_id: str,
        query: str,
        top_k: int = DEFAULT_RETRIEVAL_TOP_K,
        min_similarity: float = DEFAULT_RETRIEVAL_MIN_SIMILARITY,
    ) -> dict:
        """Build bounded, auditable personal context.

        Returns ``{context, sources, used_fallback}``.
        The context is capped at
        ``MAX_RETRIEVAL_CONTEXT_CHARS`` (overflow
        safeguard) and every line carries its source
        document attribution. If retrieval fails, the
        caller gets an empty context with
        ``used_fallback=True`` (deterministic
        fallback — generation proceeds without
        personal history).
        """
        if not str(user_id).strip():
            return {"context": "", "sources": [], "used_fallback": True}

        try:
            results = self.retrieve(
                user_id=user_id,
                query=query,
                top_k=top_k,
                min_similarity=min_similarity,
            )
        except Exception as exc:  # noqa: BLE001 — fail-soft
            logger.warning("document.retrieval.failed: %s", exc)
            return {"context": "", "sources": [], "used_fallback": True}

        sources = [
            {
                "document_id": item["document_id"],
                "document_type": item["document_type"],
                "similarity": item["similarity"],
            }
            for item in results
        ]
        return {
            "context": build_bounded_context(
                results,
                MAX_RETRIEVAL_CONTEXT_CHARS,
                attribution=lambda item: (
                    f"[Document: {item['document_id']} | " f"{item['document_type']} | " f"{item['similarity']:.2f}]"
                ),
            ),
            "sources": sources,
            "used_fallback": False,
        }


_document_retrieval: DocumentRetrievalService | None = None


def get_document_retrieval() -> DocumentRetrievalService:
    """Lazy singleton (no work at import time)."""
    global _document_retrieval
    if _document_retrieval is None:
        _document_retrieval = DocumentRetrievalService()
    return _document_retrieval
