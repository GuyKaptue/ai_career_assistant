from fastapi.testclient import TestClient

from app.infrastructure.document_export.cover_letter_docx import (
    from_document,
    render_cover_letter_to_docx,
)
from app.main import app

client = TestClient(app)


def _german_fixture() -> dict:
    return {
        "document_type": "cover_letter",
        "template_id": "formal-german-din5008",
        "sender_name": "Max Mustermann",
        "sender_street": "Musterstr. 1",
        "sender_city": "12345 Berlin",
        "sender_phone": "030 123456",
        "sender_email": "max@example.test",
        "recipient_lines": ["Beispiel GmbH", "Personalabteilung", "10115 Berlin"],
        "company": "Beispiel GmbH",
        "target_role": "Data Scientist",
        "subject": "Bewerbung als Data Scientist (w/m/d) – Kennziffer: T-2026-75",
        "reference_no": "T-2026-75",
        "salutation": "Sehr geehrte Damen und Herren,",
        "body_paragraphs": [
            "Mit Begeisterung bewerbe ich mich auf die ausgeschriebene Position.",
            "Als Data Scientist mit Python- und SQL-Erfahrung passe ich gut ins Profil.",
        ],
        "closing": "Mit freundlichen Grüßen",
        "signature": "Max Mustermann",
        "letter_date": "2026-10-07",
        "locale": "de",
    }


def test_from_document_maps_structured_fields() -> None:
    data = from_document(_german_fixture())

    assert data.sender_name == "Max Mustermann"
    assert data.locale == "de"
    assert "T-2026-75" in data.subject
    assert len(data.body_paragraphs) == 2
    assert data.salutation.startswith("Sehr geehrte")


def test_from_document_falls_back_without_structured_keys() -> None:
    data = from_document({"name": "Jane", "company": "Acme", "target_role": "Analyst"})

    assert data.salutation == "Dear Hiring Manager,"
    assert "Analyst" in data.subject
    assert data.letter_date != ""


def test_render_cover_letter_docx_bytes_and_structure() -> None:
    from io import BytesIO

    from docx import Document

    payload = render_cover_letter_to_docx(_german_fixture())

    assert payload.startswith(b"PK")
    doc = Document(BytesIO(payload))
    texts = [p.text for p in doc.paragraphs]
    joined = "\n".join(texts)
    assert "Max Mustermann" in joined
    assert "Beispiel GmbH" in joined
    assert "T-2026-75" in joined
    assert "Sehr geehrte Damen und Herren," in joined
    assert "Mit freundlichen Grüßen" in joined
    # Sender + rule + recipient + date + subject + salutation + 2 body + closing + sig.
    assert len([t for t in texts if t.strip()]) >= 9


def test_generate_endpoint_accepts_structured_cover_letter() -> None:
    response = client.post(
        "/api/v1/documents/cover-letter/generate",
        json={"name": "Jane", "company": "Acme", "target_role": "Analyst", "locale": "de"},
    )

    assert response.status_code == 200
    assert response.json()["ai_generated"] is False


def test_template_registry_lists_formal_german() -> None:
    response = client.get("/api/v1/templates", params={"document_type": "cover_letter"})

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert "formal-german-din5008" in ids
    assert "classic-letter" in ids
