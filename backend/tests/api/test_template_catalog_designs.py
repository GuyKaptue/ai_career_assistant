"""More than 20 distinct designs; sidebar left/right; banner; every format renders."""

from __future__ import annotations

import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.domain.templates.template_registry import TemplateRegistry
from app.main import app

client = TestClient(app)
REG = TemplateRegistry()
CV = [t for t in REG.list_templates("cv")]
TWO_COL = [t for t in CV if t.metadata.get("columns") == 2]


def _png(tid, kind="cv", **params):
    r = client.get(f"/api/v1/templates/{tid}/sample", params={"document_type": kind, "format": "png", **params})
    assert r.status_code == 200, r.text[:200]
    return r.content


def test_catalog_has_more_than_twenty_cv_designs():
    assert len(CV) >= 30 and len(TWO_COL) == 18
    assert len(REG.list_templates("cover_letter")) == 10


def test_every_cv_and_letter_template_has_a_distinct_preview():
    hashes = {}
    for t in [*CV, *REG.list_templates("cover_letter")]:
        h = hashlib.sha256(_png(t.id, t.document_type)).hexdigest()
        assert h not in hashes, f"{t.id} looks identical to {hashes[h]}"
        hashes[h] = t.id


@pytest.mark.parametrize("tid", [t.id for t in TWO_COL])
def test_two_column_templates_render_all_formats(tid):
    magic = {"png": b"\x89PNG", "pdf": b"%PDF", "docx": b"PK", "html": b"<!DOCTYPE"}
    for fmt, head in magic.items():
        r = client.get(f"/api/v1/templates/{tid}/sample", params={"format": fmt})
        assert r.status_code == 200 and r.content.startswith(head), (tid, fmt)


def _px(png, x, y):
    return Image.open(io.BytesIO(png)).convert("RGB").getpixel((x, y))


def test_sidebar_side_follows_template_and_can_be_flipped():
    navy = (0x0B, 0x1F, 0x3A)
    left = _png("sidebar-left-navy")
    assert _px(left, 10, 500) == navy and _px(left, 590, 500) != navy
    right = _png("sidebar-left-navy", sidebar="right")
    assert _px(right, 590, 500) == navy and _px(right, 10, 500) != navy
    native_right = _png("sidebar-right-blue")
    assert _px(native_right, 590, 500) == (0x1D, 0x4E, 0xD8)


def test_sidebar_width_differs():
    narrow = _png("sidebar-left-narrow")
    assert _px(narrow, 160, 500) != _px(narrow, 100, 500)  # 25% sidebar ends at x=150
    wide = _png("sidebar-right-wide")
    assert _px(wide, 600 - 215, 500) == (0x4C, 0x1D, 0x95)  # 38% sidebar reaches x=372
    assert _px(wide, 600 - 230, 500) != (0x4C, 0x1D, 0x95)


def test_banner_template_has_full_width_band():
    png = _png("banner-left-ocean")
    assert _px(png, 590, 20) == _px(png, 10, 20) == (0x0E, 0xA5, 0xE9)


def test_invalid_sidebar_rejected():
    assert client.get("/api/v1/templates/sidebar-left-navy/sample", params={"sidebar": "top"}).status_code == 400


def test_listing_exposes_new_templates():
    items = client.get("/api/v1/templates", params={"document_type": "cv"}).json()["items"]
    ids = {i["id"] for i in items}
    assert {"sidebar-left-navy", "sidebar-right-blue", "banner-left-ocean"} <= ids


def test_export_honours_template_sidebar_and_override(auth_headers):
    h = auth_headers("catalog-user")
    doc = client.post(
        "/api/v1/documents",
        json={
            "title": "CV",
            "document_type": "cv",
            "template_id": "sidebar-right-blue",
            "content": "Alex Example\n\nEngineer\n\nEngineer\n\nSummary text.\n\nSkills\n- Python",
        },
        headers=h,
    ).json()
    url = f"/api/v1/documents/{doc['id']}/export"
    html_right = client.get(url, params={"format": "html"}, headers=h).text
    assert "grid-column:2" in html_right and "#1D4ED8" in html_right
    html_left = client.get(url, params={"format": "html", "sidebar": "left"}, headers=h).text
    assert html_left != html_right
    for fmt, head in (("pdf", b"%PDF"), ("docx", b"PK")):
        assert client.get(url, params={"format": fmt}, headers=h).content.startswith(head)
    assert client.get(url, params={"format": "pdf", "sidebar": "x"}, headers=h).status_code == 400


def test_all_theme_text_pairs_are_aa_in_templates():
    from app.domain.templates.themes import THEMES, contrast_report, resolve_theme

    for t in REG.list_templates("cv"):
        if t.metadata.get("theme_id"):
            theme, _ = resolve_theme(str(t.metadata["theme_id"]))
            assert all(r["passes"] for r in contrast_report(theme)), t.id
    assert len(THEMES) == 20


def test_listing_exposes_design_fields_for_the_ui():
    items = {i["id"]: i for i in client.get("/api/v1/templates", params={"document_type": "cv"}).json()["items"]}
    right = items["sidebar-right-blue"]
    assert (right["columns"], right["sidebar"], right["sidebar_pct"], right["theme_id"]) == (
        2,
        "right",
        32,
        "sky_light",
    )
    assert items["professional"]["columns"] == 1 and items["professional"]["sidebar"] is None
