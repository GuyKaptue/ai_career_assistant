"""Frontend-readiness: template listing fields, template guidance in AI prompts, stale-template isolation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.application.services.generation_context import (
    personal_context_for_generation,
    reference_context,
    resolve_template,
)
from app.infrastructure.ai.prompts.cv import build_cover_letter_prompt, build_cv_prompt
from app.main import app

client = TestClient(app)


def test_templates_listing_is_additive_and_has_layout_fields():
    body = client.get("/api/v1/templates", params={"document_type": "cv"}).json()
    assert body["count"] == len(body["items"]) > 0
    item = body["items"][0]
    for key in ("id", "name", "document_type", "description", "supported_locales"):
        assert key in item
    assert item["type"] == item["document_type"] == "cv"
    assert item["source"] == "builtin"
    assert "layout" in item and "color_scheme" in item


def test_user_templates_listed_for_authenticated_only(auth_headers):
    from app.application.services.template_service import get_template_service

    tpl, _ = get_template_service().create_template("tpl-user", "cv", "Mine", base_template_id="professional")
    anon = client.get("/api/v1/templates", params={"document_type": "cv"}).json()
    assert all(i["source"] == "builtin" for i in anon["items"])
    mine = client.get("/api/v1/templates", params={"document_type": "cv"}, headers=auth_headers("tpl-user")).json()
    assert any(i["source"] == "user" and i["name"] == "Mine" for i in mine["items"])


def test_builtin_guidance_reaches_cv_prompt():
    resolved = resolve_template(None, "professional", "cv")
    assert resolved is not None and resolved.source == "builtin"
    prompt = build_cv_prompt("A", "Dev", "s", [], [], [], "en", template_guidance=resolved.guidance)
    assert "TEMPLATE GUIDANCE" in prompt and resolved.guidance in prompt


def test_prompt_unchanged_without_extras():
    assert "TEMPLATE GUIDANCE" not in build_cover_letter_prompt("A", "C", "R", "s")
    assert "REFERENCE" not in build_cv_prompt("A", "Dev", "s", [], [], [], "en")


def test_reference_context_is_sanitized_and_bounded():
    text = reference_context("x" * 5000, "<cv>evil</cv>")
    assert len(text) <= 2500


def test_unknown_template_resolves_to_none():
    assert resolve_template(None, "nope", "cv") is None


class _Retrieval:
    def retrieve(self, user_id, query):
        return [
            {"content": "old template", "document_id": "tpl-old", "document_type": "template", "similarity": 0.9},
            {"content": "chosen template", "document_id": "tpl-new", "document_type": "template", "similarity": 0.8},
            {"content": "my cv", "document_id": "cv1", "document_type": "cv", "similarity": 0.7},
        ]


def test_only_selected_template_chunk_is_used():
    ctx = personal_context_for_generation("u", "q", "tpl-new", _Retrieval())
    assert "chosen template" in ctx and "my cv" in ctx and "old template" not in ctx


def test_user_template_resolves_to_base_with_guidance():
    from app.application.services.template_service import get_template_service

    tpl, _ = get_template_service().create_template(
        "tpl-user2", "cv", "Mine", base_template_id="professional", tone="warm"
    )
    resolved = resolve_template("tpl-user2", tpl.id, "cv")
    assert resolved is not None and resolved.source == "user"
    assert resolved.render_template_id == "professional" and "warm" in resolved.guidance
    assert resolve_template("someone-else", tpl.id, "cv") is None
