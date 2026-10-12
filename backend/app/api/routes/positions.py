"""Position intake: turn a URL, pasted text or an uploaded file into a position.

All endpoints require authentication: fetching arbitrary URLs and running OCR
are the expensive / abusable operations of the API, so they are never anonymous.
Nothing is stored here — the result is a preview the client can edit and then
attach to a project (``POST /api/v1/projects/{id}/position``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.routes._uploads import read_limited
from app.api.schemas import COMMON_ERROR_RESPONSES, PositionExtractPayload
from app.application.services import position_extraction
from app.core.errors import ValidationError
from app.core.security.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/positions", tags=["positions"], responses=COMMON_ERROR_RESPONSES)


def extract_from_payload(url: str | None, text: str | None) -> position_extraction.ExtractionResult:
    """Exactly one of url / text must be given."""
    has_url = bool(url and url.strip())
    has_text = bool(text and text.strip())
    if has_url == has_text:
        raise ValidationError("Provide exactly one of 'url' or 'text'.")
    if has_url:
        return position_extraction.extract_from_url(str(url))
    return position_extraction.extract_from_text(str(text))


@router.post("/extract")
def extract_position(body: PositionExtractPayload, current_user: dict = Depends(get_current_user)) -> dict:
    """Extract a position from a public job-ad URL or pasted text."""
    return extract_from_payload(body.url, body.text).to_dict()


@router.post("/extract/file")
async def extract_position_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Extract position(s) from a PDF, DOCX, image (PNG/JPEG/WEBP), ZIP, HTML or text file."""
    content = await read_limited(file, position_extraction.MAX_UPLOAD_BYTES)
    result = await run_in_threadpool(position_extraction.extract_from_file, content, filename=file.filename)
    return result.to_dict()
