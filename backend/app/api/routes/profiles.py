from fastapi import APIRouter, Depends

from app.api.schemas import COMMON_ERROR_RESPONSES, ProfilePayload
from app.application.services.application_tracking import application_tracker
from app.application.services.document_store import document_store
from app.application.services.profile_service import profile_store
from app.core.errors import NotFoundError, ValidationError
from app.core.security.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"], responses=COMMON_ERROR_RESPONSES)


@router.post("")
def create_profile(body: ProfilePayload, current_user: dict = Depends(get_current_user)) -> dict:
    payload = body.model_dump(exclude_unset=True)
    email = current_user.get("email") or payload.get("email")
    if not email:
        raise ValidationError("email is required.")
    profile_payload = {**payload, "user_id": current_user["sub"], "email": email}
    profile = profile_store.create(profile_payload)
    return profile.to_dict()


@router.get("/{user_id}")
def get_profile(user_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    if user_id != current_user["sub"]:
        raise NotFoundError("Profile not found.")
    profile = profile_store.get(user_id)
    if profile is None:
        raise NotFoundError("Profile not found.")
    return profile.to_dict()


@router.patch("/{user_id}")
def update_profile(user_id: str, body: ProfilePayload, current_user: dict = Depends(get_current_user)) -> dict:
    if user_id != current_user["sub"]:
        raise NotFoundError("Profile not found.")
    payload = body.model_dump(exclude_unset=True)
    profile = profile_store.get(user_id)
    if profile is None:
        raise NotFoundError("Profile not found.")
    allowed_fields = {"full_name", "target_role", "location", "summary"}
    safe_payload = {key: value for key, value in payload.items() if key in allowed_fields}
    updated = profile_store.update(user_id, safe_payload)
    return updated.to_dict()


@router.delete("/me")
def delete_my_data(current_user: dict = Depends(get_current_user)) -> dict:
    """GDPR right to erasure: delete the caller's profile, documents,
    and applications in one operation. The Supabase Auth account itself
    is managed by the Auth service; this endpoint removes the app-layer
    data only (RLS + `on delete cascade` handle the rest)."""
    user_id = current_user["sub"]

    documents = document_store.list_for_user(user_id)
    applications = application_tracker.list_for_user(user_id)

    deleted_documents = 0
    for document in documents:
        if document_store.delete(document.id):
            deleted_documents += 1

    deleted_applications = 0
    for application in applications:
        if application_tracker.delete(application.application_id):
            deleted_applications += 1

    try:
        profile_store.delete(user_id)
    except (KeyError, NotImplementedError):
        # Profile deletion is optional — Auth owns the identity row.
        pass

    return {
        "deleted": True,
        "user_id": user_id,
        "deleted_documents": deleted_documents,
        "deleted_applications": deleted_applications,
    }
