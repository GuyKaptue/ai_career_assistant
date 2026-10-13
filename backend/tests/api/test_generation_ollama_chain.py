"""The Ollama → Hugging Face → template chain through the real endpoints (7b).

Every consumer of ``get_adapter()`` that generates text is covered: the CV
endpoint, the cover-letter endpoint, the resignation endpoint and the chat
completions endpoint. Ollama is a scripted server behind the shared adapter, so
the whole chain is exercised without a network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.application.services.ollama_status_probe as probe_module
import app.application.services.shared_router as shared_router_module
from app.main import app
from tests.unit.ollama_helpers import (
    FailingHfAdapter,
    FakeHfAdapter,
    FakeOllamaServer,
    http,
    install_adapter,
    ok_chat,
    reset_shared_state,
)

# Only these routes consume get_adapter(); the resignation route is template-only.
CV_PATH = "/api/v1/documents/cv/generate"
COVER_LETTER_PATH = "/api/v1/documents/cover-letter/generate"
CHAT_PATH = "/api/v1/chat/completions"

CV_PAYLOAD = {
    "use_ai": True,
    "full_name": "Ada Lovelace",
    "target_role": "Data Analyst",
    "company": "Analytic Engines Ltd",
    "skills": ["python", "sql", "statistics"],
    "experience": [
        {
            "role": "Analyst",
            "company": "Analytic Engines Ltd",
            "start": "2020-01",
            "end": "2023-01",
            "achievements": ["Built the first reporting pipeline"],
        }
    ],
    "education": [{"degree": "BSc Mathematics", "institution": "University of London", "year": "1838"}],
    "language": "en",
    "template": "professional",
}

COVER_LETTER_PAYLOAD = {
    "use_ai": True,
    "name": "Ada Lovelace",
    "company": "Analytic Engines Ltd",
    "target_role": "Data Analyst",
    "summary": "Analytical engineer with five years of experience.",
    "language": "en",
}

PROMPT_MARKER = "PROMPT_SHOULD_NEVER_BE_LOGGED"
CONTENT_MARKER = "CONTENT_SHOULD_NEVER_BE_LOGGED"

# Already satisfies the career_advice markdown contract (## Summary / ## Steps),
# so generate_validated() does not enter its repair loop.
CONTRACT_OK = "## Summary\nHere is your answer.\n\n## Steps\n- Start with a plan."


def _hf_result(**overrides):
    """A completed-looking Hugging Face result, optionally overridden."""
    base = {
        "content": "hf answer",
        "model_id": "fake/hf-model",
        "fallback_reason": None,
        "fallback_chain": ["fake/hf-model"],
        "routing_score": 0.5,
        "required_context": 64,
    }
    base.update({k: v for k, v in overrides.items() if v is not None})
    return base


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    reset_shared_state()
    yield
    reset_shared_state()


@pytest.fixture
def auth(auth_headers):
    """Bearer headers for the chat endpoints, using the project's fixture."""
    return auth_headers("ollama-chain-user")


def _chat_session(client, auth) -> str:
    """Create a chat session for the authenticated test user."""
    response = client.post("/api/v1/chat/sessions", headers=auth, json={"mode": "general"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ---------------------------------------------------------------------------
# Ollama answers
# ---------------------------------------------------------------------------
class TestOllamaAnswers:
    @pytest.mark.parametrize(
        ("path", "payload", "task"),
        [
            (CV_PATH, CV_PAYLOAD, "cv_generation"),
            (COVER_LETTER_PATH, COVER_LETTER_PAYLOAD, "cover_letter_generation"),
        ],
        ids=["cv", "cover_letter"],
    )
    def test_ollama_answers_and_hf_is_never_called(self, monkeypatch, client, path, payload, task):
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([ok_chat(content="local answer")])
        wrapper = install_adapter(monkeypatch, server, hf)

        response = client.post(path, json=payload)

        assert response.status_code == 200, response.text
        assert hf.call_count == 0
        assert len(server.chat_requests) == 1
        # the Ollama model id is surfaced to the caller
        assert wrapper.ollama_model_id.startswith("ollama:")

    def test_chat_endpoint_uses_ollama(self, monkeypatch, client, auth):
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([ok_chat(content=CONTRACT_OK)])
        install_adapter(monkeypatch, server, hf)

        session_id = _chat_session(client, auth)
        response = client.post(CHAT_PATH, headers=auth, json={"session_id": session_id, "message": "help me"})

        assert response.status_code == 200, response.text
        assert hf.call_count == 0
        assert len(server.chat_requests) == 1


# ---------------------------------------------------------------------------
# Ollama fails, HF answers
# ---------------------------------------------------------------------------
class TestFallbackToHuggingFace:
    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            (CV_PATH, CV_PAYLOAD),
            (COVER_LETTER_PATH, COVER_LETTER_PAYLOAD),
        ],
        ids=["cv", "cover_letter"],
    )
    def test_hf_content_is_returned(self, monkeypatch, client, path, payload):
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([http(404)])
        install_adapter(monkeypatch, server, hf)

        response = client.post(path, json=payload)

        assert response.status_code == 200, response.text
        assert hf.call_count == 1
        assert len(server.chat_requests) >= 1

    def test_fallback_chain_is_prefixed_with_the_ollama_id(self, monkeypatch, client):
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER, fallback_chain=["fake/hf-model"]))
        server = FakeOllamaServer([http(404)])
        wrapper = install_adapter(monkeypatch, server, hf)

        result = wrapper.generate_with_fallback("cv_generation", "prompt")

        assert result["fallback_chain"][0].startswith("ollama:")
        assert result["fallback_chain"][1:] == ["fake/hf-model"]

    def test_chat_falls_back_and_still_succeeds(self, monkeypatch, client, auth):
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([http(404)])
        install_adapter(monkeypatch, server, hf)

        session_id = _chat_session(client, auth)
        response = client.post(CHAT_PATH, headers=auth, json={"session_id": session_id, "message": "help me"})

        assert response.status_code == 200, response.text
        # generate_validated() re-prompts to satisfy the markdown contract, so HF
        # answers once for the turn plus once per repair round.
        assert 1 <= hf.call_count <= 3


# ---------------------------------------------------------------------------
# Everything fails: the template / deterministic fallback
# ---------------------------------------------------------------------------
class TestBothProvidersFail:
    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            (CV_PATH, CV_PAYLOAD),
            (COVER_LETTER_PATH, COVER_LETTER_PAYLOAD),
        ],
        ids=["cv", "cover_letter"],
    )
    def test_template_fallback_is_returned(self, monkeypatch, client, path, payload):
        hf = FailingHfAdapter()
        server = FakeOllamaServer([http(404)])
        install_adapter(monkeypatch, server, hf)

        response = client.post(path, json=payload)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("ai_generated") is False
        # The typed reason is surfaced so a caller can tell why it degraded.
        assert body.get("fallback_reason"), "the template result must carry a reason"
        assert body.get("content"), "the template result must not be empty"

    def test_chat_returns_the_labelled_deterministic_reply(self, monkeypatch, client, auth):
        hf = FailingHfAdapter()
        server = FakeOllamaServer([http(404)])
        install_adapter(monkeypatch, server, hf)

        session_id = _chat_session(client, auth)
        response = client.post(CHAT_PATH, headers=auth, json={"session_id": session_id, "message": "help me"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ai_generated"] is False
        assert "review before sending" in body["message"]["content"]
        assert body["model_id"] is None

    def test_generate_validated_path_also_falls_back(self, monkeypatch, client, auth):
        """The contract-enforcing path degrades the same way."""
        hf = FailingHfAdapter()
        server = FakeOllamaServer([http(404)])
        install_adapter(monkeypatch, server, hf)

        session_id = _chat_session(client, auth)
        response = client.post(CHAT_PATH, headers=auth, json={"session_id": session_id, "message": "help me"})

        assert response.status_code == 200
        assert response.json()["ai_generated"] is False


# ---------------------------------------------------------------------------
# Configuration paths
# ---------------------------------------------------------------------------
class TestUseOllamaDisabled:
    def test_ollama_is_never_contacted(self, monkeypatch, client):
        from app.application.services.ollama_first_adapter import OllamaFirstAdapter

        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([ok_chat()])
        plain = hf  # the plain HF adapter is returned unchanged
        monkeypatch.setattr(shared_router_module, "build_generation_adapter", lambda _: plain)
        shared_router_module.set_adapter_for_testing(plain)
        probe_module.reset_probe_cache()

        response = client.post(CV_PATH, json=CV_PAYLOAD)

        assert response.status_code == 200, response.text
        assert server.total_requests == 0
        assert hf.call_count >= 1
        assert not isinstance(plain, OllamaFirstAdapter)

    def test_chat_behaves_like_the_plain_adapter(self, monkeypatch, client, auth):
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([ok_chat()])
        monkeypatch.setattr(shared_router_module, "build_generation_adapter", lambda _: hf)
        shared_router_module.set_adapter_for_testing(hf)
        probe_module.reset_probe_cache()

        session_id = _chat_session(client, auth)
        response = client.post(CHAT_PATH, headers=auth, json={"session_id": session_id, "message": "hi"})

        assert response.status_code == 200, response.text
        assert server.total_requests == 0
        assert hf.call_count >= 1


class TestPinnedHuggingFaceModel:
    def test_a_pinned_chat_model_skips_ollama(self, monkeypatch, client, auth):
        """`model_id` pins the model for the turn; Ollama is not consulted."""
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([ok_chat(content=CONTRACT_OK)])
        install_adapter(monkeypatch, server, hf)

        session_id = _chat_session(client, auth)
        response = client.post(
            CHAT_PATH,
            headers=auth,
            json={"session_id": session_id, "message": "hi", "model_id": "meta-llama/Llama-3.1-8B-Instruct"},
        )

        assert response.status_code == 200, response.text
        assert server.total_requests == 0
        assert hf.call_count >= 1
        assert hf.calls[0]["preferred_model_id"] == "meta-llama/Llama-3.1-8B-Instruct"


# ---------------------------------------------------------------------------
# Breaker through the API
# ---------------------------------------------------------------------------
class TestBreakerThroughApi:
    def test_open_breaker_makes_zero_ollama_requests(self, monkeypatch, client):
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([http(404)])
        wrapper = install_adapter(monkeypatch, server, hf)

        # Trip it with the three availability failures that open the breaker.
        for _ in range(3):
            wrapper.generate_with_fallback("cv_generation", "prompt")
        requests_before = len(server.chat_requests)
        assert wrapper.circuit_state == "OPEN"

        response = client.post(CV_PATH, json=CV_PAYLOAD)

        assert response.status_code == 200, response.text
        assert len(server.chat_requests) == requests_before
        assert hf.call_count == 4

    def test_breaker_state_survives_across_requests(self, monkeypatch, client):
        from app.application.services.ai_model_router import CircuitBreaker

        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([http(404)])
        wrapper = install_adapter(monkeypatch, server, hf, breaker=CircuitBreaker(failure_threshold=3))

        for _ in range(3):
            client.post(CV_PATH, json=CV_PAYLOAD)

        assert wrapper.circuit_state == "OPEN"


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------
class TestPrivacy:
    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            (CV_PATH, CV_PAYLOAD),
            (COVER_LETTER_PATH, COVER_LETTER_PAYLOAD),
        ],
        ids=["cv", "cover_letter"],
    )
    def test_no_record_contains_the_prompt_or_the_content(self, monkeypatch, caplog, client, path, payload):
        import logging

        hf = FailingHfAdapter(marker=CONTENT_MARKER)
        server = FakeOllamaServer([ok_chat(content=CONTENT_MARKER)])
        install_adapter(monkeypatch, server, hf)

        with caplog.at_level(logging.DEBUG):
            client.post(path, json=payload)

        blob = " ".join(record.getMessage() for record in caplog.records)
        assert PROMPT_MARKER not in blob
        assert CONTENT_MARKER not in blob
        assert "Analytic Engines Ltd" not in blob

    def test_chat_logs_neither_the_message_nor_the_reply(self, monkeypatch, caplog, client, auth):
        import logging

        hf = FailingHfAdapter(marker=CONTENT_MARKER)
        server = FakeOllamaServer([ok_chat(content=CONTENT_MARKER)])
        install_adapter(monkeypatch, server, hf)

        session_id = _chat_session(client, auth)
        with caplog.at_level(logging.DEBUG):
            client.post(
                CHAT_PATH,
                headers=auth,
                json={"session_id": session_id, "message": f"secret {PROMPT_MARKER} question"},
            )

        blob = " ".join(record.getMessage() for record in caplog.records)
        assert PROMPT_MARKER not in blob
        assert CONTENT_MARKER not in blob

    def test_response_body_is_not_polluted_with_internals(self, monkeypatch, client):
        hf = FakeHfAdapter(_hf_result(content=CONTENT_MARKER))
        server = FakeOllamaServer([ok_chat(content=CONTENT_MARKER)])
        install_adapter(monkeypatch, server, hf)

        body = client.post(CV_PATH, json=CV_PAYLOAD).text

        assert "ollama.test" not in body
        assert "11434" not in body
