"""API tests for semantic matching (RD-04).

Covers the enhanced resume check (semantic +
combined scores, ATS fallback) and semantic
job re-ranking.
"""

from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FIXED_JOB_PAYLOAD = {
    "count": 2,
    "results": [
        {
            "title": "Chef",
            "company": "Kitchen Co",
            "location": "Remote",
            "description": "cooking gourmet food",
            "url": "https://example.com/chef",
            "provider": "fake",
            "provider_id": "chef-1",
        },
        {
            "title": "Data Scientist",
            "company": "Data Inc",
            "location": "Remote",
            "description": "python machine learning data analysis",
            "url": "https://example.com/ds",
            "provider": "fake",
            "provider_id": "ds-1",
        },
    ],
    "page": 1,
    "limit": 5,
    "total": 2,
    "audit": {},
}


def test_resume_check_includes_semantic_scores():
    response = client.post(
        "/api/v1/resume/check",
        json={
            "resume_text": "python data scientist machine learning",
            "job_description": "python data scientist machine learning required",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    # Existing ATS fields preserved...
    assert "score" in payload
    assert "matched_keywords" in payload
    assert "explanation" in payload
    # ...plus the RD-04 semantic additions.
    assert "semantic_score" in payload
    assert "ats_keyword_score" in payload
    assert "combined_score" in payload
    assert "matched_concepts" in payload
    assert payload["semantic_fallback"] is False


def test_resume_check_falls_back_to_ats(monkeypatch):
    def failing_match(*_args, **_kwargs):
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(
        "app.application.services.semantic_matching." "SemanticMatchingService.semantic_match",
        failing_match,
    )

    response = client.post(
        "/api/v1/resume/check",
        json={
            "resume_text": "python data scientist",
            "job_description": "python data scientist required",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["semantic_fallback"] is True
    assert payload["semantic_score"] is None
    # Combined score degrades to the ATS score.
    assert payload["combined_score"] == payload["score"]


def test_job_search_reranks_with_candidate_text(monkeypatch):
    monkeypatch.setattr(
        "app.main.search_jobs",
        lambda **_kwargs: deepcopy(FIXED_JOB_PAYLOAD),
    )

    response = client.get(
        "/api/v1/jobs/search",
        params={
            "query": "data",
            "candidate_text": "python data scientist machine learning",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ranked_by"] == "combined_semantic_ats"
    # The data role outranks the chef role for a
    # data-science candidate.
    assert payload["results"][0]["title"] == "Data Scientist"
    assert "combined_score" in payload["results"][0]
    assert "semantic_score" in payload["results"][0]
    assert "matched_concepts" in payload["results"][0]


def test_job_search_without_candidate_text_unchanged(monkeypatch):
    monkeypatch.setattr(
        "app.main.search_jobs",
        lambda **_kwargs: deepcopy(FIXED_JOB_PAYLOAD),
    )

    response = client.get(
        "/api/v1/jobs/search",
        params={"query": "data"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "ranked_by" not in payload
    assert "combined_score" not in payload["results"][0]
    # Original provider order preserved.
    assert payload["results"][0]["title"] == "Chef"
