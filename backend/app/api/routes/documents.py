from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response

from app.api.schemas import COMMON_ERROR_RESPONSES, DocumentPayload
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
from app.core.errors import ExportError, NotFoundError, ValidationError
from app.core.security.dependencies import get_current_user

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
    current_user: dict = Depends(get_current_user),
) -> Response:
    document = _get_owned_document(document_id, current_user["sub"])

    payload = document.to_dict()
    if format == "html":
        return PlainTextResponse(render_document_to_html(payload))

    if format == "text":
        return PlainTextResponse(document.content)

    if format == "pdf":
        try:
            pdf_bytes = render_document_to_pdf(payload)
        except Exception as exc:
            raise ExportError("PDF export failed.", internal=str(exc)) from exc
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{document.title}.pdf"'},
        )

    if format == "docx":
        try:
            docx_bytes = render_document_to_docx(payload)
        except Exception as exc:
            raise ExportError("DOCX export failed.", internal=str(exc)) from exc
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{document.title}.docx"'},
        )

    raise ValidationError("Unsupported export format. Use html, text, pdf, or docx.")


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
