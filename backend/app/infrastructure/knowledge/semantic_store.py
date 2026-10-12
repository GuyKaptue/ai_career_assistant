"""Semantic embedding storage (RD-04).

Persists embeddings for user profiles, CVs, and job
descriptions in Supabase pgvector, with an in-memory
fallback (and fail-soft behaviour) matching the
knowledge store pattern.

The backend is selected at call time so tests can
force in-memory mode by patching settings.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.core.config import settings
from app.core.persistence import build_supabase_client
from app.infrastructure.knowledge.embeddings import cosine_similarity

logger = logging.getLogger(__name__)

# Entity types stored in the semantic embedding table.
ENTITY_PROFILE = "profile"
ENTITY_CV = "cv"
ENTITY_COVER_LETTER = "cover_letter"
ENTITY_RESUME_ANALYSIS = "resume_analysis"
ENTITY_JOB_DESCRIPTION = "job_description"

ENTITY_TYPES = (
    ENTITY_PROFILE,
    ENTITY_CV,
    ENTITY_COVER_LETTER,
    ENTITY_RESUME_ANALYSIS,
    ENTITY_JOB_DESCRIPTION,
)


class SemanticEmbeddingStore:
    """pgvector-backed embedding store with in-memory fallback."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], dict[str, Any]] = {}

    @property
    def _supabase_configured(self) -> bool:
        return bool(settings.supabase_url and settings.supabase_service_role_key)

    def _client(self) -> httpx.Client:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase is not configured.")
        return build_supabase_client(settings.supabase_url, settings.supabase_service_role_key)

    def save(
        self,
        entity_type: str,
        entity_id: str,
        content: str,
        embedding: list[float],
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Persist one embedding (write-through, fail-soft)."""
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of: {', '.join(ENTITY_TYPES)}")

        record: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "content": content,
            "embedding": embedding,
            "user_id": user_id,
            "metadata": metadata or {},
        }

        if self._supabase_configured:
            try:
                self._persist(record)
            except Exception as exc:  # noqa: BLE001 — fail-soft
                logger.warning("semantic.persist.failed: %s", exc)

        self._entries[(entity_type, entity_id)] = record
        return record

    def _persist(self, record: dict[str, Any]) -> None:
        with self._client() as client:
            response = client.post("/rest/v1/semantic_embeddings", json=record)
            if response.status_code >= 400:
                raise RuntimeError(f"semantic_embeddings write failed: {response.text}")

    def search(
        self,
        query_embedding: list[float],
        entity_type: str | None = None,
        user_id: str | None = None,
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[tuple[dict[str, Any], float]]:
        """Return ``(record, similarity)`` pairs, best first.

        User-scoped: when ``user_id`` is given, only that
        user's embeddings (and public ones) are searched.
        """
        if self._supabase_configured:
            try:
                return self._rpc_search(query_embedding, entity_type, user_id, top_k, min_similarity)
            except Exception as exc:  # noqa: BLE001 — fail-soft
                logger.warning("semantic.rpc_search.failed: %s", exc)
        return self._local_search(query_embedding, entity_type, user_id, top_k, min_similarity)

    def _rpc_search(
        self,
        query_embedding: list[float],
        entity_type: str | None,
        user_id: str | None,
        top_k: int,
        min_similarity: float,
    ) -> list[tuple[dict[str, Any], float]]:
        body: dict[str, Any] = {
            "query_embedding": query_embedding,
            "match_threshold": min_similarity,
            "match_count": top_k,
        }
        if entity_type:
            body["entity_type_filter"] = entity_type
        if user_id:
            body["user_filter"] = user_id
        with self._client() as client:
            response = client.post("/rest/v1/rpc/semantic_search", json=body)
            if response.status_code >= 400:
                raise RuntimeError(f"semantic_search rpc failed: {response.text}")
            rows = response.json()

        results: list[tuple[dict[str, Any], float]] = []
        for row in rows:
            record = {
                "id": row["id"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "content": row["content"],
                "user_id": row.get("user_id"),
                "metadata": row.get("metadata") or {},
            }
            results.append((record, float(row.get("similarity", 0.0))))
        return results

    def _local_search(
        self,
        query_embedding: list[float],
        entity_type: str | None,
        user_id: str | None,
        top_k: int,
        min_similarity: float,
    ) -> list[tuple[dict[str, Any], float]]:
        scored: list[tuple[dict[str, Any], float]] = []
        for (stored_type, _entity_id), record in self._entries.items():
            if entity_type and stored_type != entity_type:
                continue
            # User-scoped isolation: a user only sees their
            # own embeddings plus public (user_id=None) ones.
            record_user = record.get("user_id")
            if user_id and record_user is not None and record_user != user_id:
                continue
            embedding = record.get("embedding")
            if not embedding:
                continue
            similarity = cosine_similarity(query_embedding, embedding)
            if similarity >= min_similarity:
                public_record = {k: v for k, v in record.items() if k != "embedding"}
                scored.append((public_record, similarity))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def new_id(self) -> str:
        return str(uuid.uuid4())
