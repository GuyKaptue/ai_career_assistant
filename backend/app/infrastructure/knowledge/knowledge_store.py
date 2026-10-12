"""Knowledge storage (RD-03).

Two backends behind one interface:

1. Supabase pgvector: embeddings are written to the
   ``knowledge_entries`` table (``vector(384)`` column) and
   searched server-side via the ``knowledge_search`` RPC
   (cosine distance, threshold-filtered).
2. In-memory: cosine similarity computed locally. Used when
   Supabase is unconfigured, and as the deterministic
   fallback whenever the remote path fails.

Both paths return the same result shape so the application
layer never branches on the backend.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.core.config import settings
from app.core.persistence import build_supabase_client
from app.domain.knowledge.models import KnowledgeEntry
from app.infrastructure.knowledge.embeddings import cosine_similarity

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """pgvector-backed knowledge store with in-memory fallback.

    The backend is selected at call time (not at init) so
    tests can force in-memory mode by patching settings,
    matching the other service stores.
    """

    def __init__(self) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}

    @property
    def _supabase_configured(self) -> bool:
        return bool(settings.supabase_url and settings.supabase_service_role_key)

    # -- writes ---------------------------------------------------------

    def add(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        if self._supabase_configured:
            try:
                self._persist(entry)
            except Exception as exc:  # noqa: BLE001 — fail-soft to memory
                logger.warning("knowledge.persist.failed entry=%s: %s", entry.id, exc)
        self._entries[entry.id] = entry
        return entry

    def _client(self) -> httpx.Client:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase is not configured.")
        return build_supabase_client(settings.supabase_url, settings.supabase_service_role_key)

    def _persist(self, entry: KnowledgeEntry) -> None:
        payload: dict[str, Any] = {
            "id": entry.id,
            "domain": entry.domain,
            "content": entry.content,
            "source": entry.source,
            "metadata": entry.metadata,
        }
        if entry.embedding is not None:
            payload["embedding"] = entry.embedding
        with self._client() as client:
            response = client.post("/rest/v1/knowledge_entries", json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"knowledge_entries write failed: {response.text}")

    # -- reads ----------------------------------------------------------

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        domain: str | None = None,
        min_similarity: float = 0.0,
    ) -> list[tuple[KnowledgeEntry, float]]:
        """Return ``(entry, similarity)`` pairs, best first."""
        if self._supabase_configured:
            try:
                return self._rpc_search(query_embedding, top_k, domain, min_similarity)
            except Exception as exc:  # noqa: BLE001 — fail-soft to local
                logger.warning("knowledge.rpc_search.failed: %s", exc)
        return self._local_search(query_embedding, top_k, domain, min_similarity)

    def _rpc_search(
        self,
        query_embedding: list[float],
        top_k: int,
        domain: str | None,
        min_similarity: float,
    ) -> list[tuple[KnowledgeEntry, float]]:
        body: dict[str, Any] = {
            "query_embedding": query_embedding,
            "match_threshold": min_similarity,
            "match_count": top_k,
        }
        if domain:
            body["domain_filter"] = domain
        with self._client() as client:
            response = client.post("/rest/v1/rpc/knowledge_search", json=body)
            if response.status_code >= 400:
                raise RuntimeError(f"knowledge_search rpc failed: {response.text}")
            rows = response.json()

        results: list[tuple[KnowledgeEntry, float]] = []
        for row in rows:
            entry = KnowledgeEntry(
                id=str(row["id"]),
                domain=row["domain"],
                content=row["content"],
                source=row["source"],
                metadata=row.get("metadata") or {},
                created_at=row.get("created_at", ""),
            )
            results.append((entry, float(row.get("similarity", 0.0))))
        return results

    def _local_search(
        self,
        query_embedding: list[float],
        top_k: int,
        domain: str | None,
        min_similarity: float,
    ) -> list[tuple[KnowledgeEntry, float]]:
        scored: list[tuple[KnowledgeEntry, float]] = []
        for entry in self._entries.values():
            if domain and entry.domain != domain:
                continue
            if entry.embedding is None:
                continue
            similarity = cosine_similarity(query_embedding, entry.embedding)
            if similarity >= min_similarity:
                scored.append((entry, similarity))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def all_entries(self) -> list[KnowledgeEntry]:
        return list(self._entries.values())

    def is_empty(self) -> bool:
        return not self._entries

    def new_id(self) -> str:
        return str(uuid.uuid4())
