from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response

from app.api.schemas import COMMON_ERROR_RESPONSES, DocumentPayload, RenderPayload
from app.application.services.document_generation import (
    render_document_to_docx,
    render_document_to_html,
    render_document_to_pdf,
)
from app.application.services.document_retrieval import (
    DEFAULT_RETRIEVAL_MIN_SIMILARITY,
    DEFAULT_RETRIEVAL_TOP_K,
    DOCUMENT_ENTITY_TYPES,
    get_document_retrieval,
)
from app.application.services.document_store import document_store
from app.application.services.generation_context import resolve_template
from app.core.errors import ExportError, NotFoundError, ValidationError
from app.core.security.dependencies import get_current_user, get_optional_user
from app.domain.templates.themes import THEMES

router = APIRouter(prefix="/api/v1/documents", tags=["documents"], responses=COMMON_ERROR_RESPONSES)


@router.get("")
def list_documents(current_user: dict = Depends(get_current_user)) -> dict:
    documents = document_store.list_for_user(current_user["sub"])
    return {"count": len(documents), "items": [document.to_dict() for document in documents]}


@router.post("")
def create_document(body: DocumentPayload, current_user: dict = Depends(get_current_user)) -> dict:
    payload = body.model_dump(exclude_unset=True)
    if not payload.get("content"):
        raise ValidationError("content is required.")
    allowed_fields = {"title", "document_type", "template_id", "content"}
    safe_payload = {key: value for key, value in payload.items() if key in allowed_fields}
    safe_payload["user_id"] = current_user["sub"]
    document = document_store.create(safe_payload)
    return document.to_dict()


@router.get("/retrieve")
def retrieve_personal_documents(
    query: str,
    top_k: int = DEFAULT_RETRIEVAL_TOP_K,
    min_similarity: float = DEFAULT_RETRIEVAL_MIN_SIMILARITY,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Retrieve the user's own relevant document chunks (RD-05).

    User-scoped: only the requesting user's indexed
    documents are searched. Results carry the source
    document id, type, and similarity.
    """
    results = get_document_retrieval().retrieve(
        user_id=current_user["sub"],
        query=query,
        top_k=top_k,
        min_similarity=min_similarity,
    )
    return {"count": len(results), "items": results}


@router.get("/{document_id}")
def get_document(document_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    document = _get_owned_document(document_id, current_user["sub"])
    return document.to_dict()


@router.patch("/{document_id}")
def update_document(
    document_id: str,
    body: DocumentPayload,
    current_user: dict = Depends(get_current_user),
) -> dict:
    payload = body.model_dump(exclude_unset=True)
    _get_owned_document(document_id, current_user["sub"])
    allowed_fields = {"title", "document_type", "template_id", "content"}
    safe_payload = {key: value for key, value in payload.items() if key in allowed_fields}
    try:
        document = document_store.update(document_id, safe_payload)
    except KeyError as exc:
        raise NotFoundError("Document not found.") from exc
    return document.to_dict()


@router.get("/{document_id}/versions")
def list_document_versions(document_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    _get_owned_document(document_id, current_user["sub"])
    try:
        versions = document_store.list_versions(document_id)
    except KeyError as exc:
        raise NotFoundError("Document not found.") from exc
    return {"count": len(versions), "items": versions}


@router.get("/{document_id}/versions/{version}")
def get_document_version(
    document_id: str,
    version: int,
    current_user: dict = Depends(get_current_user),
) -> dict:
    _get_owned_document(document_id, current_user["sub"])
    try:
        return document_store.get_version(document_id, version)
    except KeyError as exc:
        raise NotFoundError(f"Version {version} not found.") from exc


@router.post("/{document_id}/versions/{version}/restore")
def restore_document_version(
    document_id: str,
    version: int,
    current_user: dict = Depends(get_current_user),
) -> dict:
    _get_owned_document(document_id, current_user["sub"])
    try:
        document = document_store.restore_version(document_id, version)
    except KeyError as exc:
        raise NotFoundError(f"Version {version} not found.") from exc
    return document.to_dict()


@router.get("/{document_id}/export", response_model=None)
def export_document(
    document_id: str,
    format: str = "html",
    theme_id: str = "",
    country: str = "",
    sidebar: str = "",
    current_user: dict = Depends(get_current_user),
) -> Response:
    document = _get_owned_document(document_id, current_user["sub"])

    payload = document.to_dict()
    resolved = resolve_template(
        current_user["sub"], str(payload.get("template_id") or ""), str(payload.get("document_type") or "cv")
    )
    if resolved is not None:  # a user template renders with its built-in base design
        payload["template_id"] = resolved.render_template_id
    if theme_id and theme_id not in THEMES:
        raise ValidationError(f"Unknown theme '{theme_id}'.")
    if sidebar not in ("", "left", "right"):
        raise ValidationError("sidebar must be 'left' or 'right'.")
    if theme_id or country or sidebar:
        payload["theme_id"], payload["country"], payload["sidebar"] = theme_id, country, sidebar
    if format == "text":
        return PlainTextResponse(document.content)
    return _render_response(payload, format, document.title)


_MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe_filename(title: str) -> str:
    """ASCII-safe file stem for Content-Disposition (no quotes, control chars or path separators)."""
    stem = re.sub(r"\.{2,}", "_", re.sub(r"[^A-Za-z0-9._ -]+", "_", title)).strip(" ._") or "document"
    return stem[:80]


def _render_response(payload: dict, fmt: str, title: str) -> Response:
    if fmt == "html":
        return PlainTextResponse(render_document_to_html(payload))
    if fmt not in _MEDIA:
        raise ValidationError("Unsupported export format. Use html, text, pdf, or docx.")
    try:
        data = render_document_to_pdf(payload) if fmt == "pdf" else render_document_to_docx(payload)
    except Exception as exc:
        raise ExportError(f"{fmt.upper()} export failed.", internal=str(exc)) from exc
    return Response(
        content=data,
        media_type=_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(title)}.{fmt}"'},
    )


@router.post("/render", response_model=None)
def render_document(body: RenderPayload, current_user: dict | None = Depends(get_optional_user)) -> Response:
    """Render text in a template design and return the file; nothing is saved.

    Anonymous callers can use built-in templates; a user's own template id needs their token.
    """
    user_id = current_user["sub"] if current_user else None
    resolved = resolve_template(user_id, body.template_id, body.document_type)
    if resolved is None:
        raise ValidationError(f"Template '{body.template_id}' is not available for '{body.document_type}'.")
    if body.theme_id and body.theme_id not in THEMES:
        raise ValidationError(f"Unknown theme '{body.theme_id}'.")
    payload = {
        "title": body.title,
        "content": body.content,
        "document_type": body.document_type,
        "template_id": resolved.render_template_id,
        "theme_id": body.theme_id,
        "country": body.country.upper(),
        "sidebar": body.sidebar,
    }
    return _render_response(payload, body.format, body.title)


@router.post("/{document_id}/index")
def index_document(document_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Chunk, embed, and index one owned document for personal retrieval (RD-05).

    Only CVs, cover letters, and resume analyses are
    eligible. Each chunk is stored with its source
    document id so retrieval is auditable.
    """
    document = _get_owned_document(document_id, current_user["sub"])
    if document.document_type not in DOCUMENT_ENTITY_TYPES:
        raise ValidationError(
            "Only documents of type " f"{', '.join(DOCUMENT_ENTITY_TYPES)} can be indexed for retrieval."
        )
    return get_document_retrieval().index_document(
        user_id=current_user["sub"],
        document_type=document.document_type,
        document_id=document_id,
        content=document.content,
    )


@router.delete("/{document_id}")
def delete_document(document_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete one owned document (and its retained version history).

    GDPR right to erasure: a user can delete their own documents.
    Foreign documents return 404 (not 403) to avoid leaking existence.
    """
    _get_owned_document(document_id, current_user["sub"])
    deleted = document_store.delete(document_id)
    if not deleted:
        raise NotFoundError("Document not found.")
    return {"deleted": True, "document_id": document_id}


def _get_owned_document(document_id: str, user_id: str):
    document = document_store.get(document_id)
    if document is None or document.user_id != user_id:
        raise NotFoundError("Document not found.")
    return document
