"""End-to-end journey test (TEST-01).

Exercises the full user journey through the HTTP API:
signup → login → profile → CV → persist → edit → export →
search → track.

Supabase Auth is not available in the test environment, so the
journey simulates the authenticated flow by minting a JWT with
the same HS256 secret the API uses (the same mechanism the
`auth_headers` fixture uses). Every step goes through the real
HTTP routes, so the test proves the routes compose into a
coherent journey rather than only working in isolation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import AppSettings
from app.core.security import auth
from app.main import app

client = TestClient(app)


@pytest.fixture
def auth_headers(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], dict[str, str]]:
    """Mint a valid HS256 bearer token for a simulated user."""
    secret = "e2e-journey-signing-secret-2026-abc"
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=secret))

    def build(user_id: str) -> dict[str, str]:
        token = jwt.encode(
            {
                "sub": user_id,
                "email": f"{user_id}@example.test",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            secret,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    return build


def test_e2e_journey(auth_headers):
    """signup → login → profile → CV → persist → edit → export → search → track."""
    user_id = "e2e-user"
    headers = auth_headers(user_id)

    # --- signup / login (simulated): identity is the JWT sub ---
    assert headers["Authorization"].startswith("Bearer ")

    # --- profile: create, read, update ---
    created_profile = client.post(
        "/api/v1/profiles",
        json={
            "user_id": user_id,
            "email": "e2e@example.test",
            "full_name": "E2E Tester",
            "target_role": "Data Analyst",
            "summary": "Analyst with SQL and Python skills.",
        },
        headers=headers,
    )
    assert created_profile.status_code == 200
    assert created_profile.json()["target_role"] == "Data Analyst"

    fetched_profile = client.get(f"/api/v1/profiles/{user_id}", headers=headers)
    assert fetched_profile.status_code == 200
    assert fetched_profile.json()["full_name"] == "E2E Tester"

    updated_profile = client.patch(
        f"/api/v1/profiles/{user_id}",
        json={"target_role": "Senior Data Analyst"},
        headers=headers,
    )
    assert updated_profile.status_code == 200
    assert updated_profile.json()["target_role"] == "Senior Data Analyst"

    # --- CV: generate (offline template path) ---
    cv = client.post(
        "/api/v1/documents/cv/generate",
        json={
            "name": "E2E Tester",
            "target_role": "Senior Data Analyst",
            "summary": "Analyst with SQL and Python skills.",
        },
        headers=headers,
    )
    assert cv.status_code == 200
    cv_payload = cv.json()
    assert cv_payload["ai_generated"] is False
    assert "E2E Tester" in cv_payload["content"]

    # --- persist: store the generated CV as a document ---
    stored = client.post(
        "/api/v1/documents",
        json={
            "title": "E2E CV",
            "document_type": "cv",
            "template_id": "professional",
            "content": cv_payload["content"],
        },
        headers=headers,
    )
    assert stored.status_code == 200
    document_id = stored.json()["id"]

    listed = client.get("/api/v1/documents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1

    # --- edit: update the persisted document ---
    edited = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"content": cv_payload["content"] + "\n\nAdditional section."},
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["version"] >= 1

    # --- export: HTML and text ---
    exported_html = client.get(
        f"/api/v1/documents/{document_id}/export",
        params={"format": "html"},
        headers=headers,
    )
    assert exported_html.status_code == 200
    assert "E2E Tester" in exported_html.text

    exported_text = client.get(
        f"/api/v1/documents/{document_id}/export",
        params={"format": "text"},
        headers=headers,
    )
    assert exported_text.status_code == 200
    assert "E2E Tester" in exported_text.text

    # --- search: job search (no provider configured → 503, not mock data) ---
    search = client.get(
        "/api/v1/jobs/search",
        params={"query": "data analyst"},
    )
    assert search.status_code == 503
    assert "No job provider" in search.json()["detail"]

    # --- track: add an application to the tracker ---
    tracked = client.post(
        "/api/v1/applications",
        json={
            "user_id": user_id,
            "company": "E2E Corp",
            "position": "Senior Data Analyst",
            "status": "applied",
        },
        headers=headers,
    )
    assert tracked.status_code == 200
    application_id = tracked.json()["application_id"]

    listed_apps = client.get("/api/v1/applications", headers=headers)
    assert listed_apps.status_code == 200
    assert listed_apps.json()["count"] >= 1

    # --- status flow: applied → interview ---
    status_update = client.patch(
        f"/api/v1/applications/{application_id}/status",
        json={"status": "interview"},
        headers=headers,
    )
    assert status_update.status_code == 200
    assert status_update.json()["status"] == "interview"

    # --- cleanup: delete the tracked application and the document ---
    deleted_app = client.delete(
        f"/api/v1/applications/{application_id}",
        headers=headers,
    )
    assert deleted_app.status_code == 200

    deleted_doc = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=headers,
    )
    assert deleted_doc.status_code == 200

    # --- GDPR erasure: delete all my data ---
    erased = client.delete("/api/v1/profiles/me", headers=headers)
    assert erased.status_code == 200
    assert erased.json()["deleted"] is True
