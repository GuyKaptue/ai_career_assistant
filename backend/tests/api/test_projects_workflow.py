"""End-to-end project workflow over HTTP: position → match → apply → tracker → job search."""

import io
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.application.services import position_extraction as px
from app.core.errors import ConfigurationError
from app.domain.jobs.models import Job
from app.domain.jobs.providers import ProviderSearchResult
from app.domain.jobs.service import clear_job_cache
from app.main import app

client = TestClient(app)

AD = """Senior Python Developer (m/w/d)
Company: Acme GmbH
Location: Berlin

We are looking for an experienced Python developer to build FastAPI services on PostgreSQL.
Requirements: Python, FastAPI, PostgreSQL, Docker and strong communication skills.
"""

CANDIDATE = {
    "name": "Ada Müller",
    "summary": "Backend engineer with eight years of experience.",
    "skills": ["Photoshop", "Docker", "Python", "Public speaking", "FastAPI"],
    "experience": [
        {
            "role": "Backend Engineer",
            "company": "Initech",
            "highlights": ["Organised team lunches", "Built FastAPI services in Python", "Wrote documentation"],
        }
    ],
    "education": [{"degree": "BSc Computer Science", "school": "TU Berlin"}],
}


@pytest.fixture(autouse=True)
def _fresh_job_cache():
    clear_job_cache()
    yield
    clear_job_cache()


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _project_with_position(headers, **extra):
    created = client.post("/api/v1/projects", json={"name": "Acme application", **extra}, headers=headers)
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]
    attached = client.post(f"/api/v1/projects/{project_id}/position", json={"text": AD}, headers=headers)
    assert attached.status_code == 200, attached.text
    return project_id


class TestProjectCrud:
    def test_requires_authentication(self):
        assert client.get("/api/v1/projects").status_code == 401
        assert client.post("/api/v1/projects", json={"name": "x"}).status_code == 401

    def test_create_list_get_update_delete(self, auth_headers):
        headers = auth_headers("alice")
        created = client.post("/api/v1/projects", json={"name": "  My   plan "}, headers=headers).json()
        assert created["name"] == "My plan"
        assert (created["status"], created["template_id"], created["cover_letter_template_id"]) == (
            "draft",
            "professional",
            "classic-letter",
        )
        listed = client.get("/api/v1/projects", headers=headers).json()
        assert listed["count"] == 1
        assert client.get(f"/api/v1/projects/{created['id']}", headers=headers).json()["id"] == created["id"]
        patched = client.patch(
            f"/api/v1/projects/{created['id']}",
            json={"name": "Renamed", "template_id": "modern", "status": "archived"},
            headers=headers,
        )
        assert patched.status_code == 200
        assert (patched.json()["name"], patched.json()["template_id"], patched.json()["status"]) == (
            "Renamed",
            "modern",
            "archived",
        )
        assert client.delete(f"/api/v1/projects/{created['id']}", headers=headers).json()["deleted"] is True
        assert client.get(f"/api/v1/projects/{created['id']}", headers=headers).status_code == 404

    @pytest.mark.parametrize(
        "body",
        [
            {"name": "x", "template_id": "does-not-exist"},
            {"name": "x", "cover_letter_template_id": "professional"},  # a CV template, not a letter template
            {"name": "x" * 121},
        ],
    )
    def test_invalid_create_is_a_400(self, auth_headers, body):
        response = client.post("/api/v1/projects", json=body, headers=auth_headers("alice"))
        assert response.status_code == 400
        assert response.json()["category"] == "validation"

    def test_patch_cannot_touch_protected_fields(self, auth_headers):
        headers = auth_headers("alice")
        project = client.post("/api/v1/projects", json={"name": "p"}, headers=headers).json()
        response = client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"user_id": "mallory", "application_id": "x", "position": {"title": "hax"}},
            headers=headers,
        )
        assert response.status_code == 400  # nothing editable was sent
        assert client.get(f"/api/v1/projects/{project['id']}", headers=headers).json()["user_id"] == "alice"

    def test_projects_are_private_to_their_owner(self, auth_headers):
        project_id = _project_with_position(auth_headers("alice"))
        bob = auth_headers("bob")
        for method, path, kwargs in [
            ("get", f"/api/v1/projects/{project_id}", {}),
            ("patch", f"/api/v1/projects/{project_id}", {"json": {"name": "stolen"}}),
            ("delete", f"/api/v1/projects/{project_id}", {}),
            ("post", f"/api/v1/projects/{project_id}/position", {"json": {"text": AD}}),
            ("post", f"/api/v1/projects/{project_id}/match", {"json": {"cv_text": "x"}}),
            ("post", f"/api/v1/projects/{project_id}/apply", {"json": {"candidate": CANDIDATE}}),
        ]:
            response = getattr(client, method)(path, headers=bob, **kwargs)
            assert response.status_code == 404, (method, path)
        assert client.get("/api/v1/projects", headers=bob).json()["count"] == 0


class TestFromJob:
    JOB = {
        "title": "Backend Developer",
        "company": "Globex",
        "location": "Hamburg",
        "url": "https://jobs.example/globex/1",
        "provider": "adzuna",
        "published_at": "2026-10-05",
        "description": "Build and run Python services for our logistics platform with PostgreSQL.",
    }

    def test_job_search_result_becomes_a_project(self, auth_headers):
        response = client.post("/api/v1/projects/from-job", json={"job": self.JOB}, headers=auth_headers("alice"))
        assert response.status_code == 200
        project = response.json()
        assert project["name"] == "Globex – Backend Developer"
        assert project["status"] == "researching"
        position = project["position"]
        assert (position["title"], position["company"], position["location"]) == (
            "Backend Developer",
            "Globex",
            "Hamburg",
        )
        assert position["source"] == "job_search:adzuna"
        assert "python" in position["keywords"]
        assert position["warnings"] == []

    def test_short_board_snippet_is_flagged_not_hidden(self, auth_headers):
        job = {**self.JOB, "description": "short"}
        position = client.post("/api/v1/projects/from-job", json={"job": job}, headers=auth_headers("a")).json()[
            "position"
        ]
        assert any("full description" in warning for warning in position["warnings"])

    def test_requires_title_or_company(self, auth_headers):
        assert client.post("/api/v1/projects/from-job", json={"job": {}}, headers=auth_headers("a")).status_code == 400


class TestPositionIntake:
    def test_position_endpoints_require_authentication(self):
        assert client.post("/api/v1/positions/extract", json={"text": AD}).status_code == 401
        assert client.post("/api/v1/positions/extract/file", files={"file": ("a.txt", AD.encode())}).status_code == 401

    def test_extract_text_preview(self, auth_headers):
        body = client.post("/api/v1/positions/extract", json={"text": AD}, headers=auth_headers("a")).json()
        assert body["count"] == 1
        assert body["positions"][0]["company"] == "Acme GmbH"

    @pytest.mark.parametrize("payload", [{}, {"url": "https://a.example/x", "text": AD}, {"url": " ", "text": " "}])
    def test_exactly_one_of_url_or_text(self, auth_headers, payload):
        response = client.post("/api/v1/positions/extract", json=payload, headers=auth_headers("a"))
        assert response.status_code == 400
        assert "exactly one" in response.json()["detail"].lower()

    def test_url_extraction_goes_through_the_safe_fetcher(self, auth_headers, monkeypatch):
        monkeypatch.setattr(px, "fetch_url", lambda url, **kw: (AD.encode(), "text/plain", url))
        body = client.post(
            "/api/v1/positions/extract", json={"url": "https://jobs.example/1"}, headers=auth_headers("a")
        ).json()
        assert body["positions"][0]["url"] == "https://jobs.example/1"

    @pytest.mark.parametrize(
        "url", ["http://127.0.0.1:8000/admin", "http://169.254.169.254/latest/meta-data/", "file:///etc/passwd"]
    )
    def test_ssrf_urls_are_rejected_over_http(self, auth_headers, url):
        response = client.post("/api/v1/positions/extract", json={"url": url}, headers=auth_headers("a"))
        assert response.status_code == 400

    def test_file_upload_text_pdf_docx_zip(self, auth_headers):
        headers = auth_headers("a")
        text = client.post(
            "/api/v1/positions/extract/file", files={"file": ("ad.txt", AD.encode(), "text/plain")}, headers=headers
        )
        assert text.status_code == 200 and text.json()["positions"][0]["source"] == "text"

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("one.txt", AD)
            bundle.writestr("two.txt", AD.replace("Acme GmbH", "Globex"))
            bundle.writestr("evil.exe", "MZ")
        zipped = client.post(
            "/api/v1/positions/extract/file", files={"file": ("ads.zip", archive.getvalue())}, headers=headers
        )
        assert zipped.status_code == 200
        assert zipped.json()["count"] == 2
        assert zipped.json()["skipped"] == [{"name": "evil.exe", "reason": "unsupported file type"}]

    def test_oversized_upload_is_rejected(self, auth_headers, monkeypatch):
        monkeypatch.setattr(px, "MAX_UPLOAD_BYTES", 1024)
        response = client.post(
            "/api/v1/positions/extract/file", files={"file": ("big.txt", b"a" * 5000)}, headers=auth_headers("a")
        )
        assert response.status_code == 400
        assert "larger" in response.json()["detail"]

    def test_image_without_ocr_engine_is_a_503_configuration_error(self, auth_headers, monkeypatch):
        from PIL import Image

        def no_ocr(data):
            raise ConfigurationError("Image import needs OCR: install the `tesseract` command-line tool.")

        monkeypatch.setattr(px, "tesseract_ocr", no_ocr)
        image = io.BytesIO()
        Image.new("RGB", (40, 40), "white").save(image, "PNG")
        response = client.post(
            "/api/v1/positions/extract/file",
            files={"file": ("shot.png", image.getvalue(), "image/png")},
            headers=auth_headers("a"),
        )
        assert response.status_code == 503
        assert "OCR" in response.json()["detail"]


class TestAttachPosition:
    def test_attach_from_text_moves_draft_to_researching(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        project = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()
        assert project["status"] == "researching"
        assert project["position"]["title"] == "Senior Python Developer (m/w/d)"

    def test_attach_an_edited_position_object(self, auth_headers):
        headers = auth_headers("a")
        project_id = client.post("/api/v1/projects", json={"name": "p"}, headers=headers).json()["id"]
        edited = {"title": "Staff Engineer", "company": "Initech", "description": AD}
        response = client.post(f"/api/v1/projects/{project_id}/position", json={"position": edited}, headers=headers)
        assert response.status_code == 200
        assert response.json()["project"]["position"]["company"] == "Initech"

    def test_position_and_text_together_are_ambiguous(self, auth_headers):
        headers = auth_headers("a")
        project_id = client.post("/api/v1/projects", json={"name": "p"}, headers=headers).json()["id"]
        response = client.post(
            f"/api/v1/projects/{project_id}/position", json={"position": {"title": "x"}, "text": AD}, headers=headers
        )
        assert response.status_code == 400

    def test_attach_from_zip_with_index(self, auth_headers):
        headers = auth_headers("a")
        project_id = client.post("/api/v1/projects", json={"name": "p"}, headers=headers).json()["id"]
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("a.txt", AD)
            bundle.writestr("b.txt", AD.replace("Acme GmbH", "Globex AG"))
        path = f"/api/v1/projects/{project_id}/position/file"
        second = client.post(path + "?index=1", files={"file": ("ads.zip", archive.getvalue())}, headers=headers)
        assert second.status_code == 200
        assert second.json()["project"]["position"]["company"] == "Globex AG"
        assert [c["company"] for c in second.json()["candidates"]] == ["Acme GmbH", "Globex AG"]
        out_of_range = client.post(path + "?index=5", files={"file": ("ads.zip", archive.getvalue())}, headers=headers)
        assert out_of_range.status_code == 400

    def test_replacing_the_position_clears_the_stale_match(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        client.post(
            f"/api/v1/projects/{project_id}/match", json={"cv_text": "Python developer with FastAPI"}, headers=headers
        )
        assert client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["match"] is not None
        client.post(
            f"/api/v1/projects/{project_id}/position", json={"text": AD.replace("Python", "Rust")}, headers=headers
        )
        assert client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["match"] is None

    def test_remove_position(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        removed = client.delete(f"/api/v1/projects/{project_id}/position", headers=headers)
        assert removed.json()["project"]["position"] is None


class TestMatch:
    def test_scores_pasted_cv_text_and_stores_the_result(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        response = client.post(
            f"/api/v1/projects/{project_id}/match",
            json={"cv_text": "Python developer. FastAPI, PostgreSQL and Docker. Experience\nEducation\nSkills"},
            headers=headers,
        )
        assert response.status_code == 200
        result = response.json()
        assert 0 <= result["score"] <= 100
        assert "python" in [word.lower() for word in result["matched_keywords"]]
        assert client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["match"]["score"] == result["score"]

    def test_scores_an_owned_document(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        doc = client.post(
            "/api/v1/documents",
            json={"title": "CV", "document_type": "cv", "content": "Python FastAPI Docker developer"},
            headers=headers,
        ).json()
        assert (
            client.post(
                f"/api/v1/projects/{project_id}/match", json={"cv_document_id": doc["id"]}, headers=headers
            ).status_code
            == 200
        )

    def test_foreign_document_is_404(self, auth_headers):
        project_id = _project_with_position(auth_headers("a"))
        doc = client.post(
            "/api/v1/documents", json={"title": "CV", "document_type": "cv", "content": "x"}, headers=auth_headers("b")
        ).json()
        response = client.post(
            f"/api/v1/projects/{project_id}/match", json={"cv_document_id": doc["id"]}, headers=auth_headers("a")
        )
        assert response.status_code == 404

    def test_needs_a_cv_and_a_described_position(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        assert client.post(f"/api/v1/projects/{project_id}/match", json={}, headers=headers).status_code == 400
        empty = client.post("/api/v1/projects", json={"name": "no position"}, headers=headers).json()["id"]
        assert client.post(f"/api/v1/projects/{empty}/match", json={"cv_text": "x"}, headers=headers).status_code == 400


class TestApply:
    def test_apply_creates_documents_application_and_links(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        response = client.post(
            f"/api/v1/projects/{project_id}/apply",
            json={"candidate": CANDIDATE, "notes": "via referral", "follow_up_date": "2026-11-10"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ai_generated"] is False
        project, application = body["project"], body["application"]
        assert project["status"] == "applied"
        assert project["application_id"] == application["application_id"]
        assert (application["company"], application["position"], application["status"]) == (
            "Acme GmbH",
            "Senior Python Developer (m/w/d)",
            "applied",
        )
        assert (application["notes"], application["follow_up_date"]) == ("via referral", "2026-11-10")
        assert application["project_id"] == project_id
        assert application["job_key"]

        docs = {d["id"]: d for d in client.get("/api/v1/documents", headers=headers).json()["items"]}
        cv, letter = docs[project["cv_document_id"]], docs[project["cover_letter_document_id"]]
        assert (cv["document_type"], letter["document_type"]) == ("cv", "cover_letter")
        assert application["cv_document_id"] == cv["id"]
        assert "Acme GmbH" in letter["content"] and "Senior Python Developer" in letter["content"]
        assert client.get("/api/v1/applications", headers=headers).json()["count"] == 1

    def test_tailoring_reorders_but_never_adds_or_drops(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        body = client.post(
            f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers
        ).json()
        docs = {d["id"]: d for d in client.get("/api/v1/documents", headers=headers).json()["items"]}
        content = docs[body["documents"]["cv_document_id"]]["content"]
        skills = [line[2:] for line in content.split("Skills\n", 1)[1].splitlines() if line.startswith("- ")]
        assert sorted(skills) == sorted(CANDIDATE["skills"]), "no skill added or removed"
        assert skills.index("Python") < skills.index("Photoshop")
        assert skills.index("FastAPI") < skills.index("Public speaking")
        highlights = [line.strip("  • ").strip() for line in content.splitlines() if "•" in line]
        assert highlights[0] == "Built FastAPI services in Python"
        assert sorted(highlights) == sorted(CANDIDATE["experience"][0]["highlights"])

    def test_second_apply_is_a_409_and_creates_nothing_new(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        assert (
            client.post(
                f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers
            ).status_code
            == 200
        )
        again = client.post(f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers)
        assert again.status_code == 409
        assert again.json()["category"] == "conflict"
        assert client.get("/api/v1/applications", headers=headers).json()["count"] == 1
        assert len(client.get("/api/v1/documents", headers=headers).json()["items"]) == 2

    def test_cover_letter_can_be_skipped(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        body = client.post(
            f"/api/v1/projects/{project_id}/apply",
            json={"candidate": CANDIDATE, "include_cover_letter": False},
            headers=headers,
        ).json()
        assert body["documents"]["cover_letter_document_id"] is None
        assert len(client.get("/api/v1/documents", headers=headers).json()["items"]) == 1

    def test_existing_documents_can_be_attached_instead_of_generated(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        cv = client.post(
            "/api/v1/documents", json={"title": "My CV", "document_type": "cv", "content": "mine"}, headers=headers
        ).json()
        body = client.post(
            f"/api/v1/projects/{project_id}/apply",
            json={"cv_document_id": cv["id"], "include_cover_letter": False},
            headers=headers,
        ).json()
        assert body["documents"]["cv_document_id"] == cv["id"]
        assert body["generated"] == []

    def test_foreign_or_wrong_type_documents_are_rejected(self, auth_headers):
        project_id = _project_with_position(auth_headers("a"))
        foreign = client.post(
            "/api/v1/documents", json={"title": "x", "document_type": "cv", "content": "x"}, headers=auth_headers("b")
        ).json()
        response = client.post(
            f"/api/v1/projects/{project_id}/apply", json={"cv_document_id": foreign["id"]}, headers=auth_headers("a")
        )
        assert response.status_code == 404
        letter = client.post(
            "/api/v1/documents",
            json={"title": "l", "document_type": "cover_letter", "content": "x"},
            headers=auth_headers("a"),
        ).json()
        wrong = client.post(
            f"/api/v1/projects/{project_id}/apply", json={"cv_document_id": letter["id"]}, headers=auth_headers("a")
        )
        assert wrong.status_code == 400

    def test_missing_candidate_name_fails_without_creating_anything(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        response = client.post(
            f"/api/v1/projects/{project_id}/apply", json={"candidate": {"skills": ["x"]}}, headers=headers
        )
        assert response.status_code == 400
        assert "candidate.name" in response.json()["detail"]
        assert client.get("/api/v1/documents", headers=headers).json()["items"] == []
        assert client.get("/api/v1/applications", headers=headers).json()["items"] == []
        assert client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["status"] == "researching"

    def test_position_without_company_cannot_be_applied_to(self, auth_headers):
        headers = auth_headers("a")
        project_id = client.post("/api/v1/projects", json={"name": "p"}, headers=headers).json()["id"]
        client.post(
            f"/api/v1/projects/{project_id}/position",
            json={"text": "Join our team and help us build great products for customers all around the world."},
            headers=headers,
        )
        response = client.post(f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers)
        assert response.status_code == 400
        assert "company" in response.json()["detail"]

    def test_project_without_position_cannot_be_applied_to(self, auth_headers):
        headers = auth_headers("a")
        project_id = client.post("/api/v1/projects", json={"name": "p"}, headers=headers).json()["id"]
        assert (
            client.post(
                f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers
            ).status_code
            == 400
        )

    def test_invalid_follow_up_fails_before_anything_is_created(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        response = client.post(
            f"/api/v1/projects/{project_id}/apply",
            json={"candidate": CANDIDATE, "follow_up_date": "soon"},
            headers=headers,
        )
        assert response.status_code == 400
        assert client.get("/api/v1/documents", headers=headers).json()["items"] == []

    def test_failure_after_document_creation_rolls_the_documents_back(self, auth_headers, monkeypatch):
        from app.application.services import apply_flow

        def boom(payload):
            raise RuntimeError("tracker unavailable")

        monkeypatch.setattr(apply_flow.application_tracker, "create", boom)
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        with pytest.raises(RuntimeError):
            client.post(f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers)
        assert client.get("/api/v1/documents", headers=headers).json()["items"] == [], "no orphaned documents"
        assert client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["status"] == "researching"

    def test_applied_position_cannot_be_removed(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        client.post(f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers)
        assert client.delete(f"/api/v1/projects/{project_id}/position", headers=headers).status_code == 400

    def test_deleting_a_project_keeps_documents_and_tracker_entry(self, auth_headers):
        headers = auth_headers("a")
        project_id = _project_with_position(headers)
        client.post(f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers)
        client.delete(f"/api/v1/projects/{project_id}", headers=headers)
        assert client.get("/api/v1/applications", headers=headers).json()["count"] == 1
        assert len(client.get("/api/v1/documents", headers=headers).json()["items"]) == 2


class TestApplicationsApi:
    def _create(self, headers, **extra):
        return client.post(
            "/api/v1/applications", json={"company": "Acme", "position": "Dev", **extra}, headers=headers
        ).json()

    def test_get_and_patch_notes_follow_up_url(self, auth_headers):
        headers = auth_headers("a")
        app_id = self._create(headers)["application_id"]
        assert client.get(f"/api/v1/applications/{app_id}", headers=headers).json()["company"] == "Acme"
        patched = client.patch(
            f"/api/v1/applications/{app_id}",
            json={
                "notes": "Call on Monday",
                "follow_up_date": "2026-11-03",
                "job_url": "https://jobs.example/1",
                "status": "interview",
            },
            headers=headers,
        ).json()
        assert (patched["notes"], patched["follow_up_date"], patched["job_url"], patched["status"]) == (
            "Call on Monday",
            "2026-11-03",
            "https://jobs.example/1",
            "interview",
        )

    def test_only_sent_fields_change_and_null_clears(self, auth_headers):
        headers = auth_headers("a")
        app_id = self._create(headers, notes="keep", follow_up_date="2026-11-01")["application_id"]
        patched = client.patch(f"/api/v1/applications/{app_id}", json={"follow_up_date": None}, headers=headers).json()
        assert patched["follow_up_date"] is None
        assert patched["notes"] == "keep"

    @pytest.mark.parametrize(
        "body", [{}, {"follow_up_date": "tomorrow"}, {"status": "ghosted"}, {"company": " "}, {"user_id": "x"}]
    )
    def test_invalid_patch_is_a_400(self, auth_headers, body):
        headers = auth_headers("a")
        app_id = self._create(headers)["application_id"]
        assert client.patch(f"/api/v1/applications/{app_id}", json=body, headers=headers).status_code == 400

    def test_other_users_cannot_read_or_edit(self, auth_headers):
        app_id = self._create(auth_headers("a"))["application_id"]
        assert client.get(f"/api/v1/applications/{app_id}", headers=auth_headers("b")).status_code == 404
        assert (
            client.patch(f"/api/v1/applications/{app_id}", json={"notes": "x"}, headers=auth_headers("b")).status_code
            == 404
        )

    def test_requires_authentication(self):
        assert client.get("/api/v1/applications/x").status_code == 401
        assert client.patch("/api/v1/applications/x", json={"notes": "x"}).status_code == 401

    def test_status_endpoint_still_works(self, auth_headers):
        headers = auth_headers("a")
        app_id = self._create(headers)["application_id"]
        assert (
            client.patch(f"/api/v1/applications/{app_id}/status", json={"status": "offer"}, headers=headers).json()[
                "status"
            ]
            == "offer"
        )


class StaticProvider:
    name = "fake"

    def __init__(self, jobs):
        self.jobs = jobs

    def search(self, query, location=None, limit=5, page=1, options=None):
        return ProviderSearchResult(self.jobs, has_more=False)


def _jobs():
    return [
        Job(
            "Senior Python Developer (m/w/d)",
            "Acme GmbH",
            "Berlin",
            "d",
            "https://jobs.example/acme",
            "fake",
            "1",
            _days_ago(2),
        ),
        Job("Data Engineer", "Globex", "Hamburg", "d", "https://jobs.example/globex", "fake", "2", _days_ago(3)),
        Job("Old Posting", "Initech", "Köln", "d", "https://jobs.example/old", "fake", "3", _days_ago(90)),
    ]


class TestJobSearchWithUser:
    @pytest.fixture(autouse=True)
    def _providers(self, monkeypatch):
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [StaticProvider(_jobs())])

    def _titles(self, response):
        assert response.status_code == 200, response.text
        return [job["title"] for job in response.json()["results"]]

    def test_anonymous_search_is_recent_only_and_not_filtered_by_applications(self):
        titles = self._titles(client.get("/api/v1/jobs/search", params={"query": "dev"}))
        assert titles == ["Senior Python Developer (m/w/d)", "Data Engineer"]  # 90-day-old posting is gone

    def test_include_old_returns_everything(self):
        titles = self._titles(client.get("/api/v1/jobs/search", params={"query": "dev", "include_old": "true"}))
        assert "Old Posting" in titles

    def test_wider_window_includes_older_postings(self):
        titles = self._titles(client.get("/api/v1/jobs/search", params={"query": "dev", "published_since_days": 100}))
        assert "Old Posting" in titles

    def test_applied_jobs_disappear_for_that_user_only(self, auth_headers):
        headers = auth_headers("alice")
        project_id = _project_with_position(headers)  # Acme GmbH – Senior Python Developer
        client.post(f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers)

        alice = client.get("/api/v1/jobs/search", params={"query": "dev"}, headers=headers)
        assert self._titles(alice) == ["Data Engineer"]
        assert alice.json()["audit"]["excluded_applied"] == 1
        assert self._titles(
            client.get("/api/v1/jobs/search", params={"query": "dev"}, headers=auth_headers("bob"))
        ) == [
            "Senior Python Developer (m/w/d)",
            "Data Engineer",
        ]
        # …and the cached anonymous variant is unaffected.
        assert len(self._titles(client.get("/api/v1/jobs/search", params={"query": "dev"}))) == 2

    def test_include_applied_shows_them_annotated_with_their_status(self, auth_headers):
        headers = auth_headers("alice")
        project_id = _project_with_position(headers)
        client.post(f"/api/v1/projects/{project_id}/apply", json={"candidate": CANDIDATE}, headers=headers)
        app_id = client.get("/api/v1/applications", headers=headers).json()["items"][0]["application_id"]
        client.patch(f"/api/v1/applications/{app_id}/status", json={"status": "interview"}, headers=headers)

        response = client.get(
            "/api/v1/jobs/search", params={"query": "dev", "include_applied": "true"}, headers=headers
        )
        by_title = {job["title"]: job for job in response.json()["results"]}
        assert by_title["Senior Python Developer (m/w/d)"]["application_status"] == "interview"
        assert by_title["Data Engineer"]["application_status"] is None

    def test_manually_tracked_job_is_excluded_too(self, auth_headers):
        headers = auth_headers("alice")
        client.post("/api/v1/applications", json={"company": "Globex", "position": "Data Engineer"}, headers=headers)
        assert self._titles(client.get("/api/v1/jobs/search", params={"query": "dev"}, headers=headers)) == [
            "Senior Python Developer (m/w/d)"
        ]

    def test_results_expose_the_job_key(self):
        job = client.get("/api/v1/jobs/search", params={"query": "dev"}).json()["results"][0]
        assert len(job["job_key"]) == 20
