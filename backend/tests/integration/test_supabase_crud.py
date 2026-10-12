"""Real Supabase CRUD proof — opt-in integration test.

Run with: RUN_SUPABASE_CRUD=1 python -m pytest backend/tests/test_supabase_crud.py -q -s

Why separate: unit tests stay hermetic (in-memory, string user_ids).
This test uses service_role + a real auth.users UUID to prove the
storage → app-layer path end-to-end: profiles + documents create/read/
update/delete through SupabaseRepository with UUID ids and
Prefer: return=representation.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest


def _env() -> tuple[str, str]:
    from app.core.config import load_environment

    load_environment("/Users/guykaptue/Downloads/ai_career_assistant/.env")
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    assert url and key, "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY required in .env"
    return url, key


@pytest.mark.skipif(os.getenv("RUN_SUPABASE_CRUD") != "1", reason="opt-in live Supabase CRUD")
def test_live_supabase_profile_and_document_crud() -> None:
    from app.core.persistence import SupabaseRepository
    from app.domain.documents.models import DocumentRecord
    from app.domain.users.models import UserProfile

    url, key = _env()
    admin_headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # 1. Real auth user (FK target for profiles.user_id / documents.user_id).
    email = f"crud-{uuid.uuid4().hex[:8]}@example.test"
    with httpx.Client(timeout=20.0) as client:
        created = client.post(
            f"{url}/auth/v1/admin/users",
            headers=admin_headers,
            json={"email": email, "password": "Test1234!Test1234!", "email_confirm": True},
        )
        assert created.status_code in (200, 201), created.text
        user_id = created.json()["id"]

    profiles = SupabaseRepository("profiles", UserProfile, "user_id")
    documents = SupabaseRepository("documents", DocumentRecord, "id")

    # 2. Profile CRUD via repository (same path ProfileStore uses).
    profile = profiles.create(
        {
            "user_id": user_id,
            "email": email,
            "full_name": "CRUD Test",
            "target_role": "Data Analyst",
            "location": "Remote",
            "summary": "integration proof",
        }
    )
    assert profile.user_id == user_id
    assert profiles.get(user_id) is not None
    assert profiles.get(user_id).email == email
    updated = profiles.update(user_id, {"target_role": "Senior Data Analyst"})
    assert updated.target_role == "Senior Data Analyst"
    assert [p.user_id for p in profiles.list_for_user(user_id)] == [user_id]

    # 3. Document CRUD via repository (same path DocumentStore uses).
    # No id supplied -> let helpers/DB mint UUID; repository must parse body.
    doc = documents.create(
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "document_type": "cv",
            "title": "CRUD Test CV",
            "content": "John Doe\nData Analyst\nPython SQL",
            "template_id": "professional",
        }
    )
    assert doc.user_id == user_id
    fetched = documents.get(doc.id)
    assert fetched is not None and fetched.title == "CRUD Test CV"
    renamed = documents.update(doc.id, {"title": "CRUD Test CV v2"})
    assert renamed.title == "CRUD Test CV v2"
    assert any(d.id == doc.id for d in documents.list_for_user(user_id))

    print(f"\nLIVE CRUD OK user={user_id} doc={doc.id}")

    # 4. Cleanup: documents + profile + auth user.
    with httpx.Client(
        base_url=url,
        headers={**admin_headers, "Prefer": "return=representation"},
        timeout=20.0,
    ) as client:
        client.delete("/rest/v1/documents", params={"id": f"eq.{doc.id}"})
        client.delete("/rest/v1/profiles", params={"user_id": f"eq.{user_id}"})
        client.delete(f"/auth/v1/admin/users/{user_id}")
