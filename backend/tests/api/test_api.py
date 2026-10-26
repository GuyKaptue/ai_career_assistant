from pathlib import Path

from fastapi.testclient import TestClient

from app.domain.jobs.service import search_jobs
from app.main import app

client = TestClient(app)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
EN_CV = FIXTURES / "synthetic_cv_en.pdf"
DE_CV = FIXTURES / "synthetic_cv_de.pdf"


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_template_listing_endpoint():
    response = client.get("/api/v1/templates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert any(item["id"] == "professional" for item in payload["items"])


def test_profile_creation_endpoint(auth_headers):
    response = client.post(
        "/api/v1/profiles",
        json={
            "user_id": "user-profile-1",
            "email": "user@example.com",
            "full_name": "Jane Learner",
            "target_role": "Product Analyst",
        },
        headers=auth_headers("user-profile-1"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "user-profile-1@example.test"
    assert payload["target_role"] == "Product Analyst"


def test_application_tracking_endpoint(auth_headers):
    response = client.post(
        "/api/v1/applications",
        json={
            "user_id": "user-profile-1",
            "company": "Example Corp",
            "position": "Data Analyst",
            "status": "applied",
        },
        headers=auth_headers("user-profile-1"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"] == "Example Corp"
    assert payload["status"] == "applied"


def test_resume_check_endpoint():
    resume_text = (
        "Summary\nExperienced data analyst with Python and SQL skills.\n\n"
        "Experience\nBuilt analytics dashboards and reporting tools.\n\n"
        "Skills\nPython, SQL, analytics, dashboard, reporting"
    )
    job_description = "Python SQL analytics data analyst dashboard reporting"
    response = client.post(
        "/api/v1/resume/check",
        json={
            "resume_text": resume_text,
            "job_description": job_description,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["score"] >= 70
    assert "python" in payload["matched_keywords"]
    assert "formatting_score" in payload
    assert "readability_score" in payload
    assert "explanation" in payload


def test_job_search_endpoint_rejects_blank_query():
    response = client.get("/api/v1/jobs/search", params={"query": "   "})

    assert response.status_code == 400
    assert "A search query is required" in response.json()["detail"]


def test_job_search_endpoint_requires_provider_configuration():
    response = client.get("/api/v1/jobs/search", params={"query": "data analyst"})

    assert response.status_code == 503
    assert "No job provider has been configured" in response.json()["detail"]


def test_search_jobs_uses_configured_provider(monkeypatch):
    class FakeProvider:
        name = "fake-provider"

        def search(self, query, location=None, limit=5):
            return [
                {
                    "title": "Senior Data Analyst",
                    "company": "Northwind Labs",
                    "location": "Remote",
                    "description": "Own SQL and dashboard reporting.",
                    "url": "https://example.com/jobs/1",
                    "source": "fake-provider",
                    "provider_id": "job-1",
                    "published_at": "2026-10-01T00:00:00Z",
                }
            ]

    monkeypatch.setenv("JOB_PROVIDER", "fake-provider")
    monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [FakeProvider()])

    result = search_jobs("data analyst", location="Remote", limit=5)

    assert result["count"] == 1
    assert result["results"][0]["title"] == "Senior Data Analyst"
    assert result["results"][0]["company"] == "Northwind Labs"
    assert result["results"][0]["location"] == "Remote"
    assert result["audit"]["providers_succeeded"] == 1
    assert result["audit"]["cached"] is False


def test_resignation_letter_generation_endpoint():
    response = client.post(
        "/api/v1/documents/resignation/generate",
        json={
            "name": "Jane Learner",
            "company": "Northwind Labs",
            "role": "Data Analyst",
            "last_working_day": "2026-12-31",
            "notice_period": "30 days",
            "reason": "pursuing a new opportunity",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_type"] == "resignation"
    assert "Jane Learner" in payload["content"]
    assert "Northwind Labs" in payload["content"]


def test_resignation_tone_selector_produces_distinct_letters():
    base_payload = {
        "name": "Jane Learner",
        "company": "Northwind Labs",
        "role": "Data Analyst",
        "last_working_day": "2026-12-31",
        "notice_period": "30 days",
        "reason": "pursuing a new opportunity",
    }

    formal = client.post("/api/v1/documents/resignation/generate", json={**base_payload, "tone": "formal"}).json()
    warm = client.post("/api/v1/documents/resignation/generate", json={**base_payload, "tone": "warm"}).json()
    brief = client.post("/api/v1/documents/resignation/generate", json={**base_payload, "tone": "brief"}).json()

    # Each tone renders a different letter; brief is the most concise.
    assert formal["content"] != warm["content"]
    assert formal["content"] != brief["content"]
    assert len(brief["content"]) < len(warm["content"]) < len(formal["content"])

    # Every tone keeps the same facts (no fabrication, PROJ §5.4).
    for payload in (formal, warm, brief):
        assert payload["document_type"] == "resignation"
        assert payload["metadata"]["tone"] in ("formal", "warm", "brief")
        assert "Jane Learner" in payload["content"]
        assert "Northwind Labs" in payload["content"]
        assert "2026-12-31" in payload["content"]
        assert "30 days" in payload["content"]

    # Tone is omitted → formal default.
    default = client.post("/api/v1/documents/resignation/generate", json=base_payload).json()
    assert default["metadata"]["tone"] == "formal"
    assert default["content"] == formal["content"]


def test_resignation_rejects_unknown_tone():
    response = client.post(
        "/api/v1/documents/resignation/generate",
        json={"name": "Jane", "company": "ACME", "tone": "sarcastic"},
    )
    assert response.status_code == 400
    assert "tone" in response.json()["detail"]


def test_cv_generate_defaults_to_offline_template():
    response = client.post(
        "/api/v1/documents/cv/generate",
        json={"name": "Jane Learner", "target_role": "Data Analyst", "summary": "SQL dashboards"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_generated"] is False
    assert payload["review_before_sending"] is False
    assert "Jane Learner" in payload["content"]


def test_cv_generate_ai_failure_falls_back_to_template(monkeypatch):
    from app import main as main_module

    class FailingAdapter:
        def generate_with_fallback(self, **kwargs):
            raise RuntimeError("MODEL_UNAVAILABLE: down")

    monkeypatch.setattr(main_module, "get_adapter", lambda: FailingAdapter())
    response = client.post(
        "/api/v1/documents/cv/generate",
        json={"name": "Jane", "target_role": "Analyst", "use_ai": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_generated"] is False
    assert payload["fallback_reason"] is not None


def test_cv_generate_ai_success_carries_review_notice(monkeypatch):
    from app import main as main_module

    class OkAdapter:
        def generate_with_fallback(self, **kwargs):
            return {
                "model_id": "test/model",
                "content": "AI CV body",
                "fallback_reason": None,
                "fallback_chain": [],
                "routing_score": 1.0,
                "required_context": 1024,
            }

    monkeypatch.setattr(main_module, "get_adapter", lambda: OkAdapter())
    response = client.post(
        "/api/v1/documents/cv/generate",
        json={"name": "Jane", "target_role": "Analyst", "use_ai": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_generated"] is True
    assert payload["model_id"] == "test/model"
    assert payload["review_before_sending"] is True
    assert "review before sending" in payload["content"]


def test_delete_document_removes_owned_document(auth_headers):
    created = client.post(
        "/api/v1/documents",
        json={"title": "Draft", "document_type": "cv", "content": "Hello"},
        headers=auth_headers("user-delete-1"),
    ).json()
    document_id = created["id"]

    response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=auth_headers("user-delete-1"),
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "document_id": document_id}

    # Gone after delete.
    assert (
        client.get(
            f"/api/v1/documents/{document_id}",
            headers=auth_headers("user-delete-1"),
        ).status_code
        == 404
    )


def test_delete_document_foreign_returns_404(auth_headers):
    created = client.post(
        "/api/v1/documents",
        json={"title": "Draft", "document_type": "cv", "content": "Hello"},
        headers=auth_headers("user-delete-2"),
    ).json()

    response = client.delete(
        f"/api/v1/documents/{created['id']}",
        headers=auth_headers("user-delete-1"),
    )

    assert response.status_code == 404


def test_delete_application_removes_owned_application(auth_headers):
    created = client.post(
        "/api/v1/applications",
        json={"user_id": "user-delete-3", "company": "ACME", "position": "Analyst"},
        headers=auth_headers("user-delete-3"),
    ).json()
    application_id = created["application_id"]

    response = client.delete(
        f"/api/v1/applications/{application_id}",
        headers=auth_headers("user-delete-3"),
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "application_id": application_id}

    assert (
        client.get(
            "/api/v1/applications",
            headers=auth_headers("user-delete-3"),
        ).json()["count"]
        == 0
    )


def test_delete_application_foreign_returns_404(auth_headers):
    created = client.post(
        "/api/v1/applications",
        json={"user_id": "user-delete-4", "company": "ACME", "position": "Analyst"},
        headers=auth_headers("user-delete-4"),
    ).json()

    response = client.delete(
        f"/api/v1/applications/{created['application_id']}",
        headers=auth_headers("user-delete-1"),
    )

    assert response.status_code == 404


def test_delete_my_data_removes_profile_documents_and_applications(auth_headers):
    user_id = "user-delete-all"
    client.post(
        "/api/v1/profiles",
        json={"user_id": user_id, "email": "delete-all@example.test", "full_name": "Delete All"},
        headers=auth_headers(user_id),
    )
    client.post(
        "/api/v1/documents",
        json={"title": "Doc", "document_type": "cv", "content": "x"},
        headers=auth_headers(user_id),
    )
    client.post(
        "/api/v1/applications",
        json={"user_id": user_id, "company": "ACME", "position": "Analyst"},
        headers=auth_headers(user_id),
    )

    response = client.delete("/api/v1/profiles/me", headers=auth_headers(user_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted"] is True
    assert payload["user_id"] == user_id
    assert payload["deleted_documents"] >= 1
    assert payload["deleted_applications"] >= 1

    assert (
        client.get(
            f"/api/v1/profiles/{user_id}",
            headers=auth_headers(user_id),
        ).status_code
        == 404
    )


def test_template_preview_renders_sample_cv():
    response = client.post(
        "/api/v1/templates/preview",
        json={"template_id": "professional", "document_type": "cv", "locale": "en"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["template_id"] == "professional"
    assert payload["document_type"] == "cv"
    assert payload["ai_generated"] is False
    assert payload["review_before_sending"] is False
    assert "Sample Candidate" in payload["content"]


def test_template_preview_renders_cover_letter_and_resignation():
    letter = client.post(
        "/api/v1/templates/preview",
        json={"template_id": "classic-letter", "document_type": "cover_letter", "locale": "en"},
    ).json()
    assert letter["document_type"] == "cover_letter"
    assert "Sample Company" in letter["content"]

    resignation = client.post(
        "/api/v1/templates/preview",
        json={"template_id": "formal-resignation", "document_type": "resignation", "locale": "en"},
    ).json()
    assert resignation["document_type"] == "resignation"
    assert "Sample Company" in resignation["content"]


def test_template_preview_rejects_unknown_template():
    response = client.post(
        "/api/v1/templates/preview",
        json={"template_id": "does-not-exist", "document_type": "cv", "locale": "en"},
    )

    assert response.status_code == 400
    assert "does-not-exist" in response.json()["detail"]


def test_template_preview_rejects_unsupported_locale():
    response = client.post(
        "/api/v1/templates/preview",
        json={"template_id": "professional", "document_type": "cv", "locale": "xx"},
    )

    assert response.status_code == 400
    assert "xx" in response.json()["detail"]


class TestResumeExtractUpload:
    """POST /api/v1/resume/extract with the two real CVs.

    Manual equivalent: open ATS review or job search in the UI, click the
    CV-upload button, choose either repo-root PDF. Server logs
    (`cv_pdf_extractor` + `resume extract …` lines) show filename, bytes,
    pages, and chars; failures explain themselves in `detail`.
    """

    def test_extract_english_cv(self):
        with EN_CV.open("rb") as handle:
            response = client.post(
                "/api/v1/resume/extract",
                files={"file": ("synthetic_cv_en.pdf", handle, "application/pdf")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["filename"] == "synthetic_cv_en.pdf"
        assert payload["pages"] >= 1
        assert payload["chars"] > 3000
        assert "Sample Candidate" in payload["text"]
        assert "Python" in payload["text"]

    def test_extract_german_cv(self):
        with DE_CV.open("rb") as handle:
            response = client.post(
                "/api/v1/resume/extract",
                files={"file": ("synthetic_cv_de.pdf", handle, "application/pdf")},
            )

        assert response.status_code == 200
        payload = response.json()
        assert "Sample Candidate" in payload["text"]
        assert "Zusammenfassung" in payload["text"]

    def test_extract_feeds_resume_check(self):
        """Upload → extracted text → resume/check returns a 0–100 score."""
        with EN_CV.open("rb") as handle:
            extracted = client.post(
                "/api/v1/resume/extract",
                files={"file": ("synthetic_cv_en.pdf", handle, "application/pdf")},
            ).json()

        check = client.post(
            "/api/v1/resume/check",
            json={
                "resume_text": extracted["text"],
                "job_description": "Data Scientist with Python, SQL, machine learning, ETL pipelines",
            },
        )
        assert check.status_code == 200
        assert 0 <= check.json()["score"] <= 100

    def test_rejects_non_pdf_filename(self):
        response = client.post(
            "/api/v1/resume/extract",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )

        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]

    def test_rejects_unreadable_bytes(self):
        response = client.post(
            "/api/v1/resume/extract",
            files={"file": ("broken.pdf", b"not a pdf at all", "application/pdf")},
        )

        assert response.status_code == 400
