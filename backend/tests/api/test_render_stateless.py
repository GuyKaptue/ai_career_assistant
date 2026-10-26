"""Stateless render: file out, nothing stored; safe filenames; template and theme validation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.application.services.document_store import document_store
from app.infrastructure.document_export.previews import sample_content
from app.main import app

client = TestClient(app)
BODY = {"content": sample_content("cv", "en"), "document_type": "cv", "template_id": "sidebar-right-blue"}


def test_render_returns_files_without_auth_and_stores_nothing(auth_headers):
    before = len(document_store.list_for_user("render-user"))
    for fmt, head in (("pdf", b"%PDF"), ("docx", b"PK"), ("html", b"<!DOCTYPE")):
        r = client.post(
            "/api/v1/documents/render", json={**BODY, "format": fmt, "theme_id": "navy_exec", "country": "de"}
        )
        assert r.status_code == 200 and r.content.startswith(head), fmt
    assert len(document_store.list_for_user("render-user")) == before


def test_render_respects_sidebar_and_design():
    left = client.post("/api/v1/documents/render", json={**BODY, "format": "html", "sidebar": "left"}).text
    right = client.post("/api/v1/documents/render", json={**BODY, "format": "html"}).text
    assert left != right and "grid-column:2" in right


def test_render_rejects_bad_input():
    assert client.post("/api/v1/documents/render", json={**BODY, "template_id": "nope"}).status_code == 400
    assert client.post("/api/v1/documents/render", json={**BODY, "theme_id": "x"}).status_code == 400
    assert client.post("/api/v1/documents/render", json={**BODY, "sidebar": "top"}).status_code == 422
    assert client.post("/api/v1/documents/render", json={**BODY, "content": ""}).status_code == 422
    assert client.post("/api/v1/documents/render", json={**BODY, "format": "exe"}).status_code == 422


def test_filename_is_sanitised():
    r = client.post("/api/v1/documents/render", json={**BODY, "title": 'a"b/../c\r\nX: y', "format": "pdf"})
    disp = r.headers["content-disposition"]
    assert "\r" not in disp and "\n" not in disp and '"b' not in disp and ".." not in disp.split("filename=")[1]


def test_user_template_needs_token(auth_headers):
    from app.application.services.template_service import get_template_service

    tpl, _ = get_template_service().create_template("render-user", "cv", "Mine", base_template_id="modern")
    body = {**BODY, "template_id": tpl.id, "format": "pdf"}
    assert client.post("/api/v1/documents/render", json=body).status_code == 400
    ok = client.post("/api/v1/documents/render", json=body, headers=auth_headers("render-user"))
    assert ok.status_code == 200 and ok.content.startswith(b"%PDF")


def test_render_default_template_when_template_id_missing_or_empty():
    from app.infrastructure.document_export.previews import sample_content

    for document_type in ("cv", "cover_letter"):
        content = sample_content(document_type, "en")
        for template_id in (None, ""):
            for fmt, head in (("pdf", b"%PDF"), ("docx", b"PK"), ("html", b"<!DOCTYPE")):
                body = {"content": content, "document_type": document_type, "format": fmt}
                if template_id is not None:
                    body["template_id"] = template_id
                r = client.post("/api/v1/documents/render", json=body)
                assert r.status_code == 200, (document_type, template_id, fmt, r.status_code, r.text[:200])
                if fmt == "pdf":
                    assert r.content.startswith(b"%PDF")
                elif fmt == "docx":
                    import io
                    import zipfile

                    z = zipfile.ZipFile(io.BytesIO(r.content))
                    assert "word/document.xml" in z.namelist()
                else:
                    assert r.content.startswith(b"<!DOCTYPE") or b"<!DOCTYPE" in r.content[:64]


def test_render_unknown_template_id_still_400():
    from app.infrastructure.document_export.previews import sample_content

    body = {"content": sample_content("cv", "en"), "document_type": "cv", "template_id": "nope", "format": "pdf"}
    assert client.post("/api/v1/documents/render", json=body).status_code == 400
