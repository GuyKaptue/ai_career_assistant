"""Characterization test for general (legacy) path - ensures byte-identical behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.core.config import AppSettings
from app.core.security import auth
from app.main import app
from tests.conftest import TEST_JWT_SECRET

client = TestClient(app)


def _auth(monkeypatch, user_id: str = "char") -> dict[str, str]:
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=TEST_JWT_SECRET))
    token = jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


# --- Success path ---
def test_general_success_returns_chat_contract(monkeypatch):
    captured = {}
    content = """## Summary
Give practical career advice tailored to the conversation.
## Steps
- Review your goals
- Take concrete action
## Caveats
Results vary by market."""

    class OkAdapter:
        def generate_with_fallback(self, **kwargs):
            captured.update(kwargs)
            return {
                "content": content,
                "model_id": "m/chat",
                "fallback_chain": [],
                "routing_score": 0.9,
                "required_context": 1024,
            }

    monkeypatch.setattr("app.application.services.chat_service.get_adapter", lambda: OkAdapter())
    monkeypatch.setattr(
        "app.application.services.knowledge_base.get_knowledge_base",
        lambda: type("K", (), {"retrieve_for_generation": lambda self, query: {"context": ""}})(),
    )
    monkeypatch.setattr(
        "app.application.services.document_retrieval.get_document_retrieval",
        lambda: type("D", (), {"retrieve_for_generation": lambda self, user_id, query: {"context": ""}})(),
    )
    h = _auth(monkeypatch, "c1")
    s = client.post("/api/v1/chat/sessions", json={"title": "t", "mode": "general"}, headers=h).json()
    r = client.post("/api/v1/chat/completions", json={"session_id": s["id"], "message": "hi"}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["ai_generated"] is True
    assert d["fallback"] is False
    assert d["message"]["role"] == "assistant"
    assert d["message"]["content"].startswith("## Summary")
    assert "AI-generated content" in d["message"]["content"]


# --- Provider failure fallback ---
def test_general_provider_failure_returns_fallback(monkeypatch):
    from app.core.errors import AIProviderError

    class FailAdapter:
        def generate_with_fallback(self, **kwargs):
            raise AIProviderError("MODEL_UNAVAILABLE: provider down")

    monkeypatch.setattr("app.application.services.chat_service.get_adapter", lambda: FailAdapter())
    monkeypatch.setattr(
        "app.application.services.knowledge_base.get_knowledge_base",
        lambda: type("K", (), {"retrieve_for_generation": lambda self, query: {"context": ""}})(),
    )
    monkeypatch.setattr(
        "app.application.services.document_retrieval.get_document_retrieval",
        lambda: type("D", (), {"retrieve_for_generation": lambda self, user_id, query: {"context": ""}})(),
    )
    h = _auth(monkeypatch, "c2")
    s = client.post("/api/v1/chat/sessions", json={"title": "t", "mode": "general"}, headers=h).json()
    r = client.post("/api/v1/chat/completions", json={"session_id": s["id"], "message": "hi"}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["ai_generated"] is False
    assert d["fallback"] is True
    assert "Offline reply" in d["message"]["content"]


# --- Validation failure after repair (contract-based fallback) ---
def test_general_validation_failure_after_repair_returns_fallback(monkeypatch):
    from app.application.services import output_validation

    calls = []

    class RepairFailAdapter:
        def generate_with_fallback(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {
                    "content": "Not the right format",
                    "model_id": "m/chat",
                    "fallback_chain": [],
                    "routing_score": 0.9,
                    "required_context": 1024,
                }
            return {
                "content": "Still wrong",
                "model_id": "m/chat",
                "fallback_chain": [],
                "routing_score": 0.9,
                "required_context": 1024,
            }

    monkeypatch.setattr("app.application.services.chat_service.get_adapter", lambda: RepairFailAdapter())
    monkeypatch.setattr(output_validation, "DEFAULT_MAX_REPAIRS", 1)
    monkeypatch.setattr(
        "app.application.services.knowledge_base.get_knowledge_base",
        lambda: type("K", (), {"retrieve_for_generation": lambda self, query: {"context": ""}})(),
    )
    monkeypatch.setattr(
        "app.application.services.document_retrieval.get_document_retrieval",
        lambda: type("D", (), {"retrieve_for_generation": lambda self, user_id, query: {"context": ""}})(),
    )
    h = _auth(monkeypatch, "c3")
    s = client.post("/api/v1/chat/sessions", json={"title": "t", "mode": "general"}, headers=h).json()
    r = client.post("/api/v1/chat/completions", json={"session_id": s["id"], "message": "hi"}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["ai_generated"] is False
    assert d["fallback"] is True
    # Contract-based fallback from deterministic_unavailable_content for CHAT_CONTRACT
    assert "The AI did not return a valid result" in d["message"]["content"]
    assert "missing required section(s)" in d["message"]["content"]


# --- DE language ---
def test_general_de_language(monkeypatch):
    content = """## Summary
Geben Sie praktische Karriereratschläge, die auf das Gespräch zugeschnitten sind.
## Steps
- Überprüfen Sie Ihre Ziele
- Ergreifen Sie konkrete Maßnahmen
## Caveats
Die Ergebnisse variieren je nach Markt."""

    class OkAdapter:
        def generate_with_fallback(self, **kwargs):
            return {
                "content": content,
                "model_id": "m/chat",
                "fallback_chain": [],
                "routing_score": 0.9,
                "required_context": 1024,
            }

    monkeypatch.setattr("app.application.services.chat_service.get_adapter", lambda: OkAdapter())
    monkeypatch.setattr(
        "app.application.services.knowledge_base.get_knowledge_base",
        lambda: type("K", (), {"retrieve_for_generation": lambda self, query: {"context": ""}})(),
    )
    monkeypatch.setattr(
        "app.application.services.document_retrieval.get_document_retrieval",
        lambda: type("D", (), {"retrieve_for_generation": lambda self, user_id, query: {"context": ""}})(),
    )
    h = _auth(monkeypatch, "c4")
    s = client.post("/api/v1/chat/sessions", json={"title": "t", "mode": "general", "language": "de"}, headers=h).json()
    r = client.post("/api/v1/chat/completions", json={"session_id": s["id"], "message": "hi"}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "Karriereratschläge" in d["message"]["content"]


# --- FR language ---
def test_general_fr_language(monkeypatch):
    content = """## Summary
Donnez des conseils de carrière pratiques adaptés à la conversation.
## Steps
- Réviser vos objectifs
- Prendre des mesures concrètes
## Caveats
Les résultats varient selon le marché."""

    class OkAdapter:
        def generate_with_fallback(self, **kwargs):
            return {
                "content": content,
                "model_id": "m/chat",
                "fallback_chain": [],
                "routing_score": 0.9,
                "required_context": 1024,
            }

    monkeypatch.setattr("app.application.services.chat_service.get_adapter", lambda: OkAdapter())
    monkeypatch.setattr(
        "app.application.services.knowledge_base.get_knowledge_base",
        lambda: type("K", (), {"retrieve_for_generation": lambda self, query: {"context": ""}})(),
    )
    monkeypatch.setattr(
        "app.application.services.document_retrieval.get_document_retrieval",
        lambda: type("D", (), {"retrieve_for_generation": lambda self, user_id, query: {"context": ""}})(),
    )
    h = _auth(monkeypatch, "c5")
    s = client.post("/api/v1/chat/sessions", json={"title": "t", "mode": "general", "language": "fr"}, headers=h).json()
    r = client.post("/api/v1/chat/completions", json={"session_id": s["id"], "message": "hi"}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "conseils" in d["message"]["content"]
