"""API tests for the knowledge endpoints (RD-03).

Covers public search with source attribution, query
validation, authenticated ingestion, and end-to-end
ingest → search round-trips.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.application.services.knowledge_base import KnowledgeBaseService
from app.infrastructure.knowledge.embeddings import EmbeddingService
from app.infrastructure.knowledge.knowledge_store import KnowledgeStore
from app.main import app

client = TestClient(app)


@pytest.fixture
def fresh_knowledge(monkeypatch: pytest.MonkeyPatch) -> KnowledgeBaseService:
    """Isolate the route's knowledge base per test."""
    import app.api.routes.knowledge as knowledge_route

    fresh = KnowledgeBaseService(
        store=KnowledgeStore(),
        embeddings=EmbeddingService(),
    )
    monkeypatch.setattr(knowledge_route, "get_knowledge_base", lambda: fresh)
    return fresh


def test_knowledge_search_returns_attributed_results(fresh_knowledge):
    response = client.get(
        "/api/v1/knowledge/search",
        params={"q": "quantify achievements with numbers"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "quantify achievements with numbers"
    assert payload["count"] >= 1
    item = payload["items"][0]
    assert item["source"]
    assert item["similarity"] >= 0.35
    assert item["domain"] in {
        "cv_best_practices",
        "cover_letter_guidelines",
        "career_advice",
        "hr_recommendations",
        "country_rules",
    }


def test_knowledge_search_requires_query(fresh_knowledge):
    response = client.get("/api/v1/knowledge/search")

    assert response.status_code == 422


def test_knowledge_search_filters_by_domain(fresh_knowledge):
    response = client.get(
        "/api/v1/knowledge/search",
        params={"q": "thank you note after interview", "domain": "career_advice"},
    )

    assert response.status_code == 200
    assert all(item["domain"] == "career_advice" for item in response.json()["items"])


def test_knowledge_ingest_requires_authentication(fresh_knowledge):
    response = client.post(
        "/api/v1/knowledge/ingest",
        json={"domain": "career_advice", "content": "New guidance."},
    )

    assert response.status_code == 401


def test_knowledge_ingest_creates_entry(fresh_knowledge, auth_headers):
    response = client.post(
        "/api/v1/knowledge/ingest",
        json={
            "domain": "career_advice",
            "content": "Practice answers to common behavioral questions aloud.",
            "source": "community-contribution",
        },
        headers=auth_headers("knowledge-user"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["domain"] == "career_advice"
    assert payload["source"] == "community-contribution"
    assert payload["id"]


def test_knowledge_ingest_rejects_unknown_domain(fresh_knowledge, auth_headers):
    response = client.post(
        "/api/v1/knowledge/ingest",
        json={"domain": "nonexistent", "content": "New guidance."},
        headers=auth_headers("knowledge-user"),
    )

    assert response.status_code == 400


def test_ingested_entry_is_searchable(fresh_knowledge, auth_headers):
    client.post(
        "/api/v1/knowledge/ingest",
        json={
            "domain": "hr_recommendations",
            "content": "Keep the CV summary under four lines for recruiter scans.",
            "source": "community-contribution",
        },
        headers=auth_headers("knowledge-user"),
    )

    response = client.get(
        "/api/v1/knowledge/search",
        params={"q": "CV summary under four lines recruiter scans"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["source"] == "community-contribution" for item in items)
