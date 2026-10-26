"""API-level Pydantic schemas (MASTER_IMPLEMANTATION_PROMPT §26).

Request bodies are intentionally permissive: all fields are optional so
business rules stay in the handlers (with their specific 400 messages),
while *wrong types* are rejected early with a 422 validation envelope.
Unknown extra keys are allowed and pass through untouched (forward
compatibility with renderers that read additional fields).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApplicationPayload",
    "ApplicationStatusPayload",
    "ApplicationUpdatePayload",
    "ChatCompletionPayload",
    "ChatSessionCreatePayload",
    "COMMON_ERROR_RESPONSES",
    "CoverLetterGenerationPayload",
    "CVGenerationPayload",
    "DocumentPayload",
    "ErrorResponse",
    "GENERATION_ERROR_RESPONSES",
    "HealthResponse",
    "ProfilePayload",
    "ApplyPayload",
    "ProjectMatchPayload",
    "ProjectFromJobPayload",
    "PositionAttachPayload",
    "PositionExtractPayload",
    "ProjectUpdatePayload",
    "ProjectCreatePayload",
    "ReadyResponse",
    "ResignationPayload",
    "ResumeCheckPayload",
    "TemplatePreviewPayload",
]


class ErrorResponse(BaseModel):
    """Consistent error envelope returned by every failure path (§26/§27)."""

    detail: str
    category: str


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    """Readiness report: overall status plus per-dependency checks (§28)."""

    status: str
    checks: dict[str, Any]
    ai: dict[str, Any] | None = None


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Validation error (category: validation)."},
    401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."},
    404: {"model": ErrorResponse, "description": "Resource not found."},
    500: {"model": ErrorResponse, "description": "Unexpected server error — no internals are returned."},
}

GENERATION_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **COMMON_ERROR_RESPONSES,
    422: {"model": ErrorResponse, "description": "Request body failed schema validation."},
    502: {"model": ErrorResponse, "description": "AI provider error (category: ai_provider)."},
    503: {"model": ErrorResponse, "description": "Upstream dependency unavailable."},
}


class _LoosePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class CVGenerationPayload(_LoosePayload):
    name: str | None = None
    target_role: str | None = None
    summary: str | None = None
    experience: list[Any] | None = None
    education: list[Any] | None = None
    skills: list[Any] | None = None
    template_id: str | None = None
    language: str | None = None
    use_ai: bool | None = None


class CoverLetterGenerationPayload(_LoosePayload):
    name: str | None = None
    company: str | None = None
    target_role: str | None = None
    summary: str | None = None
    template_id: str | None = None
    language: str | None = None
    use_ai: bool | None = None


class ResignationPayload(_LoosePayload):
    name: str | None = None
    company: str | None = None
    role: str | None = None
    last_working_day: str | None = None
    notice_period: str | None = None
    reason: str | None = None
    tone: str | None = None
    template_id: str | None = None
    language: str | None = None


class ResumeCheckPayload(_LoosePayload):
    resume_text: str | None = None
    job_description: str | None = None


class DocumentPayload(_LoosePayload):
    title: str | None = None
    document_type: str | None = None
    template_id: str | None = None
    content: str | None = None


class RenderPayload(BaseModel):
    """Stateless export request: render the given text in a template design; nothing is stored."""

    model_config = ConfigDict(extra="ignore")
    content: str = Field(min_length=1, max_length=200_000)
    document_type: Literal["cv", "cover_letter", "resignation"] = "cv"
    template_id: str = Field(default="", max_length=100)
    title: str = Field(default="Document", max_length=200)
    format: Literal["html", "pdf", "docx"] = "pdf"
    theme_id: str = Field(default="", max_length=60)
    country: str = Field(default="", max_length=10)
    sidebar: Literal["", "left", "right"] = ""


class ProfilePayload(_LoosePayload):
    email: str | None = None
    full_name: str | None = None
    target_role: str | None = None
    location: str | None = None
    summary: str | None = None


class ApplicationPayload(_LoosePayload):
    company: str | None = None
    position: str | None = None
    status: str | None = None
    job_url: str | None = None
    notes: str | None = None
    follow_up_date: str | None = None


class ApplicationUpdatePayload(_LoosePayload):
    """Partial update of a tracked application (only the fields sent change)."""

    company: str | None = None
    position: str | None = None
    status: str | None = None
    job_url: str | None = None
    notes: str | None = None
    follow_up_date: str | None = None


class ApplicationStatusPayload(_LoosePayload):
    status: str | None = None


class ProjectCreatePayload(_LoosePayload):
    name: str | None = None
    template_id: str | None = None
    cover_letter_template_id: str | None = None


class ProjectUpdatePayload(_LoosePayload):
    name: str | None = None
    status: str | None = None
    template_id: str | None = None
    cover_letter_template_id: str | None = None


class PositionExtractPayload(_LoosePayload):
    """Exactly one of ``url`` / ``text``."""

    url: str | None = None
    text: str | None = None


class PositionAttachPayload(_LoosePayload):
    """Attach a position: extract from ``url`` / ``text`` or store an edited ``position``."""

    url: str | None = None
    text: str | None = None
    position: dict[str, Any] | None = None


class ProjectFromJobPayload(_LoosePayload):
    """Start a project from a job-search result (``job`` as returned by /jobs/search)."""

    job: dict[str, Any] | None = None
    name: str | None = None
    template_id: str | None = None
    cover_letter_template_id: str | None = None


class ProjectMatchPayload(_LoosePayload):
    cv_text: str | None = None
    cv_document_id: str | None = None


class ApplyPayload(_LoosePayload):
    candidate: dict[str, Any] | None = None
    cv_document_id: str | None = None
    cover_letter_document_id: str | None = None
    include_cover_letter: bool = True
    notes: str | None = None
    follow_up_date: str | None = None


class TemplatePreviewPayload(_LoosePayload):
    """Request body for template preview.

    All fields are sample values so a user can see how a template
    renders before committing real content. No PII is required.
    """

    template_id: str | None = None
    document_type: str | None = None
    locale: str | None = None
    name: str | None = None
    target_role: str | None = None
    company: str | None = None
    summary: str | None = None


class ChatSessionCreatePayload(_LoosePayload):
    """Create a chat session (thread). All fields optional; handler defaults apply."""

    title: str | None = None
    model_id: str | None = None
    mode: str | None = None
    language: str | None = None


class ChatCompletionPayload(_LoosePayload):
    """One chat completion turn.

    ``message`` is the new user message. ``session_id`` targets an existing
    thread; when omitted the caller must supply ``message`` and a new session
    is created server-side. ``model_id`` pins the model for this turn (chat
    model picker) and falls back to the session's model, then auto-routing.
    ``document_context`` carries extracted CV/letter text the user attached
    (reference-only — never overrides their facts).
    """

    session_id: str | None = None
    message: str | None = None
    model_id: str | None = None
    mode: str | None = None
    title: str | None = None
    document_context: str | None = None
    #: A job posting the user wants to work with: a link to fetch or the pasted text.
    job_url: str | None = None
    job_text: str | None = None
    #: Which document the user is working on ("cv" or "cover_letter").
    document_type: Literal["cv", "cover_letter"] | None = None
    #: The template the generated document should use.
    template_id: str | None = None
    #: The visual theme of the generated document.
    theme_id: str | None = None
    #: Optional job-search preferences from the frontend form (see ``PAYLOAD_FIELD_MAP``).
    preferences: dict[str, Any] | None = None
