"""Knowledge API routes (RD-03).

- ``GET  /api/v1/knowledge/search`` — public retrieval
  with source attribution and similarity scores.
- ``POST /api/v1/knowledge/ingest`` — authenticated
  ingestion of new knowledge entries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.schemas import COMMON_ERROR_RESPONSES
from app.application.services.knowledge_base import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_TOP_K,
    get_knowledge_base,
)
from app.core.errors import ValidationError
from app.core.security.dependencies import get_current_user
from app.domain.knowledge.schemas import (
    KnowledgeIngestPayload,
    KnowledgeSearchResultItem,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"], responses=COMMON_ERROR_RESPONSES)


@router.get("/search")
def search_knowledge(
    q: str = Query(min_length=1, max_length=500),
    domain: str | None = Query(default=None),
    top_k: int = Query(default=DEFAULT_TOP_K, ge=1, le=10),
    min_similarity: float = Query(default=DEFAULT_MIN_SIMILARITY, ge=0.0, le=1.0),
) -> dict:
    """Retrieve relevant career guidance with source attribution."""
    results = get_knowledge_base().search(
        query=q,
        top_k=top_k,
        domain=domain,
        min_similarity=min_similarity,
    )
    items = [KnowledgeSearchResultItem(**item) for item in results]
    return {"query": q, "used_fallback": False, "count": len(items), "items": [item.model_dump() for item in items]}


@router.post("/ingest")
def ingest_knowledge(
    body: KnowledgeIngestPayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Add a knowledge entry (authenticated)."""
    try:
        body.validate_domain()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    entry = get_knowledge_base().ingest(
        domain=body.domain,
        content=body.content,
        source=body.source,
        metadata=body.metadata,
    )
    return entry.to_dict()
