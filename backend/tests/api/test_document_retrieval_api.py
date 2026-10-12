"""API tests for personal document retrieval (RD-05).

Covers: authenticated indexing, user-scoped
retrieval, validation, foreign-document 404s,
and personalized generation for authenticated
vs anonymous requests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.application.services.document_retrieval import (
    DocumentRetrievalService,
)
from app.infrastructure.knowledge.embeddings import EmbeddingService
from app.infrastructure.knowledge.semantic_store import (
    SemanticEmbeddingStore,
)
from app.main import app

client = TestClient(app)


@pytest.fixture
def fresh_retrieval(monkeypatch: pytest.MonkeyPatch) -> DocumentRetrievalService:
    """Isolate the documents route's retrieval service per test."""
    import app.api.routes.documents as documents_route

    fresh = DocumentRetrievalService(
        store=SemanticEmbeddingStore(),
        embeddings=EmbeddingService(),
    )
    monkeypatch.setattr(documents_route, "get_document_retrieval", lambda: fresh)
    return fresh


@pytest.fixture
def fresh_generation_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> DocumentRetrievalService:
    """Isolate the generation endpoints' retrieval service per test."""
    import app.main as main_module

    fresh = DocumentRetrievalService(
        store=SemanticEmbeddingStore(),
        embeddings=EmbeddingService(),
    )
    monkeypatch.setattr(main_module, "get_document_retrieval", lambda: fresh)
    return fresh


def _create_document(auth_headers, user_id: str, document_type: str, content: str):
    response = client.post(
        "/api/v1/documents",
        json={
            "title": f"{document_type} document",
            "document_type": document_type,
            "content": content,
        },
        headers=auth_headers(user_id),
    )
    assert response.status_code == 200
    return response.json()


class TestIndexEndpoint:
    def test_index_requires_authentication(self, fresh_retrieval):
        response = client.post("/api/v1/documents/some-id/index")
        assert response.status_code == 401

    def test_index_round_trip(self, fresh_retrieval, auth_headers):
        document = _create_document(
            auth_headers,
            "index-user",
            "cv",
            "Data scientist with Python and machine learning experience.",
        )

        response = client.post(
            f"/api/v1/documents/{document['id']}/index",
            headers=auth_headers("index-user"),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["document_id"] == document["id"]
        assert payload["document_type"] == "cv"
        assert payload["chunks"] >= 1

        retrieved = client.get(
            "/api/v1/documents/retrieve",
            params={"query": "data scientist python machine learning"},
            headers=auth_headers("index-user"),
        )
        assert retrieved.status_code == 200
        items = retrieved.json()["items"]
        assert items
        assert all(item["document_id"] == document["id"] for item in items)

    def test_index_rejects_non_indexable_document_type(self, fresh_retrieval, auth_headers):
        document = _create_document(
            auth_headers,
            "index-user",
            "other",
            "Not a retrievable document type.",
        )
        response = client.post(
            f"/api/v1/documents/{document['id']}/index",
            headers=auth_headers("index-user"),
        )
        assert response.status_code == 400

    def test_index_foreign_document_returns_404(self, fresh_retrieval, auth_headers):
        document = _create_document(
            auth_headers,
            "owner-user",
            "cv",
            "Someone else's cv content.",
        )
        response = client.post(
            f"/api/v1/documents/{document['id']}/index",
            headers=auth_headers("other-user"),
        )
        # 404 (not 403) to avoid leaking existence.
        assert response.status_code == 404


class TestRetrieveEndpoint:
    def test_retrieve_requires_authentication(self, fresh_retrieval):
        response = client.get(
            "/api/v1/documents/retrieve",
            params={"query": "python"},
        )
        assert response.status_code == 401

    def test_retrieve_requires_query(self, fresh_retrieval, auth_headers):
        response = client.get(
            "/api/v1/documents/retrieve",
            headers=auth_headers("retrieve-user"),
        )
        assert response.status_code == 422

    def test_retrieve_is_user_scoped(self, fresh_retrieval, auth_headers):
        document = _create_document(
            auth_headers,
            "owner-user",
            "cv",
            "Secret cv content about python data science.",
        )
        index_response = client.post(
            f"/api/v1/documents/{document['id']}/index",
            headers=auth_headers("owner-user"),
        )
        assert index_response.status_code == 200

        response = client.get(
            "/api/v1/documents/retrieve",
            params={"query": "python data science"},
            headers=auth_headers("other-user"),
        )
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_retrieve_returns_attributed_results(self, fresh_retrieval, auth_headers):
        document = _create_document(
            auth_headers,
            "retrieve-user",
            "cover_letter",
            "Cover letter for a data scientist role at a tech company.",
        )
        client.post(
            f"/api/v1/documents/{document['id']}/index",
            headers=auth_headers("retrieve-user"),
        )

        response = client.get(
            "/api/v1/documents/retrieve",
            params={"query": "data scientist cover letter"},
            headers=auth_headers("retrieve-user"),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] >= 1
        item = payload["items"][0]
        assert item["document_id"] == document["id"]
        assert item["document_type"] == "cover_letter"
        assert item["similarity"] >= 0.0


class TestPersonalizedGeneration:
    def test_generation_personalizes_for_authenticated_user(self, fresh_generation_retrieval, auth_headers):
        fresh_generation_retrieval.index_document(
            user_id="gen-user",
            document_type="cv",
            document_id="cv-personal",
            content="Data scientist with Python and machine learning experience.",
        )

        response = client.post(
            "/api/v1/documents/cv/generate",
            json={
                "name": "Candidate",
                "target_role": "Data Scientist",
                "summary": "Python machine learning data scientist",
            },
            headers=auth_headers("gen-user"),
        )

        assert response.status_code == 200
        content = response.json()["content"]
        assert "Relevant personal history" in content
        assert "cv-personal" in content

    def test_generation_anonymous_request_has_no_personal_history(
        self,
        fresh_generation_retrieval,
    ):
        response = client.post(
            "/api/v1/documents/cv/generate",
            json={
                "name": "Candidate",
                "target_role": "Data Scientist",
                "summary": "Looking for a data science role.",
            },
        )

        assert response.status_code == 200
        assert "Relevant personal history" not in response.json()["content"]

    def test_cover_letter_generation_personalizes(self, fresh_generation_retrieval, auth_headers):
        fresh_generation_retrieval.index_document(
            user_id="cl-user",
            document_type="cover_letter",
            document_id="cl-personal",
            content="Cover letter for a data scientist role at a tech company.",
        )

        response = client.post(
            "/api/v1/documents/cover-letter/generate",
            json={
                "name": "Candidate",
                "company": "Tech Company",
                "target_role": "Data Scientist",
                "summary": "Data scientist cover letter experience",
            },
            headers=auth_headers("cl-user"),
        )

        assert response.status_code == 200
        content = response.json()["content"]
        assert "Relevant personal history" in content
        assert "cl-personal" in content
