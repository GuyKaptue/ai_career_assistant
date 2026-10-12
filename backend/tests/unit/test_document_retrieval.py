"""Unit tests for personal document retrieval (RD-05).

Covers: chunking, indexing with source attribution,
user-scoped retrieval, relevance thresholds, top_k
caps, bounded context, and the deterministic fallback
when retrieval fails.
"""

from __future__ import annotations

import pytest

from app.application.services.document_generation import (
    generate_cv_document,
)
from app.application.services.document_retrieval import (
    CHUNK_SIZE,
    DEFAULT_RETRIEVAL_MIN_SIMILARITY,
    MAX_RETRIEVAL_CONTEXT_CHARS,
    MAX_RETRIEVAL_TOP_K,
    DocumentRetrievalService,
    chunk_text,
)
from app.core.errors import ValidationError
from app.infrastructure.knowledge.embeddings import (
    EmbeddingService,
)
from app.infrastructure.knowledge.semantic_store import (
    SemanticEmbeddingStore,
)


@pytest.fixture
def retrieval() -> DocumentRetrievalService:
    """Fresh retrieval service per test."""
    return DocumentRetrievalService(
        store=SemanticEmbeddingStore(),
        embeddings=EmbeddingService(),
    )


class TestChunkText:
    def test_empty_text_returns_no_chunks(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_is_single_chunk(self):
        assert chunk_text("Short text.") == ["Short text."]

    def test_long_text_is_split_into_bounded_chunks(self):
        text = ". ".join(f"Sentence {i}." for i in range(100))
        chunks = chunk_text(text)
        assert len(chunks) > 1
        assert all(len(chunk) <= CHUNK_SIZE for chunk in chunks)

    def test_consecutive_chunks_overlap(self):
        text = "alpha " * 300
        chunks = chunk_text(text)
        assert len(chunks) > 1
        # The next chunk begins inside the previous
        # chunk's text (overlapping window).
        assert chunks[1][:20] in chunks[0]

    def test_chunks_prefer_sentence_boundaries(self):
        text = ". ".join(f"Sentence number {i} here." for i in range(100))
        chunks = chunk_text(text)
        for chunk in chunks[:-1]:
            assert chunk.rstrip().endswith(".")

    def test_chunks_preserve_all_content(self):
        sentences = [f"Sentence {i}." for i in range(100)]
        chunks = chunk_text(" ".join(sentences))
        joined = " ".join(chunks)
        for sentence in sentences:
            assert sentence in joined


class TestIndexDocument:
    def test_index_document_chunks_and_stores(self, retrieval):
        content = ". ".join(f"Achievement {i} in data science." for i in range(30))
        result = retrieval.index_document(
            user_id="user-1",
            document_type="cv",
            document_id="cv-1",
            content=content,
        )
        assert result["document_id"] == "cv-1"
        assert result["document_type"] == "cv"
        assert result["user_id"] == "user-1"
        assert result["chunks"] > 1

    def test_indexed_chunks_carry_source_attribution(self, retrieval):
        content = ". ".join(f"Chunk {i} content about data science." for i in range(30))
        retrieval.index_document(
            user_id="user-1",
            document_type="cv",
            document_id="cv-1",
            content=content,
        )
        results = retrieval.retrieve(
            user_id="user-1",
            query="chunk content data science",
            top_k=MAX_RETRIEVAL_TOP_K,
        )
        assert results
        for item in results:
            assert item["document_id"] == "cv-1"
            assert item["document_type"] == "cv"

    def test_index_document_rejects_invalid_type(self, retrieval):
        with pytest.raises(ValidationError):
            retrieval.index_document(
                user_id="user-1",
                document_type="invalid",
                document_id="doc-1",
                content="content",
            )

    def test_index_document_requires_user_id(self, retrieval):
        with pytest.raises(ValidationError):
            retrieval.index_document(
                user_id="",
                document_type="cv",
                document_id="doc-1",
                content="content",
            )

    def test_index_document_requires_document_id(self, retrieval):
        with pytest.raises(ValidationError):
            retrieval.index_document(
                user_id="user-1",
                document_type="cv",
                document_id="",
                content="content",
            )


class TestRetrieve:
    def test_retrieve_returns_relevant_chunks_with_attribution(self, retrieval):
        retrieval.index_document(
            user_id="user-1",
            document_type="cv",
            document_id="cv-1",
            content="Senior data scientist with Python and machine learning.",
        )
        results = retrieval.retrieve(
            user_id="user-1",
            query="data scientist Python machine learning",
        )
        assert results
        top = results[0]
        assert top["document_id"] == "cv-1"
        assert top["document_type"] == "cv"
        assert top["similarity"] >= DEFAULT_RETRIEVAL_MIN_SIMILARITY
        assert "data scientist" in top["content"].lower()

    def test_retrieve_is_user_scoped(self, retrieval):
        retrieval.index_document(
            user_id="user-b",
            document_type="cv",
            document_id="cv-b",
            content="Secret cv content about python data science.",
        )
        results = retrieval.retrieve(
            user_id="user-a",
            query="python data science",
        )
        # user-a must not see user-b's documents.
        assert results == []

    def test_retrieve_caps_top_k(self, retrieval):
        for i in range(MAX_RETRIEVAL_TOP_K + 2):
            retrieval.index_document(
                user_id="user-1",
                document_type="cv",
                document_id=f"cv-{i}",
                content=f"python data scientist experience number {i}",
            )
        results = retrieval.retrieve(
            user_id="user-1",
            query="python data scientist",
            top_k=999,
        )
        assert len(results) == MAX_RETRIEVAL_TOP_K

    def test_retrieve_filters_by_min_similarity(self, retrieval):
        retrieval.index_document(
            user_id="user-1",
            document_type="cv",
            document_id="cv-1",
            content="python data scientist with five years experience",
        )
        results = retrieval.retrieve(
            user_id="user-1",
            query="python data scientist",
            min_similarity=0.99,
        )
        # Similar but non-identical text cannot
        # reach 0.99: the safeguard filters it out.
        assert results == []

    def test_retrieve_requires_query(self, retrieval):
        with pytest.raises(ValidationError):
            retrieval.retrieve(user_id="user-1", query="   ")

    def test_retrieve_requires_user_id(self, retrieval):
        with pytest.raises(ValidationError):
            retrieval.retrieve(user_id="", query="python")


class TestRetrieveForGeneration:
    def test_context_includes_source_attribution(self, retrieval):
        retrieval.index_document(
            user_id="user-1",
            document_type="cv",
            document_id="cv-1",
            content="Team leadership experience leading engineers.",
        )
        result = retrieval.retrieve_for_generation(
            user_id="user-1",
            query="team leadership experience",
        )
        assert result["used_fallback"] is False
        assert "cv-1" in result["context"]
        assert result["sources"][0]["document_id"] == "cv-1"

    def test_context_is_bounded(self, retrieval):
        long_content = ". ".join(f"Detailed achievement number {i} with metrics." for i in range(200))
        retrieval.index_document(
            user_id="user-1",
            document_type="cv",
            document_id="cv-1",
            content=long_content,
        )
        result = retrieval.retrieve_for_generation(
            user_id="user-1",
            query="achievement metrics",
            top_k=MAX_RETRIEVAL_TOP_K,
        )
        # Overflow safeguard: history can never
        # flood the prompt.
        assert len(result["context"]) <= MAX_RETRIEVAL_CONTEXT_CHARS

    def test_anonymous_user_gets_fallback(self, retrieval):
        result = retrieval.retrieve_for_generation(
            user_id="",
            query="anything",
        )
        assert result == {"context": "", "sources": [], "used_fallback": True}

    def test_retrieval_failure_degrades_to_fallback(self, retrieval, monkeypatch):
        def failing_retrieve(**_kwargs):
            raise RuntimeError("embedding unavailable")

        monkeypatch.setattr(retrieval, "retrieve", failing_retrieve)
        result = retrieval.retrieve_for_generation(
            user_id="user-1",
            query="python",
        )
        assert result["used_fallback"] is True
        assert result["context"] == ""
        assert result["sources"] == []


class TestGenerationIntegration:
    def test_personal_context_is_appended_with_notice(self):
        document = {
            "name": "Candidate",
            "target_role": "Data Scientist",
            "summary": "Summary here.",
        }
        result = generate_cv_document(
            document,
            personal_context="- Led a team. [Document: cv-1 | cv | 0.90]",
        )
        assert "Relevant personal history" in result["content"]
        assert "Led a team" in result["content"]
        assert "cv-1" in result["content"]

    def test_personal_context_never_overrides_user_content(self):
        document = {
            "name": "Candidate Name",
            "target_role": "Data Scientist",
            "summary": "User's own summary.",
        }
        result = generate_cv_document(
            document,
            personal_context="- Conflicting history. [Document: cv-1 | cv | 0.90]",
        )
        # User's facts come first; personal history
        # is appended as reference-only.
        assert result["content"].index("User's own summary.") < result["content"].index("Conflicting history")

    def test_no_personal_context_leaves_content_unchanged(self):
        document = {"name": "Candidate", "target_role": "Role", "summary": "S."}
        with_context = generate_cv_document(document, personal_context="")
        without = generate_cv_document(document)
        assert with_context["content"] == without["content"]
