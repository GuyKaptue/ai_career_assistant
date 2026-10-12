"""API tests for the AI chat platform (sessions + completions).

Chat sessions are user-scoped (Bearer JWT). Completions append a user
message, run inference through the shared HF adapter (with deterministic
offline fallback), and return the assistant message. The adapter is stubbed
here so tests never touch the network, mirroring the CV-generation tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.core.config import AppSettings
from app.core.security import auth
from app.main import app
from tests.conftest import TEST_JWT_SECRET

client = TestClient(app)


def _auth(monkeypatch, user_id: str = "chat-user") -> dict[str, str]:
    """Build a valid bearer header using the shared test signing secret."""
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=TEST_JWT_SECRET))
    token = jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_models_endpoint_lists_models() -> None:
    response = client.get("/api/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert all("model_id" in item for item in payload["items"])


def test_create_session_requires_auth() -> None:
    response = client.post("/api/v1/chat/sessions", json={})

    assert response.status_code == 401


def test_create_session_returns_owned_thread(monkeypatch) -> None:
    headers = _auth(monkeypatch, "chat-owner")
    response = client.post(
        "/api/v1/chat/sessions",
        json={"title": "My CV thread", "mode": "cv_builder"},
        headers=headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user_id"] == "chat-owner"
    assert payload["mode"] == "cv_builder"
    assert payload["message_count"] == 0


def test_list_sessions_returns_only_own_threads(monkeypatch) -> None:
    owner = _auth(monkeypatch, "chat-list-owner")
    other = _auth(monkeypatch, "chat-list-other")
    client.post("/api/v1/chat/sessions", json={"title": "Owner thread"}, headers=owner)
    client.post("/api/v1/chat/sessions", json={"title": "Other thread"}, headers=other)

    response = client.get("/api/v1/chat/sessions", headers=owner)

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["user_id"] == "chat-list-owner"


def test_chat_completion_appends_assistant_message(monkeypatch) -> None:
    from app.api.routes import chat as chat_route

    result = {
        "session_id": "s",
        "message": {
            "id": "m2",
            "session_id": "s",
            "role": "assistant",
            "content": "Here is a concise CV tip.\n\nAI-generated content — review before sending.",
            "model_id": "test/chat-model",
            "citations": [],
            "artifact": None,
            "created_at": "",
        },
        "model_id": "test/chat-model",
        "ai_generated": True,
        "fallback": False,
        "fallback_reason": None,
        "citations": [],
        "review_notice": "AI-generated content — review before sending.",
    }

    monkeypatch.setattr(chat_route, "run_chat_turn", lambda *a, **k: result)

    headers = _auth(monkeypatch, "chat-complete")
    session = client.post("/api/v1/chat/sessions", json={"title": "Chat"}, headers=headers).json()

    response = client.post(
        "/api/v1/chat/completions",
        json={"session_id": session["id"], "message": "How do I write a CV summary?"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_generated"] is True
    assert payload["fallback"] is False
    assert payload["model_id"] == "test/chat-model"
    assert "review before sending" in payload["message"]["content"]


def test_chat_completion_falls_back_when_inference_fails(monkeypatch) -> None:
    from app.api.routes import chat as chat_route

    result = {
        "session_id": "s",
        "message": {
            "id": "m2",
            "session_id": "s",
            "role": "assistant",
            "content": "[Offline reply — AI inference is unavailable right now]",
            "model_id": None,
            "citations": [],
            "artifact": None,
            "created_at": "",
        },
        "model_id": None,
        "ai_generated": False,
        "fallback": True,
        "fallback_reason": "MODEL_UNAVAILABLE: provider down",
        "citations": [],
        "review_notice": "AI-generated content — review before sending.",
    }

    monkeypatch.setattr(chat_route, "run_chat_turn", lambda *a, **k: result)

    headers = _auth(monkeypatch, "chat-fallback")
    session = client.post("/api/v1/chat/sessions", json={"title": "Chat"}, headers=headers).json()

    response = client.post(
        "/api/v1/chat/completions",
        json={"session_id": session["id"], "message": "Hello"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_generated"] is False
    assert payload["fallback"] is True
    assert payload["fallback_reason"] is not None


def test_chat_completion_rejects_empty_message(monkeypatch) -> None:
    headers = _auth(monkeypatch, "chat-empty")
    session = client.post("/api/v1/chat/sessions", json={"title": "Chat"}, headers=headers).json()

    response = client.post(
        "/api/v1/chat/completions",
        json={"session_id": session["id"], "message": "   "},
        headers=headers,
    )

    assert response.status_code == 400


def test_chat_completion_rejects_foreign_session(monkeypatch) -> None:
    owner = _auth(monkeypatch, "chat-cross-owner")
    intruder = _auth(monkeypatch, "chat-cross-intruder")
    session = client.post("/api/v1/chat/sessions", json={"title": "Private"}, headers=owner).json()

    # Another user cannot read or post into someone else's thread. The route
    # rejects with 404 (before any inference) to avoid leaking thread existence.
    get_response = client.get(f"/api/v1/chat/sessions/{session['id']}", headers=intruder)
    post_response = client.post(
        "/api/v1/chat/completions",
        json={"session_id": session["id"], "message": "intrusion"},
        headers=intruder,
    )

    assert get_response.status_code == 404
    assert post_response.status_code == 404


def test_delete_session_removes_owned_thread(monkeypatch) -> None:
    headers = _auth(monkeypatch, "chat-delete")
    session = client.post("/api/v1/chat/sessions", json={"title": "Bye"}, headers=headers).json()

    response = client.delete(f"/api/v1/chat/sessions/{session['id']}", headers=headers)

    assert response.status_code == 200
    listing = client.get("/api/v1/chat/sessions", headers=headers).json()
    assert listing["count"] == 0
