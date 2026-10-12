"""Unit tests for the knowledge base (RD-03).

Covers: deterministic embeddings, seed corpus coverage,
retrieval relevance with source attribution, safeguard
thresholds and budget caps, validation, extensibility,
and the deterministic fallback when retrieval fails.
"""

from __future__ import annotations

import math

import pytest

from app.application.services.document_generation import (
    generate_cv_document,
)
from app.application.services.knowledge_base import (
    DEFAULT_MIN_SIMILARITY,
    MAX_CONTEXT_CHARS,
    MAX_TOP_K,
    SEED_CORPUS,
    KnowledgeBaseService,
)
from app.core.errors import ValidationError
from app.domain.knowledge.models import KNOWLEDGE_DOMAINS
from app.infrastructure.knowledge.embeddings import (
    EmbeddingService,
    cosine_similarity,
    deterministic_embedding,
)
from app.infrastructure.knowledge.knowledge_store import KnowledgeStore


@pytest.fixture
def knowledge() -> KnowledgeBaseService:
    """Fresh, seeded knowledge base per test."""
    return KnowledgeBaseService(
        store=KnowledgeStore(),
        embeddings=EmbeddingService(),
    )


class TestDeterministicEmbeddings:
    def test_embedding_is_deterministic(self):
        first = deterministic_embedding("quantify achievements")
        second = deterministic_embedding("quantify achievements")
        assert first == second

    def test_embedding_is_l2_normalized(self):
        vector = deterministic_embedding("Data Scientist with Python and machine learning")
        norm = math.sqrt(sum(value * value for value in vector))
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_embedding_has_expected_dimension(self):
        vector = deterministic_embedding("test")
        assert len(vector) == 384

    def test_similar_texts_score_higher_than_dissimilar(self):
        query = deterministic_embedding("quantify achievements with numbers")
        similar = deterministic_embedding("Quantify achievements with numbers instead of vague responsibilities.")
        dissimilar = deterministic_embedding("Follow up within 24 hours with a thank-you note.")
        assert cosine_similarity(query, similar) > cosine_similarity(query, dissimilar)

    def test_embedding_service_falls_back_without_token(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
        service = EmbeddingService()
        vector = service.embed_one("offline embedding")
        assert len(vector) == 384
        assert vector == deterministic_embedding("offline embedding")


class TestSeedCorpus:
    def test_seed_corpus_covers_all_domains(self, knowledge):
        seeded_domains = {entry.domain for entry in knowledge.store.all_entries()}
        assert seeded_domains == set(KNOWLEDGE_DOMAINS)

    def test_seed_corpus_has_source_attribution(self, knowledge):
        for entry in knowledge.store.all_entries():
            assert entry.source

    def test_seed_corpus_entries_have_embeddings(self, knowledge):
        for entry in knowledge.store.all_entries():
            assert entry.embedding is not None
            assert len(entry.embedding) == 384


class TestRetrieval:
    def test_search_returns_relevant_result_with_attribution(self, knowledge):
        results = knowledge.search(query="quantify achievements with numbers")

        assert results
        top = results[0]
        assert "quantify" in top["content"].lower()
        assert top["source"]
        assert top["similarity"] >= DEFAULT_MIN_SIMILARITY
        assert top["domain"] == "cv_best_practices"

    def test_search_relevance_threshold_filters_irrelevant(self, knowledge):
        results = knowledge.search(
            query="quantify achievements",
            min_similarity=0.9,
        )
        # A short query cannot reach 0.9 similarity against
        # longer entries: the safeguard filters everything.
        assert results == []

    def test_search_domain_filter_restricts_results(self, knowledge):
        results = knowledge.search(
            query="thank you note after interview",
            domain="career_advice",
        )
        assert results
        assert all(item["domain"] == "career_advice" for item in results)

    def test_search_caps_top_k(self, knowledge):
        results = knowledge.search(
            query="career job cv letter interview resume",
            top_k=999,
        )
        assert len(results) <= MAX_TOP_K

    def test_search_rejects_empty_query(self, knowledge):
        with pytest.raises(ValidationError):
            knowledge.search(query="   ")

    def test_search_rejects_unknown_domain(self, knowledge):
        with pytest.raises(ValidationError):
            knowledge.search(query="career", domain="nonexistent_domain")

    def test_ingest_rejects_unknown_domain(self, knowledge):
        with pytest.raises(ValidationError):
            knowledge.ingest(domain="nonexistent", content="some guidance")

    def test_ingest_rejects_empty_content(self, knowledge):
        with pytest.raises(ValidationError):
            knowledge.ingest(domain="career_advice", content="   ")


class TestGenerationContext:
    def test_retrieve_for_generation_returns_attributed_context(self, knowledge):
        retrieval = knowledge.retrieve_for_generation(query="quantify achievements with numbers")

        assert retrieval["context"]
        assert "[Source:" in retrieval["context"]
        assert retrieval["sources"]
        assert retrieval["sources"][0]["source"]
        assert retrieval["used_fallback"] is False

    def test_retrieved_context_is_budget_capped(self, knowledge):
        retrieval = knowledge.retrieve_for_generation(
            query="career job cv letter interview resume guidance",
            top_k=MAX_TOP_K,
        )
        assert len(retrieval["context"]) <= MAX_CONTEXT_CHARS

    def test_retrieval_failure_falls_back_deterministically(self, knowledge):
        def failing_search(*_args, **_kwargs):
            raise RuntimeError("store unavailable")

        knowledge.store.search = failing_search  # type: ignore[method-assign]

        retrieval = knowledge.retrieve_for_generation(query="anything")

        assert retrieval["context"] == ""
        assert retrieval["sources"] == []
        assert retrieval["used_fallback"] is True

    def test_generated_cv_appends_guidance_after_user_facts(self, knowledge):
        retrieval = knowledge.retrieve_for_generation(query="quantify achievements with numbers")
        document = {
            "name": "Jane Candidate",
            "target_role": "Data Analyst",
            "summary": "Five years of analytics experience.",
        }

        result = generate_cv_document(
            document,
            template_id="professional",
            knowledge_context=retrieval["context"],
        )

        content = result["content"]
        # User-provided facts come first...
        assert content.index("Jane Candidate") < content.index("Data Analyst")
        # ...and the reference-only notice precedes the guidance.
        notice = "Career guidance (reference only"
        assert notice in content
        assert content.index("Jane Candidate") < content.index(notice)
        assert "[Source:" in content

    def test_generated_cv_without_context_has_no_guidance(self):
        result = generate_cv_document(
            {"name": "Jane", "target_role": "Analyst"},
            template_id="professional",
        )
        assert "Career guidance" not in result["content"]


class TestExtensibility:
    def test_new_domain_entries_are_retrievable_without_code_changes(self, knowledge):
        # Ingest into an existing domain with a new source —
        # no prompt or service code changes required.
        knowledge.ingest(
            domain="cv_best_practices",
            content="Use a dedicated skills section for ATS keyword matching.",
            source="community-contribution",
        )

        results = knowledge.search(query="skills section ATS keyword matching")

        assert results
        assert any(item["source"] == "community-contribution" for item in results)

    def test_seed_corpus_is_idempotent(self):
        first = KnowledgeBaseService(store=KnowledgeStore(), embeddings=EmbeddingService())
        second = KnowledgeBaseService(store=KnowledgeStore(), embeddings=EmbeddingService())
        assert len(first.store.all_entries()) == len(second.store.all_entries())
        assert len(first.store.all_entries()) == len(SEED_CORPUS)
