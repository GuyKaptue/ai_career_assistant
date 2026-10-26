"""Template-aware rendering: samples (png/pdf/docx/html) and export follow the template design."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.templates.template_registry import TemplateRegistry
from app.infrastructure.document_export.previews import sample_content
from app.infrastructure.document_export.styled import parse_content, render_styled_html, theme_for
from app.main import app

client = TestClient(app)
ALL = [
    (t.id, t.document_type) for t in TemplateRegistry().list_templates() if t.document_type in ("cv", "cover_letter")
]


@pytest.mark.parametrize(("tid", "kind"), ALL)
def test_every_template_has_png_pdf_docx_html_samples(tid, kind):
    magic = {"png": b"\x89PNG", "pdf": b"%PDF", "docx": b"PK", "html": b"<!DOCTYPE"}
    for fmt, head in magic.items():
        r = client.get(f"/api/v1/templates/{tid}/sample", params={"document_type": kind, "format": fmt})
        assert r.status_code == 200, (tid, fmt, r.text[:200])
        assert r.content.startswith(head)


def test_designs_differ_between_templates():
    a = client.get("/api/v1/templates/professional/sample", params={"format": "png"}).content
    b = client.get("/api/v1/templates/modern/sample", params={"format": "png"}).content
    assert a != b
    from PIL import Image

    assert Image.open(io.BytesIO(a)).size[0] == 600


def test_sample_validation_errors():
    assert client.get("/api/v1/templates/nope/sample").status_code == 400
    assert client.get("/api/v1/templates/professional/sample", params={"format": "gif"}).status_code == 400
    assert client.get("/api/v1/templates/professional/sample", params={"locale": "xx"}).status_code == 400


def test_parse_cv_sections():
    p = parse_content(sample_content("cv", "en"), "cv")
    assert p.name == "Alex Example" and p.subtitle
    assert [s.heading for s in p.sections] == ["Professional Experience", "Education", "Skills"] or len(p.sections) >= 3


def test_html_escapes_user_text():
    html = render_styled_html("t", "<script>x</script>\n\nRole", "cv", theme_for("modern", "blue"))
    assert "<script>x</script>" not in html


def test_export_uses_template_design(auth_headers):
    h = auth_headers("design-user")
    created = client.post(
        "/api/v1/documents",
        json={"title": "CV", "document_type": "cv", "template_id": "modern", "content": sample_content("cv", "en")},
        headers=h,
    )
    assert created.status_code in (200, 201), created.text
    doc_id = created.json()["id"]
    html = client.get(f"/api/v1/documents/{doc_id}/export", params={"format": "html"}, headers=h).text
    assert "#334155" in html  # modern -> slate accent
    pdf = client.get(f"/api/v1/documents/{doc_id}/export", params={"format": "pdf"}, headers=h)
    assert pdf.content.startswith(b"%PDF")
    docx = client.get(f"/api/v1/documents/{doc_id}/export", params={"format": "docx"}, headers=h)
    assert docx.content.startswith(b"PK")
