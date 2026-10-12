"""Chat platform API + service tests.

Covers session lifecycle (create/list/get/delete), per-user isolation
(foreign threads answer 404, never 403), turn execution with a stubbed
HF adapter (success + deterministic fallback), validation, the public
models listing, and the pure prompt/fallback helpers.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.application.services.chat_service import (
    deterministic_fallback_reply,
    run_chat_turn,
)
from app.domain.chat.models import ChatSession
from app.main import app

client = TestClient(app)

STUB_INFERENCE = {
    "model_id": "test/model",
    # Must satisfy the career_advice markdown contract (## Summary / ## Steps).
    "content": (
        "## Summary\nHere is career guidance tailored to you.\n\n"
        "## Steps\n- Be specific about the role you are targeting.\n"
    ),
    "fallback_reason": None,
    "fallback_chain": [],
    "routing_score": 0.9,
    "required_context": 1024,
}


class _OkAdapter:
    def __init__(self, captured: dict) -> None:
        self._captured = captured

    def generate_with_fallback(self, **kwargs):
        self._captured.update(kwargs)
        return dict(STUB_INFERENCE)


class _FailingAdapter:
    def generate_with_fallback(self, **kwargs):
        raise RuntimeError("MODEL_UNAVAILABLE: all candidates down")


def test_create_session_requires_auth():
    response = client.post("/api/v1/chat/sessions", json={"title": "Hi"})
    assert response.status_code == 401


def test_create_and_list_sessions_scoped_to_user(auth_headers):
    headers = auth_headers("chat-user-1")

    created = client.post(
        "/api/v1/chat/sessions",
        json={"title": "First chat", "mode": "cv_builder"},
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["user_id"] == "chat-user-1"
    assert body["mode"] == "cv_builder"
    assert body["message_count"] == 0
    assert "messages" not in body

    listed = client.get("/api/v1/chat/sessions", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["id"] == body["id"]

    # Another user's list must not leak this thread.
    other = client.get("/api/v1/chat/sessions", headers=auth_headers("chat-user-2"))
    assert other.status_code == 200
    assert other.json()["count"] == 0


def test_create_session_rejects_unknown_mode(auth_headers):
    response = client.post(
        "/api/v1/chat/sessions",
        json={"mode": "not_a_mode"},
        headers=auth_headers("chat-user-mode"),
    )
    assert response.status_code == 400
    assert response.json()["category"] == "validation"


def test_get_and_delete_session_isolation(auth_headers):
    headers = auth_headers("chat-user-3")
    created = client.post("/api/v1/chat/sessions", json={}, headers=headers).json()
    session_id = created["id"]

    got = client.get(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["id"] == session_id

    # Foreign access returns 404 (never 403) to avoid leaking existence.
    foreign = client.get(f"/api/v1/chat/sessions/{session_id}", headers=auth_headers("chat-user-4"))
    assert foreign.status_code == 404

    deleted = client.delete(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.delete(f"/api/v1/chat/sessions/{session_id}", headers=auth_headers("chat-user-4"))
    assert missing.status_code == 404


def test_completions_success_appends_and_returns_assistant(auth_headers, monkeypatch):
    from app.application.services import chat_service as service_module

    captured: dict = {}
    monkeypatch.setattr(service_module, "get_adapter", lambda: _OkAdapter(captured))

    headers = auth_headers("chat-user-5")
    session_id = client.post("/api/v1/chat/sessions", json={}, headers=headers).json()["id"]

    response = client.post(
        "/api/v1/chat/completions",
        json={
            "session_id": session_id,
            "message": "How do I write a strong CV summary?",
            "model_id": "test/model",
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["ai_generated"] is True
    assert body["fallback"] is False
    assert body["model_id"] == "test/model"
    assert body["message"]["role"] == "assistant"
    # The chosen model must be honoured by the router call.
    assert captured.get("preferred_model_id") == "test/model"

    history = client.get(f"/api/v1/chat/sessions/{session_id}", headers=headers).json()
    roles = [m["role"] for m in history["messages"]]
    assert roles == ["user", "assistant"]


def test_completions_require_auth():
    response = client.post("/api/v1/chat/completions", json={"session_id": "x", "message": "hi"})
    assert response.status_code == 401


def test_completions_reject_empty_message(auth_headers):
    headers = auth_headers("chat-user-6")
    session_id = client.post("/api/v1/chat/sessions", json={}, headers=headers).json()["id"]

    response = client.post(
        "/api/v1/chat/completions",
        json={"session_id": session_id, "message": "   "},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["category"] == "validation"


def test_completions_foreign_session_returns_404(auth_headers):
    owner = auth_headers("chat-owner")
    session_id = client.post("/api/v1/chat/sessions", json={}, headers=owner).json()["id"]

    intruder = client.post(
        "/api/v1/chat/completions",
        json={"session_id": session_id, "message": "hi"},
        headers=auth_headers("chat-intruder"),
    )
    assert intruder.status_code == 404


def test_completions_unknown_session_returns_404(auth_headers):
    headers = auth_headers("chat-user-7")
    response = client.post(
        "/api/v1/chat/completions",
        json={"session_id": "does-not-exist", "message": "hi"},
        headers=headers,
    )
    assert response.status_code == 404


def test_completions_ai_failure_uses_deterministic_fallback(auth_headers, monkeypatch):
    from app.application.services import chat_service as service_module

    monkeypatch.setattr(service_module, "get_adapter", lambda: _FailingAdapter())

    headers = auth_headers("chat-user-8")
    session_id = client.post("/api/v1/chat/sessions", json={}, headers=headers).json()["id"]

    response = client.post(
        "/api/v1/chat/completions",
        json={"session_id": session_id, "message": "Hello?"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ai_generated"] is False
    assert body["fallback"] is True
    assert body["model_id"] is None
    assert "Offline reply" in body["message"]["content"]


def test_models_listing_is_public_and_wellformed():
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == len(payload["items"])
    for item in payload["items"]:
        assert set(item).issuperset({"model_id", "provider", "health_status", "capabilities"})


def test_run_chat_turn_requires_message():
    session = ChatSession(id="s1", user_id="u1")
    try:
        run_chat_turn(session, "   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty message")


def test_deterministic_fallback_reply_is_labelled_and_not_ai():
    session = ChatSession(id="s1", user_id="u1", mode="cv_builder")
    reply = deterministic_fallback_reply(session, "help me")
    assert "Offline reply" in reply
    assert "cv_builder" in reply
