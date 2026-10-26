"""Country profiles, 20 themes with AA contrast, two-column rendering."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.documents.country_profiles import apply_photo_policy, profile_for_country
from app.domain.templates.themes import THEMES, contrast_ratio, contrast_report, nearest_aa, resolve_theme
from app.infrastructure.document_export.previews import sample_content
from app.main import app

client = TestClient(app)


def test_twenty_themes_and_all_resolve_to_aa():
    assert len(THEMES) == 20
    for tid in THEMES:
        theme, _ = resolve_theme(tid)
        assert all(r["passes"] for r in contrast_report(theme)), tid


def test_spec_defect_slate_pro_is_fixed_with_warning():
    theme, warnings = resolve_theme("slate_pro")
    assert warnings and "section_title" in warnings[0]
    assert contrast_ratio(theme.section_title, theme.background) >= 4.5


def test_override_breaking_contrast_warns_and_suggests_safe_value():
    theme, warnings = resolve_theme("minimal_white", {"text": "#CCCCCC"})
    assert warnings and contrast_ratio(theme.text, theme.background) >= 4.5
    assert nearest_aa("#CCCCCC", "#FFFFFF") != "#CCCCCC"


def test_bad_override_values_rejected():
    with pytest.raises(ValueError):
        resolve_theme("minimal_white", {"accent": "blue"})
    with pytest.raises(ValueError):
        resolve_theme("minimal_white", {"font": "Comic Sans"})
    with pytest.raises(ValueError):
        resolve_theme("nope")


def test_single_column_forces_white_background():
    theme, _ = resolve_theme("graphite_tech", single_column=True)
    assert theme.background == "#FFFFFF"


@pytest.mark.parametrize(
    ("country", "layout", "photo"),
    [
        ("DE", "two_column", "optional"),
        ("FR", "two_column", "recommended"),
        ("US", "single_column", "forbidden"),
        ("GB", "single_column", "forbidden"),
        ("SE", "hybrid", "optional"),
        ("JP", "single_column", "forbidden"),
    ],
)
def test_country_profiles(country, layout, photo):
    p = profile_for_country(country)
    assert (p.layout, p.photo) == (layout, photo)


def test_belgium_depends_on_language():
    assert profile_for_country("BE", "fr").id == "FR"
    assert profile_for_country("BE", "nl").id == "NL_BE"


def test_photo_removed_with_caveat_where_forbidden():
    keep, caveat = apply_photo_policy(profile_for_country("US"), True)
    assert not keep and caveat
    keep, caveat = apply_photo_policy(profile_for_country("DE"), True)
    assert keep and not caveat


def test_endpoints():
    themes = client.get("/api/v1/themes").json()
    assert themes["count"] == 20 and "contrast" in themes["items"][0]
    de = client.get("/api/v1/country-profiles", params={"country": "de"}).json()
    assert de["cv_layout"] == "two_column" and de["section_labels"][0] == "Zusammenfassung"
    us = client.get("/api/v1/country-profiles", params={"country": "US", "has_photo": "true"}).json()
    assert us["caveats"] and us["paper_size"] == "Letter"


@pytest.mark.parametrize("tid", list(THEMES))
def test_two_column_samples_for_every_theme(tid):
    magic = {"png": b"\x89PNG", "pdf": b"%PDF", "docx": b"PK", "html": b"<!DOCTYPE"}
    for fmt, head in magic.items():
        r = client.get("/api/v1/templates/modern/sample", params={"format": fmt, "theme_id": tid, "country": "DE"})
        assert r.status_code == 200, (tid, fmt)
        assert r.content.startswith(head)


def test_country_changes_layout():
    de = client.get("/api/v1/templates/modern/sample", params={"theme_id": "navy_exec", "country": "DE"}).content
    us = client.get("/api/v1/templates/modern/sample", params={"theme_id": "navy_exec", "country": "US"}).content
    assert de != us
    from PIL import Image

    sidebar_px = Image.open(io.BytesIO(de)).convert("RGB").getpixel((10, 400))
    assert sidebar_px == (0x0B, 0x1F, 0x3A)  # navy sidebar in the DACH layout
    assert Image.open(io.BytesIO(us)).convert("RGB").getpixel((10, 400)) == (255, 255, 255)


def test_unknown_theme_rejected():
    assert client.get("/api/v1/templates/modern/sample", params={"theme_id": "x"}).status_code == 400


def test_export_with_theme_and_country(auth_headers):
    h = auth_headers("theme-user")
    doc = client.post(
        "/api/v1/documents",
        json={"title": "CV", "document_type": "cv", "template_id": "modern", "content": sample_content("cv", "de")},
        headers=h,
    ).json()
    url = f"/api/v1/documents/{doc['id']}/export"
    pdf = client.get(url, params={"format": "pdf", "theme_id": "forest_green", "country": "DE"}, headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(url, params={"format": "pdf", "theme_id": "bad"}, headers=h).status_code == 400
