from fastapi import APIRouter, Depends

from app.api.schemas import (
    COMMON_ERROR_RESPONSES,
    ApplicationPayload,
    ApplicationStatusPayload,
    ApplicationUpdatePayload,
)
from app.application.services.application_tracking import application_tracker
from app.core.errors import NotFoundError, ValidationError
from app.core.security.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/applications", tags=["applications"], responses=COMMON_ERROR_RESPONSES)


@router.get("")
def list_applications(current_user: dict = Depends(get_current_user)) -> dict:
    apps = application_tracker.list_for_user(current_user["sub"])
    return {"count": len(apps), "items": [app.to_dict() for app in apps]}


@router.post("")
def create_application(body: ApplicationPayload, current_user: dict = Depends(get_current_user)) -> dict:
    payload = body.model_dump(exclude_unset=True)
    if not payload.get("company") or not payload.get("position"):
        raise ValidationError("company and position are required.")
    allowed_fields = {"company", "position", "status", "job_url", "notes", "follow_up_date"}
    safe_payload = {key: value for key, value in payload.items() if key in allowed_fields}
    safe_payload["user_id"] = current_user["sub"]
    app = application_tracker.create(safe_payload)
    return app.to_dict()


def _owned_application(application_id: str, current_user: dict):
    """Return the caller's application; foreign / unknown ids both give 404."""
    application = application_tracker.get(application_id)
    if application is None or application.user_id != current_user["sub"]:
        raise NotFoundError("Application not found.")
    return application


@router.get("/{application_id}")
def get_application(application_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    return _owned_application(application_id, current_user).to_dict()


@router.patch("/{application_id}")
def update_application(
    application_id: str,
    body: ApplicationUpdatePayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Edit notes, follow-up date, job URL, company, position or status.

    Only the fields present in the body change; ``null`` clears ``notes``,
    ``job_url`` and ``follow_up_date``. Ownership fields cannot be changed.
    """
    _owned_application(application_id, current_user)
    changes = body.model_dump(exclude_unset=True)
    try:
        updated = application_tracker.update(application_id, changes)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    except KeyError as exc:
        raise NotFoundError("Application not found.") from exc
    return updated.to_dict()


@router.patch("/{application_id}/status")
def update_application_status(
    application_id: str,
    body: ApplicationStatusPayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    payload = body.model_dump(exclude_unset=True)
    application = application_tracker.get(application_id)
    if application is None or application.user_id != current_user["sub"]:
        raise NotFoundError("Application not found.")
    status = payload.get("status")
    if not status:
        raise ValidationError("status is required.")
    try:
        app = application_tracker.update_status(application_id, status)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return app.to_dict()


@router.delete("/{application_id}")
def delete_application(application_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete one owned application. Foreign applications return 404."""
    application = application_tracker.get(application_id)
    if application is None or application.user_id != current_user["sub"]:
        raise NotFoundError("Application not found.")
    deleted = application_tracker.delete(application_id)
    if not deleted:
        raise NotFoundError("Application not found.")
    return {"deleted": True, "application_id": application_id}
