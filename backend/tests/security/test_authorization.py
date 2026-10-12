from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_user_data_routes_require_bearer_authentication() -> None:
    assert client.get("/api/v1/applications").status_code == 401
    assert client.get("/api/v1/documents").status_code == 401
    assert client.get("/api/v1/profiles/user-1").status_code == 401


def test_profile_identity_comes_from_token_and_other_profiles_are_hidden(auth_headers) -> None:
    response = client.post(
        "/api/v1/profiles",
        json={"user_id": "victim-user", "email": "spoofed@example.test", "full_name": "Alice"},
        headers=auth_headers("alice-user"),
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == "alice-user"
    assert response.json()["email"] == "alice-user@example.test"
    assert client.get("/api/v1/profiles/victim-user", headers=auth_headers("alice-user")).status_code == 404


def test_applications_are_scoped_to_token_subject(auth_headers) -> None:
    create_response = client.post(
        "/api/v1/applications",
        json={"user_id": "victim-user", "company": "Example", "position": "Engineer"},
        headers=auth_headers("alice-app-user"),
    )

    assert create_response.status_code == 200
    assert create_response.json()["user_id"] == "alice-app-user"
    application_id = create_response.json()["application_id"]

    bob_list = client.get("/api/v1/applications", headers=auth_headers("bob-app-user"))
    assert bob_list.status_code == 200
    assert bob_list.json()["items"] == []

    forbidden_update = client.patch(
        f"/api/v1/applications/{application_id}/status",
        json={"status": "interview"},
        headers=auth_headers("bob-app-user"),
    )
    assert forbidden_update.status_code == 404


def test_documents_are_scoped_to_token_subject(auth_headers) -> None:
    create_response = client.post(
        "/api/v1/documents",
        json={
            "user_id": "victim-user",
            "title": "Alice CV",
            "document_type": "cv",
            "content": "Private resume content",
        },
        headers=auth_headers("alice-doc-user"),
    )

    assert create_response.status_code == 200
    assert create_response.json()["user_id"] == "alice-doc-user"
    document_id = create_response.json()["id"]

    bob_list = client.get("/api/v1/documents", headers=auth_headers("bob-doc-user"))
    assert bob_list.status_code == 200
    assert bob_list.json()["items"] == []

    assert client.get(f"/api/v1/documents/{document_id}", headers=auth_headers("bob-doc-user")).status_code == 404
    assert (
        client.patch(
            f"/api/v1/documents/{document_id}",
            json={"title": "Stolen", "user_id": "bob-doc-user"},
            headers=auth_headers("bob-doc-user"),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/documents/{document_id}/export?format=text",
            headers=auth_headers("bob-doc-user"),
        ).status_code
        == 404
    )

    owner_update = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"title": "Updated Alice CV", "user_id": "bob-doc-user"},
        headers=auth_headers("alice-doc-user"),
    )
    assert owner_update.status_code == 200
    assert owner_update.json()["title"] == "Updated Alice CV"
    assert owner_update.json()["user_id"] == "alice-doc-user"
