"""Application projects: position + templates + match + apply."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.routes._uploads import read_limited
from app.api.routes.positions import extract_from_payload
from app.api.schemas import (
    COMMON_ERROR_RESPONSES,
    ApplyPayload,
    PositionAttachPayload,
    ProjectCreatePayload,
    ProjectFromJobPayload,
    ProjectMatchPayload,
    ProjectUpdatePayload,
)
from app.application.services import position_extraction
from app.application.services.apply_flow import apply_to_position
from app.application.services.ats_checker import check_resume_against_job
from app.application.services.document_store import document_store
from app.application.services.project_store import project_store
from app.application.services.semantic_matching import check_resume_semantic
from app.core.errors import NotFoundError, ValidationError
from app.core.security.dependencies import get_current_user
from app.domain.positions.models import Position
from app.domain.projects.models import Project

router = APIRouter(prefix="/api/v1/projects", tags=["projects"], responses=COMMON_ERROR_RESPONSES)


def _owned_project(project_id: str, current_user: dict) -> Project:
    """Foreign and unknown ids both answer 404 (no existence leak)."""
    project = project_store.get(project_id)
    if project is None or project.user_id != current_user["sub"]:
        raise NotFoundError("Project not found.")
    return project


def _default_name(position: dict[str, Any] | None) -> str:
    if position:
        parts = [part for part in (position.get("company"), position.get("title")) if part]
        if parts:
            return " – ".join(parts)[:120]
    return "New application"


@router.get("")
def list_projects(current_user: dict = Depends(get_current_user)) -> dict:
    projects = project_store.list_for_user(current_user["sub"])
    return {"count": len(projects), "items": [project.to_dict() for project in projects]}


@router.post("")
def create_project(body: ProjectCreatePayload, current_user: dict = Depends(get_current_user)) -> dict:
    try:
        project = project_store.create(
            current_user["sub"],
            body.name or "New application",
            template_id=body.template_id,
            cover_letter_template_id=body.cover_letter_template_id,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return project.to_dict()


@router.post("/from-job")
def create_project_from_job(body: ProjectFromJobPayload, current_user: dict = Depends(get_current_user)) -> dict:
    """Start a project from a job-search result (links job research to the project)."""
    job = body.job or {}
    title = str(job.get("title") or "").strip()
    company = str(job.get("company") or "").strip()
    if not title and not company:
        raise ValidationError("job.title or job.company is required.")
    provider = str(job.get("provider") or job.get("source") or "").strip()
    description = str(job.get("description") or "").strip()
    warnings: list[str] = []
    if len(description) < position_extraction.MIN_TEXT_CHARS:
        warnings.append("The job board returned no full description; attach the posting for a meaningful CV match.")
    position = Position(
        title=title or None,
        company=company or None,
        location=str(job.get("location") or "").strip() or None,
        description=description,
        url=str(job.get("url") or "").strip() or None,
        source=f"job_search:{provider}" if provider else "job_search",
        published_at=str(job.get("published_at") or "").strip() or None,
        keywords=position_extraction.extract_keywords(f"{title}\n{description}"),
        extracted_with="structured",
        warnings=tuple(warnings),
    ).to_dict()
    try:
        project = project_store.create(
            current_user["sub"],
            body.name or _default_name(position),
            template_id=body.template_id,
            cover_letter_template_id=body.cover_letter_template_id,
            position=position,
            status="researching",
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return project.to_dict()


@router.get("/{project_id}")
def get_project(project_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    return _owned_project(project_id, current_user).to_dict()


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    body: ProjectUpdatePayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Rename, archive, or change the CV / cover-letter template (content is untouched)."""
    _owned_project(project_id, current_user)
    try:
        return project_store.update(project_id, body.model_dump(exclude_unset=True)).to_dict()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    except KeyError as exc:
        raise NotFoundError("Project not found.") from exc


@router.delete("/{project_id}")
def delete_project(project_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete the project only; generated documents and tracker entries are kept."""
    _owned_project(project_id, current_user)
    if not project_store.delete(project_id):
        raise NotFoundError("Project not found.")
    return {"deleted": True, "project_id": project_id}


def _attach(project: Project, position: Position, result_extra: dict[str, Any]) -> dict:
    changes: dict[str, Any] = {"position": position.to_dict(), "match": None}
    if project.status == "draft":
        changes["status"] = "researching"
    updated = project_store.update(project.id, changes, internal=True)
    return {"project": updated.to_dict(), **result_extra}


@router.post("/{project_id}/position")
def attach_position(
    project_id: str,
    body: PositionAttachPayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Attach a position from a URL, pasted text, or an edited position object."""
    project = _owned_project(project_id, current_user)
    if body.position is not None:
        if body.url or body.text:
            raise ValidationError("Send either 'position' or 'url'/'text', not both.")
        position = Position.from_dict(body.position)
        if not (position.title or position.company or position.description):
            raise ValidationError("The position needs at least a title, company or description.")
        return _attach(project, position, {"candidates": [], "skipped": []})
    result = extract_from_payload(body.url, body.text)
    return _attach(project, result.positions[0], {"candidates": [], "skipped": result.skipped})


@router.post("/{project_id}/position/file")
async def attach_position_file(
    project_id: str,
    file: UploadFile = File(...),
    index: int = Query(default=0, ge=0, le=100, description="Which extracted position to attach (ZIP archives)."),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Attach a position from an uploaded PDF, DOCX, image, ZIP, HTML or text file."""
    project = _owned_project(project_id, current_user)
    content = await read_limited(file, position_extraction.MAX_UPLOAD_BYTES)
    result = await run_in_threadpool(position_extraction.extract_from_file, content, filename=file.filename)
    if not result.positions:
        raise ValidationError("No job posting could be read from the file.")
    if index >= len(result.positions):
        raise ValidationError(f"index {index} is out of range; {len(result.positions)} position(s) were found.")
    candidates = [
        {"index": i, "title": item.title, "company": item.company, "source": item.source}
        for i, item in enumerate(result.positions)
    ]
    return _attach(project, result.positions[index], {"candidates": candidates, "skipped": result.skipped})


@router.delete("/{project_id}/position")
def remove_position(project_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    project = _owned_project(project_id, current_user)
    if project.status == "applied":
        raise ValidationError("The position of an applied project cannot be removed.")
    updated = project_store.update(project_id, {"position": None, "match": None}, internal=True)
    return {"project": updated.to_dict()}


@router.post("/{project_id}/match")
def match_cv(
    project_id: str,
    body: ProjectMatchPayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Score a CV (pasted text or one of the user's documents) against the position."""
    project = _owned_project(project_id, current_user)
    position = Position.from_dict(project.position or {})
    if len(position.description) < position_extraction.MIN_TEXT_CHARS:
        raise ValidationError("The project's position has no job description to match against.")
    cv_text = (body.cv_text or "").strip()
    if body.cv_document_id:
        document = document_store.get(body.cv_document_id)
        if document is None or document.user_id != current_user["sub"]:
            raise NotFoundError("Document not found.")
        cv_text = document.content
    if not cv_text:
        raise ValidationError("Provide cv_text or cv_document_id.")
    result = check_resume_against_job(cv_text, position.description)
    result.update(check_resume_semantic(cv_text, position.description, ats_result=result))
    project_store.update(project_id, {"match": result}, internal=True)
    return result


@router.post("/{project_id}/apply")
def apply_to_project_position(
    project_id: str,
    body: ApplyPayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Tailor CV + cover letter, create the tracker entry (status *applied*) and link everything.

    Returns 409 when the project has already been applied to. Generation is
    deterministic (``ai_generated: false``): skills and highlights that match the
    position are listed first; no content is added or invented.
    """
    project = _owned_project(project_id, current_user)
    return apply_to_position(
        project,
        current_user["sub"],
        body.model_dump(exclude_unset=True),
        document_store=document_store,
    )
