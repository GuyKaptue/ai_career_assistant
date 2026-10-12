"""Pydantic schemas for the knowledge API (RD-03)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.knowledge.models import KNOWLEDGE_DOMAINS


class KnowledgeSearchPayload(BaseModel):
    """Query parameters for knowledge retrieval."""

    q: str = Field(min_length=1, max_length=500)
    domain: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)
    min_similarity: float = Field(default=0.35, ge=0.0, le=1.0)


class KnowledgeIngestPayload(BaseModel):
    """Body for adding a knowledge entry."""

    domain: str
    content: str = Field(min_length=1, max_length=4000)
    source: str = Field(default="community-contribution")
    metadata: dict = Field(default_factory=dict)

    def validate_domain(self) -> None:
        if self.domain not in KNOWLEDGE_DOMAINS:
            raise ValueError(f"domain must be one of: {', '.join(KNOWLEDGE_DOMAINS)}")


class KnowledgeSearchResultItem(BaseModel):
    """One retrieval result with source attribution."""

    id: str
    domain: str
    content: str
    source: str
    similarity: float
    metadata: dict = Field(default_factory=dict)


class KnowledgeSearchResponse(BaseModel):
    query: str
    used_fallback: bool = False
    count: int
    items: list[KnowledgeSearchResultItem]
