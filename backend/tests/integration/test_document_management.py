from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_document_persistence_and_export(auth_headers):
    payload = {
        "user_id": "user-document-layer",
        "document_type": "cv",
        "title": "Senior Analyst CV",
        "template_id": "professional",
        "content": "John Doe\nData Analyst\nPython and SQL",
    }

    headers = auth_headers("user-document-layer")
    create_response = client.post("/api/v1/documents", json=payload, headers=headers)
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["title"] == "Senior Analyst CV"
    assert created["document_type"] == "cv"

    document_id = created["id"]
    fetch_response = client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert fetch_response.status_code == 200
    assert fetch_response.json()["template_id"] == "professional"

    export_response = client.get(f"/api/v1/documents/{document_id}/export?format=html", headers=headers)
    assert export_response.status_code == 200
    assert "John Doe" in export_response.text
    assert "Data Analyst" in export_response.text

    list_response = client.get("/api/v1/documents", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()["count"] >= 1

    update_response = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"title": "Updated Senior Analyst CV", "template_id": "modern"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated Senior Analyst CV"
    assert update_response.json()["template_id"] == "modern"

    pdf_response = client.get(f"/api/v1/documents/{document_id}/export?format=pdf", headers=headers)
    assert pdf_response.status_code == 200
    assert pdf_response.content.startswith(b"%PDF")

    docx_response = client.get(f"/api/v1/documents/{document_id}/export?format=docx", headers=headers)
    assert docx_response.status_code == 200
    assert docx_response.content.startswith(b"PK")


def test_document_versioning_lifecycle(auth_headers):
    headers = auth_headers("user-versioning")
    original_content = "John Doe\nVersion one content"
    create_response = client.post(
        "/api/v1/documents",
        json={
            "user_id": "user-versioning",
            "document_type": "cv",
            "title": "Versioned CV",
            "template_id": "professional",
            "content": original_content,
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    document_id = create_response.json()["id"]
    assert create_response.json()["version"] == 1

    # Metadata-only edit does NOT create a new version.
    patch_meta = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"title": "Renamed CV"},
        headers=headers,
    )
    assert patch_meta.status_code == 200
    assert patch_meta.json()["version"] == 1

    # Clients cannot set version fields directly.
    patch_sneaky = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"content": "Version two content", "version": 99},
        headers=headers,
    )
    assert patch_sneaky.status_code == 200
    assert patch_sneaky.json()["version"] == 2
    assert patch_sneaky.json()["content"] == "Version two content"

    # Version list: v1 snapshot + current v2, oldest first.
    versions_response = client.get(f"/api/v1/documents/{document_id}/versions", headers=headers)
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert versions["count"] == 2
    assert [item["version"] for item in versions["items"]] == [1, 2]
    assert versions["items"][0]["content"] == original_content

    # Fetch a single historical version.
    v1_response = client.get(f"/api/v1/documents/{document_id}/versions/1", headers=headers)
    assert v1_response.status_code == 200
    assert v1_response.json()["content"] == original_content

    missing_response = client.get(f"/api/v1/documents/{document_id}/versions/99", headers=headers)
    assert missing_response.status_code == 404

    # Restore v1 → becomes v3 carrying the old content; history keeps v2.
    restore_response = client.post(
        f"/api/v1/documents/{document_id}/versions/1/restore",
        headers=headers,
    )
    assert restore_response.status_code == 200
    restored = restore_response.json()
    assert restored["version"] == 3
    assert restored["content"] == original_content

    versions_after = client.get(f"/api/v1/documents/{document_id}/versions", headers=headers).json()
    assert versions_after["count"] == 3
    assert [item["version"] for item in versions_after["items"]] == [1, 2, 3]

    # Ownership: another user cannot read version history.
    other_headers = auth_headers("someone-else")
    denied = client.get(f"/api/v1/documents/{document_id}/versions", headers=other_headers)
    assert denied.status_code == 404
