"""Unit tests for semantic job matching (RD-04).

Covers: semantic scoring, concept-level
explainability, combined ranking, the ATS
fallback, and the pgvector embedding store
with user-scoped isolation.
"""

from __future__ import annotations

import pytest

from app.application.services.ats_checker import (
    check_resume_against_job,
)
from app.application.services.semantic_matching import (
    WEIGHT_ATS_KEYWORD,
    WEIGHT_SEMANTIC,
    SemanticMatchingService,
    check_resume_semantic,
)
from app.infrastructure.knowledge.embeddings import (
    deterministic_embedding,
)
from app.infrastructure.knowledge.semantic_store import (
    SemanticEmbeddingStore,
)


@pytest.fixture
def matching() -> SemanticMatchingService:
    return SemanticMatchingService()


class TestSemanticMatch:
    def test_score_is_in_range(self, matching):
        result = matching.semantic_match("python data scientist", "python data scientist role")
        assert 0.0 <= result.semantic_score <= 100.0

    def test_similar_text_scores_higher(self, matching):
        similar = matching.semantic_match(
            "machine learning engineer python",
            "python machine learning engineer",
        )
        dissimilar = matching.semantic_match(
            "machine learning engineer python",
            "chef cooking gourmet food",
        )
        assert similar.semantic_score > dissimilar.semantic_score

    def test_extracts_matched_concepts_with_similarity(self, matching):
        result = matching.semantic_match(
            "python data analysis machine learning",
            "We need a python data analyst. " "Must know machine learning. Cooking optional.",
        )
        assert result.matched_concepts
        assert result.concept_details
        for detail in result.concept_details:
            assert detail["similarity"] >= 0.10
            assert detail["concept"]

    def test_empty_input_returns_zero_score(self, matching):
        result = matching.semantic_match("", "job description")
        assert result.semantic_score == 0.0
        assert result.matched_concepts == ()
        assert result.concept_details == []


class TestRankJobs:
    def test_ranks_by_combined_score(self, matching):
        jobs = [
            {
                "title": "Chef",
                "company": "Kitchen",
                "description": "cooking gourmet food",
            },
            {
                "title": "Data Scientist",
                "company": "Data Inc",
                "description": "python machine learning data analysis",
            },
        ]

        ranked = matching.rank_jobs("python data scientist machine learning", jobs)

        assert ranked[0]["title"] == "Data Scientist"
        assert ranked[0]["combined_score"] >= ranked[1]["combined_score"]

    def test_annotates_each_job_with_scores(self, matching):
        jobs = [{"title": "Data Scientist", "description": "python data"}]

        ranked = matching.rank_jobs("python data", jobs)

        assert "semantic_score" in ranked[0]
        assert "ats_keyword_score" in ranked[0]
        assert "combined_score" in ranked[0]
        assert "matched_concepts" in ranked[0]

    def test_empty_candidate_text_returns_unchanged(self, matching):
        jobs = [{"title": "Data Scientist"}]
        assert matching.rank_jobs("", jobs) == jobs


class TestCheckResumeSemantic:
    def test_combines_semantic_and_ats_scores(self):
        resume = "python data scientist machine learning"
        job = "python data scientist machine learning required"
        ats = check_resume_against_job(resume, job)

        result = check_resume_semantic(resume, job, ats_result=ats)

        assert result["semantic_score"] is not None
        assert result["ats_keyword_score"] >= 0
        assert result["semantic_fallback"] is False
        expected = WEIGHT_SEMANTIC * result["semantic_score"] + WEIGHT_ATS_KEYWORD * result["ats_keyword_score"]
        assert abs(result["combined_score"] - round(expected)) <= 1

    def test_preserves_existing_ats_fields(self):
        resume = "python data scientist"
        job = "python data scientist required"

        result = check_resume_semantic(resume, job)

        # The ATS pipeline result is the base: its
        # fields remain available alongside the
        # semantic additions.
        assert "semantic_score" in result
        assert "combined_score" in result
        ats = check_resume_against_job(resume, job)
        assert "score" in ats
        assert "matched_keywords" in ats

    def test_falls_back_to_ats_when_embedding_fails(self, monkeypatch):
        resume = "python data scientist"
        job = "python data scientist required"
        ats = check_resume_against_job(resume, job)

        def failing_match(*_args, **_kwargs):
            raise RuntimeError("embedding unavailable")

        monkeypatch.setattr(
            "app.application.services.semantic_matching." "SemanticMatchingService.semantic_match",
            failing_match,
        )

        result = check_resume_semantic(resume, job)

        assert result["semantic_fallback"] is True
        assert result["semantic_score"] is None
        assert result["combined_score"] == ats["score"]


class TestSemanticEmbeddingStore:
    def test_save_and_search_own_and_public(self):
        store = SemanticEmbeddingStore()
        store.save(
            "profile",
            "profile-1",
            "python data scientist",
            deterministic_embedding("python data scientist"),
            user_id="user-1",
        )
        store.save(
            "job_description",
            "job-1",
            "python data scientist",
            deterministic_embedding("python data scientist"),
        )

        results = store.search(
            deterministic_embedding("python data scientist"),
            user_id="user-1",
        )

        # Own profile + public job description.
        assert len(results) == 2

    def test_user_scoped_isolation(self):
        store = SemanticEmbeddingStore()
        store.save(
            "cv",
            "cv-user-b",
            "secret cv content",
            deterministic_embedding("secret cv content"),
            user_id="user-b",
        )

        results = store.search(
            deterministic_embedding("secret cv content"),
            user_id="user-a",
        )

        # user-a must not see user-b's CV embedding.
        assert results == []

    def test_rejects_invalid_entity_type(self):
        store = SemanticEmbeddingStore()
        with pytest.raises(ValueError):
            store.save(
                "invalid_type",
                "x",
                "content",
                deterministic_embedding("content"),
            )

    def test_search_filters_by_entity_type(self):
        store = SemanticEmbeddingStore()
        store.save(
            "profile",
            "profile-1",
            "python data",
            deterministic_embedding("python data"),
            user_id="user-1",
        )
        store.save(
            "cv",
            "cv-1",
            "python data",
            deterministic_embedding("python data"),
            user_id="user-1",
        )

        results = store.search(
            deterministic_embedding("python data"),
            entity_type="cv",
            user_id="user-1",
        )

        assert len(results) == 1
        assert results[0][0]["entity_type"] == "cv"
