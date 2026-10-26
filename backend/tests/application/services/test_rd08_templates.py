"""RD-08 step 5: template persistence, defaults, per-job overrides, RAG indexing (in-memory stores)."""

import httpx
import pytest

from app.application.services.candidate_analysis import CandidateAnalysis
from app.application.services.document_retrieval import DocumentRetrievalService
from app.application.services.project_store import ProjectStore
from app.application.services.tailoring_pipeline import JobTarget, write_cover_letter
from app.application.services.template_service import (
    DefaultsStore,
    TemplateService,
    UserTemplateNotFound,
    UserTemplateStore,
)
from app.core.errors import ValidationError
from app.domain.templates.template_registry import TemplateRegistry
from app.domain.users.user_core import build_user_core
from app.infrastructure.knowledge.semantic_store import SemanticEmbeddingStore


class Emb:
    def embed_one(self, text):
        return [1.0, 0.0] if "tech" in text.lower() else [0.0, 1.0]


@pytest.fixture
def parts(monkeypatch):
    store = SemanticEmbeddingStore()
    retrieval = DocumentRetrievalService(store=store, embeddings=Emb())  # type: ignore[arg-type]
    projects = ProjectStore()
    svc = TemplateService(
        registry=TemplateRegistry(),
        templates=UserTemplateStore(),
        defaults=DefaultsStore(),
        projects=projects,
        indexer=retrieval,
    )
    return svc, projects, store, retrieval


def test_create_indexes_template_into_real_store_user_scoped(parts):
    svc, _, store, retrieval = parts
    t, indexed = svc.create_template(
        "u1",
        "cover_letter",
        "My tech letter",
        base_template_id="brief-letter",
        structure_type="technical",
        tone="precise",
        language="en",
        content={"sections": ["intro", "impact"]},
    )
    assert indexed and t.user_id == "u1"
    hits = retrieval.retrieve("u1", "tech letter", min_similarity=0.5)
    assert [h["document_type"] for h in hits] == ["template"] and hits[0]["document_id"] == t.id
    assert retrieval.retrieve("u2", "tech letter", min_similarity=0.0) == []  # other user sees nothing


def test_indexing_failure_is_soft(parts):
    svc, _, _, retrieval = parts

    def boom(*a, **k):
        raise RuntimeError("embedding down")

    retrieval.index_document = boom  # type: ignore[method-assign]
    t, indexed = svc.create_template("u1", "cv", "Mine")
    assert not indexed and svc.list_templates("u1") == [t]


def test_validation(parts):
    svc, *_ = parts
    for kwargs in (
        {"kind": "poster", "name": "x"},
        {"kind": "cv", "name": " "},
        {"kind": "cv", "name": "x", "language": "xx"},
        {"kind": "cv", "name": "x", "base_template_id": "nope"},
        {"kind": "cv", "name": "x", "content": {"a": "z" * 25000}},
    ):
        with pytest.raises(ValueError):
            svc.create_template("u1", **kwargs)


def test_update_reindexes_without_stale_chunks_and_enforces_ownership(parts):
    svc, _, store, _ = parts
    t, _ = svc.create_template("u1", "cv", "Long", content={"body": "tech " * 600})
    first = len([k for k in store._entries if k[0] == "template"])
    assert first > 1
    svc.update_template("u1", t.id, {"content": {"body": "short"}})
    assert len([k for k in store._entries if k[0] == "template"]) == 1
    with pytest.raises(UserTemplateNotFound):
        svc.update_template("u2", t.id, {"name": "stolen"})
    with pytest.raises(UserTemplateNotFound):
        svc.delete_template("u2", t.id)


def test_default_seeds_new_projects_and_never_mutates_existing(parts):
    svc, projects, *_ = parts
    mine, _ = svc.create_template("u1", "cv", "Mine")
    old = projects.create("u1", "Old job")
    svc.set_default("u1", "cv", mine.id)
    seeded_cv, seeded_letter = svc.seed_for_new_project("u1")
    new = projects.create("u1", "New job", template_id=seeded_cv, cover_letter_template_id=seeded_letter)
    assert new.template_id == mine.id and projects.get(old.id).template_id == "professional"


def test_override_applies_to_one_project_and_never_changes_default(parts):
    svc, projects, *_ = parts
    mine, _ = svc.create_template("u1", "cv", "Mine")
    svc.set_default("u1", "cv", "modern")
    a, b = projects.create("u1", "A"), projects.create("u1", "B")
    svc.set_project_override("u1", a.id, "cv", mine.id)
    assert svc.resolve("u1", "cv", a.id) == (mine.id, "project")
    assert svc.resolve("u1", "cv", b.id)[0] == "professional"  # B keeps its own seeded value
    assert svc.default_for("u1", "cv") == "modern"  # default untouched
    assert svc.resolve("u1", "cv") == ("modern", "default")


def test_cannot_select_foreign_or_unknown_templates(parts):
    svc, projects, *_ = parts
    theirs, _ = svc.create_template("u2", "cv", "Theirs")
    p = projects.create("u1", "A")
    with pytest.raises(ValueError):
        svc.set_default("u1", "cv", theirs.id)
    with pytest.raises(ValueError):
        svc.set_project_override("u1", p.id, "cv", theirs.id)
    with pytest.raises(ValueError):
        projects.update(p.id, {"template_id": theirs.id})  # ProjectStore uses the same ownership rule
    with pytest.raises(KeyError):
        svc.set_project_override("u2", p.id, "cv", "modern")  # not their project


def test_project_store_accepts_own_user_template(parts):
    svc, projects, *_ = parts
    mine, _ = svc.create_template("u1", "cover_letter", "Mine")
    p = projects.create("u1", "A", cover_letter_template_id=mine.id)
    assert p.cover_letter_template_id == mine.id


def test_delete_clears_index_default_and_project_references(parts):
    svc, projects, store, _ = parts
    mine, _ = svc.create_template("u1", "cv", "Mine")
    svc.set_default("u1", "cv", mine.id)
    p = projects.create("u1", "A", template_id=mine.id)
    svc.delete_template("u1", mine.id)
    assert not [k for k in store._entries if k[0] == "template"]
    assert svc.default_for("u1", "cv") == "professional" and projects.get(p.id).template_id == "professional"


def test_context_and_cover_letter_style_for_builtin_and_user_templates(parts):
    svc, *_ = parts
    assert svc.cover_letter_style("u1", "technical-letter") == (4, "structured, emphasizing technical scope and impact")
    mine, _ = svc.create_template("u1", "cover_letter", "Mine", structure_type="brief", tone="warm")
    ctx = svc.context_for("u1", "cover_letter", mine.id)
    assert ctx.source == "user" and svc.cover_letter_style("u1", mine.id) == (3, "warm")
    with pytest.raises(UserTemplateNotFound):
        svc.context_for("u1", "cv", "nope")


def test_user_template_style_drives_the_letter_prompt(parts):
    svc, *_ = parts
    mine, _ = svc.create_template("u1", "cover_letter", "Mine", structure_type="creative")

    class Gen:
        def __init__(self):
            self.system = ""

        def generate_with_fallback(self, task, prompt, **kw):
            self.system = kw["system_prompt"]
            return {"content": "{}", "model_id": "m"}

    gen = Gen()
    core = build_user_core(user_id="u1", cv_text="Python", preferences={"cover_letter_template_id": mine.id})
    write_cover_letter(
        core, CandidateAnalysis(skills=["Python"]), JobTarget("Dev"), gen, style=svc.cover_letter_style("u1", mine.id)
    )
    assert "Exactly 4 paragraphs" in gen.system and "narrative" in gen.system


def test_semantic_store_remote_delete_is_scoped_and_fail_soft(monkeypatch):
    import dataclasses

    from app.core.config import settings
    from app.infrastructure.knowledge import semantic_store as semantic_store_module

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, dict(request.url.params)))
        return httpx.Response(500)

    monkeypatch.setattr(
        semantic_store_module,
        "settings",
        dataclasses.replace(settings, supabase_url="https://x.supabase.test", supabase_service_role_key="k"),
    )
    store = SemanticEmbeddingStore()
    monkeypatch.setattr(
        store,
        "_client",
        lambda: httpx.Client(base_url="https://x.supabase.test", transport=httpx.MockTransport(handler)),
    )
    assert store.delete("template", "t1:chunk-", "u1") == 0
    assert seen[0][0] == "DELETE" and seen[0][1]["user_id"] == "eq.u1" and seen[0][1]["entity_type"] == "eq.template"


def test_retrieval_validation_still_rejects_unknown_types(parts):
    *_, retrieval = parts
    with pytest.raises(ValidationError):
        retrieval.index_document("u1", "poem", "d", "x")


def test_edge_cases_for_updates_defaults_and_resolution(parts):
    svc, projects, _, retrieval = parts
    t, _ = svc.create_template("u1", "cv", "Mine")
    with pytest.raises(ValueError):
        svc.update_template("u1", t.id, {"bogus": 1})
    with pytest.raises(ValueError):
        svc.set_default("u1", "poster", None)
    svc.set_default("u1", "cv", t.id)
    svc.set_default("u1", "cv", None)
    assert svc.default_for("u1", "cv") == "professional"
    p = projects.create("u2", "Theirs")
    assert svc.resolve("u1", "cv", p.id) == ("professional", "builtin")  # someone else's project is ignored
    svc.update_template("u1", t.id, {"name": "  Renamed  "})
    assert svc.list_templates("u1", "cv")[0].name == "Renamed" and svc.list_templates("u1", "cover_letter") == []

    def boom(*a, **k):
        raise RuntimeError("down")

    retrieval.remove_document = boom  # type: ignore[method-assign]
    svc.delete_template("u1", t.id)  # unindex failure is soft
    assert svc.list_templates("u1") == []
