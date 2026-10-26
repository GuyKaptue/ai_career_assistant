from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, File, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.api.routes.applications import router as applications_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.positions import router as positions_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.projects import router as projects_router
from app.api.schemas import (
    GENERATION_ERROR_RESPONSES,
    CoverLetterGenerationPayload,
    CVGenerationPayload,
    ResignationPayload,
    ResumeCheckPayload,
    TemplatePreviewPayload,
)
from app.application.services.application_tracking import application_tracker
from app.application.services.ats_checker import check_resume_against_job
from app.application.services.cv_pdf_extractor import extract_text_from_pdf_bytes
from app.application.services.document_generation import (
    DEFAULT_RESIGNATION_TONE,
    RESIGNATION_TONES,
    generate_cover_letter_document,
    generate_cv_document,
    generate_resignation_letter_document,
)
from app.application.services.document_retrieval import get_document_retrieval
from app.application.services.generation_context import (
    personal_context_for_generation,
    reference_context,
    resolve_template,
)
from app.application.services.knowledge_base import get_knowledge_base
from app.application.services.semantic_matching import (
    check_resume_semantic,
    semantic_matching,
)
from app.application.services.shared_router import get_adapter, get_router, log_routing_decision
from app.application.services.template_service import get_template_service
from app.core.config import settings
from app.core.errors import (
    AIProviderError,
    ConfigurationError,
    ExternalServiceError,
    format_pydantic_errors,
    register_exception_handlers,
)
from app.core.errors import (
    ValidationError as AppValidationError,
)
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.core.observability import configure_logging
from app.core.security.dependencies import get_optional_user
from app.domain.documents.country_profiles import (
    apply_photo_policy,
    paper_for,
    profile_for_country,
    section_labels,
)
from app.domain.documents.schemas import (
    CoverLetterGenerationRequest,
    CoverLetterGenerationResult,
    CVGenerationRequest,
    CVGenerationResult,
)
from app.domain.jobs.providers import JobSearchOptions
from app.domain.jobs.service import JobSearchFailed, search_jobs
from app.domain.templates.template_registry import TemplateRegistry
from app.domain.templates.themes import FONTS, THEMES, contrast_report
from app.infrastructure.ai.prompts.cv import build_cover_letter_prompt, build_cv_prompt
from app.infrastructure.document_export.previews import SAMPLE_FORMATS, render_sample

logger = logging.getLogger(__name__)

# Structured JSON logging for the whole process (§28). Idempotent.
configure_logging(settings.log_level)

AI_REVIEW_NOTICE = "AI-generated content — review before sending."

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes (§28)."},
    {"name": "templates", "description": "Document template listing."},
    {"name": "generation", "description": "AI-assisted generation with deterministic template fallback."},
    {"name": "jobs", "description": "Job search across configured providers."},
    {"name": "profiles", "description": "User profile management (Bearer JWT)."},
    {"name": "applications", "description": "Application tracking (Bearer JWT)."},
    {"name": "documents", "description": "Document storage, versioning and export (Bearer JWT)."},
    {"name": "chat", "description": "AI chat sessions and completions with RAG grounding (Bearer JWT)."},
]

app = FastAPI(
    title="AI Career Assistant API",
    version="0.1.0",
    description=(
        "Career documents, job search and tracking.\n\n"
        "**Authentication:** `Authorization: Bearer <JWT>` on `/api/v1/` profile, "
        "application and document routes.\n\n"
        '**Errors:** every failure returns `{"detail": str, "category": str}` with categories '
        "validation, authentication, authorization, not_found, ai_provider, external_service, "
        "database, export, configuration, rate_limited, unavailable, internal. Stack traces and internal "
        "details are logged server-side and never returned.\n\n"
        "**Health:** `GET /health`, `GET /api/health`, `GET /api/ready` (readiness: config + database).\n\n"
        "**Rate limiting:** per-client requests per minute (`RATE_LIMIT_PER_MINUTE`, 0 disables); "
        "429 responses carry `category: rate_limited` and a `Retry-After` header."
    ),
    openapi_tags=OPENAPI_TAGS,
)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(profiles_router)
app.include_router(applications_router)
app.include_router(documents_router)
app.include_router(knowledge_router)
app.include_router(chat_router)
app.include_router(projects_router)
app.include_router(positions_router)

# Security + observability middleware (§12, §28). Starlette runs the last-added
# middleware outermost, so the effective order is:
#   CORS → request logging → security headers → rate limit → routes.
# Rate limiting sits innermost so 429 responses still receive security headers
# and are logged with their correlation ID; logging wraps it so every
# rejection stays observable.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# Explicit origin allowlist (§26). Added last so CORS headers also wrap error responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)


@app.get("/api/v1/templates", tags=["templates"])
def list_templates(
    document_type: str | None = None,
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    """Built-in templates (additive ``type``/``layout``/``color_scheme``/``source``) plus,
    for authenticated callers, their own templates. Existing fields are unchanged."""
    registry = TemplateRegistry()
    templates = registry.list_templates(document_type=document_type)
    items: list[dict] = [
        {
            "id": template.id,
            "name": template.name,
            "document_type": template.document_type,
            "type": template.document_type,
            "description": template.description,
            "supported_locales": list(template.supported_locales),
            "layout": template.metadata.get("layout"),
            "color_scheme": template.metadata.get("color_scheme"),
            "columns": int(template.metadata.get("columns", 1)),
            "sidebar": template.metadata.get("sidebar"),
            "sidebar_pct": template.metadata.get("sidebar_pct"),
            "theme_id": template.metadata.get("theme_id"),
            "source": "builtin",
        }
        for template in templates
    ]
    if current_user is not None:
        for own in get_template_service().list_templates(current_user["sub"], document_type):
            base = registry.get(own.base_template_id, own.kind) if own.base_template_id else None
            items.append(
                {
                    "id": own.id,
                    "name": own.name,
                    "document_type": own.kind,
                    "type": own.kind,
                    "description": own.structure_type or "",
                    "supported_locales": list(base.supported_locales) if base else ["en", "de", "fr"],
                    "layout": base.metadata.get("layout") if base else None,
                    "color_scheme": base.metadata.get("color_scheme") if base else None,
                    "columns": int(base.metadata.get("columns", 1)) if base else 1,
                    "sidebar": base.metadata.get("sidebar") if base else None,
                    "sidebar_pct": base.metadata.get("sidebar_pct") if base else None,
                    "theme_id": base.metadata.get("theme_id") if base else None,
                    "source": "user",
                }
            )
    return {"count": len(items), "items": items}


@app.get("/api/v1/themes", tags=["templates"])
def list_themes() -> dict:
    """The 20 selectable colour themes, with their WCAG AA contrast report."""
    items = [{**t.to_dict(), "contrast": contrast_report(t)} for t in THEMES.values()]
    return {"count": len(items), "items": items, "fonts": list(FONTS)}


@app.get("/api/v1/country-profiles", tags=["templates"])
def country_profile(country: str, language: str | None = None, has_photo: bool = False) -> dict:
    """CV and cover-letter conventions for the employer's country (decided in code)."""
    profile = profile_for_country(country, language)
    _, caveats = apply_photo_policy(profile, has_photo)
    locale = language if language in ("en", "de", "fr") else (profile.language if profile.language != "match" else "en")
    return {
        **profile.to_dict(country.upper()),
        "paper_size": paper_for(country, profile),
        "section_labels": section_labels(profile, locale),
        "caveats": caveats,
    }


@app.get("/api/v1/templates/{template_id}/sample", tags=["templates"], response_model=None)
def template_sample(
    template_id: str,
    document_type: str = "cv",
    locale: str = "en",
    format: str = "png",
    theme_id: str = "",
    country: str = "",
    sidebar: str = "",
) -> Response:
    """Synthetic sample of one built-in template as png, pdf, docx or html (no user data).

    Uses the same theme as document export, so a gallery thumbnail matches the download.
    """
    template = TemplateRegistry().get(template_id, document_type)
    if template is None:
        raise AppValidationError(f"Template '{template_id}' is not available for document type '{document_type}'.")
    if locale not in template.supported_locales:
        raise AppValidationError(f"Template '{template_id}' does not support locale '{locale}'.")
    if format not in SAMPLE_FORMATS:
        raise AppValidationError("Unsupported format. Use png, pdf, docx, or html.")
    if theme_id and theme_id not in THEMES:
        raise AppValidationError(f"Unknown theme '{theme_id}'.")
    if sidebar not in ("", "left", "right"):
        raise AppValidationError("sidebar must be 'left' or 'right'.")
    data = render_sample(
        template.id,
        document_type,
        locale,
        format,
        tuple(sorted((k, str(v)) for k, v in template.metadata.items())),
        theme_id,
        country.upper(),
        sidebar,
    )
    return Response(
        content=data,
        media_type=SAMPLE_FORMATS[format],
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.post("/api/v1/templates/preview", tags=["templates"])
def preview_template(body: TemplatePreviewPayload) -> dict:
    """Render a sample document for the requested template so a user can
    preview the layout before committing real content.

    Sample values are used; no PII is required. The preview is
    deterministic and never calls the AI path.
    """
    from app.core.errors import ValidationError

    payload = body.model_dump(exclude_unset=True)
    template_id = payload.get("template_id") or "professional"
    document_type = payload.get("document_type") or "cv"
    locale = (payload.get("locale") or "en").strip().lower() or "en"

    registry = TemplateRegistry()
    template = registry.get(template_id, document_type)
    if template is None:
        raise ValidationError(f"Template '{template_id}' is not available for document type '{document_type}'.")
    if locale not in template.supported_locales:
        raise ValidationError(
            f"Template '{template_id}' does not support locale '{locale}'. "
            f"Supported: {', '.join(template.supported_locales)}"
        )

    name = payload.get("name") or "Sample Candidate"
    target_role = payload.get("target_role") or "Sample Role"
    company = payload.get("company") or "Sample Company"
    summary = payload.get("summary") or "Sample summary for preview purposes only."

    if document_type == "cover_letter":
        document = {
            "name": name,
            "company": company,
            "target_role": target_role,
            "summary": summary,
            "template_id": template_id,
            "locale": locale,
        }
        content = generate_cover_letter_document(document, template_id=template_id)
    elif document_type == "resignation":
        document = {
            "name": name,
            "company": company,
            "role": target_role,
            "last_working_day": "2026-12-31",
            "notice_period": "30 days",
            "reason": "pursuing a new opportunity",
            "template_id": template_id,
            "locale": locale,
        }
        content = generate_resignation_letter_document(document, template_id=template_id)
    else:
        document = {
            "name": name,
            "target_role": target_role,
            "summary": summary,
            "template_id": template_id,
            "locale": locale,
        }
        content = generate_cv_document(document, template_id=template_id)

    return {
        "template_id": template_id,
        "document_type": document_type,
        "locale": locale,
        "name": template.name,
        "ai_generated": False,
        "review_before_sending": False,
        "content": content.get("content", ""),
    }


@app.get("/api/v1/models", tags=["chat"])
def list_models(task: str | None = Query(default=None, max_length=50)) -> dict:
    """List routable models for the chat model picker.

    Ordered by routing quality (best first); only enabled models are returned.
    No user data is involved, so the endpoint is public. Exposes only
    picker-relevant metadata (§26) — never tokens or internals.

    The list is prefixed with the ``auto`` sentinel so the picker can offer
    "let the router choose" as the default alongside manual overrides. When
    ``task`` is given, the models are ranked for that task and the response
    reports which one auto-selection would pick, so the UI can show the
    current automatic choice.
    """
    models = get_router().list_models(task=task)
    items = [
        {
            "model_id": model.model_id,
            "provider": model.provider,
            "context_window": model.context_window,
            "max_output_tokens": model.max_output_tokens,
            "quality_score": model.quality_score,
            "health_status": model.health_status,
            "license": model.license,
            "license_policy_status": getattr(model, "license_policy_status", "APPROVED"),
            "capabilities": list(model.task_capabilities),
            "supported_languages": list(model.supported_languages),
            # False = verified unable to serve chat through the inference
            # provider (see model_catalog.CHAT_ROUTER_VERIFIED). The UI shows
            # these as registered-but-unavailable instead of offering them as
            # an answer that can only fail.
            "chat_compatible": model.inference_provider_supported is not False,
        }
        for model in models
    ]

    auto_choice = None
    if task and models:
        try:
            auto_choice = (
                get_router()
                .select_model(
                    task=task,
                    token_budget=1024,
                    preferred_languages=("en", "de", "fr"),
                )
                .model_id
            )
        except Exception:  # noqa: BLE001 - picker must render even with no eligible model
            auto_choice = None

    return {
        "count": len(items),
        "items": items,
        "default": "auto",
        "auto_default_model": auto_choice,
    }


@app.post(
    "/api/v1/documents/cv/generate",
    tags=["generation"],
    responses=GENERATION_ERROR_RESPONSES,
)
def generate_cv(
    body: CVGenerationPayload,
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    """Generate a CV. `use_ai: true` routes through HF inference.

    Default (false/absent) keeps the deterministic local template path so
    the endpoint works offline. AI output is validated against
    CVGenerationResult and always carries the human-review notice.
    """
    payload = body.model_dump(exclude_unset=True)
    use_ai = bool(payload.get("use_ai", False))
    try:
        request = CVGenerationRequest(
            name=str(payload.get("name", "Candidate")),
            target_role=str(payload.get("target_role", "Target Role")),
            summary=str(payload.get("summary", "")),
            experience=payload.get("experience", []) or [],
            education=payload.get("education", []) or [],
            skills=[str(s) for s in (payload.get("skills", []) or [])],
            template_id=str(payload.get("template_id", "professional")),
            use_ai=use_ai,
        )
    except ValidationError as exc:
        raise AppValidationError(format_pydantic_errors(exc), internal=str(exc)) from exc

    # RD-03: retrieve relevant career guidance before
    # rendering. The context is reference-only and never
    # overrides the user's provided facts.
    knowledge_context = get_knowledge_base().retrieve_for_generation(query=f"{request.target_role} {request.summary}")[
        "context"
    ]

    # RD-05: personalize with the user's own documents
    # when authenticated. Anonymous requests skip
    # retrieval (empty context).
    user_id = current_user["sub"] if current_user is not None else None
    resolved = resolve_template(user_id, request.template_id, "cv")
    personal_context = personal_context_for_generation(
        user_id,
        f"{request.target_role} {request.summary}",
        resolved.selected_id if resolved else request.template_id,
        get_document_retrieval(),
    )

    try:
        base = generate_cv_document(
            payload,
            template_id=resolved.render_template_id if resolved else request.template_id,
            knowledge_context=knowledge_context,
            personal_context=personal_context,
        )
    except ValueError as exc:
        raise AppValidationError(str(exc)) from exc

    if not use_ai:
        result = CVGenerationResult(
            template_id=base["template_id"],
            content=base["content"],
            ai_generated=False,
            review_before_sending=False,
            metadata=base.get("metadata", {}),
        )
        return result.model_dump()

    prompt = build_cv_prompt(
        request.name,
        request.target_role,
        request.summary,
        request.experience,
        request.education,
        request.skills,
        request.language,
        template_guidance=resolved.guidance if resolved else "",
        reference_context=reference_context(knowledge_context, personal_context),
    )
    adapter = get_adapter()
    try:
        inference = adapter.generate_with_fallback(
            task="cv_generation",
            prompt=prompt,
            token_budget=1024,
            preferred_languages=(request.language,),
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning("ai.cv failed, falling back to template: %s", exc)
        log_routing_decision(
            task="cv_generation",
            model_id="none",
            fallback_reason=str(exc)[:500],
            fallback_chain=[],
            routing_score=None,
            required_context=1024,
            success=False,
        )
        result = CVGenerationResult(
            template_id=base["template_id"],
            content=base["content"],
            ai_generated=False,
            review_before_sending=False,
            fallback_reason=str(exc)[:500],
            metadata=base.get("metadata", {}),
        )
        return result.model_dump()

    log_routing_decision(
        task="cv_generation",
        model_id=inference["model_id"],
        fallback_reason=inference.get("fallback_reason"),
        fallback_chain=inference.get("fallback_chain", []),
        routing_score=inference.get("routing_score"),
        required_context=inference.get("required_context", 1024),
        success=True,
    )

    content = f"{inference['content']}\n\n{AI_REVIEW_NOTICE}"
    try:
        result = CVGenerationResult(
            template_id=base["template_id"],
            content=content,
            model_id=inference["model_id"],
            ai_generated=True,
            review_before_sending=True,
            fallback_reason=inference.get("fallback_reason"),
            metadata={**base.get("metadata", {}), "prompt_version": "v1"},
        )
    except ValidationError as exc:
        raise AIProviderError("AI output violated the CV schema.", internal=str(exc)) from exc
    return result.model_dump()


@app.post(
    "/api/v1/documents/cover-letter/generate",
    tags=["generation"],
    responses=GENERATION_ERROR_RESPONSES,
)
def generate_cover_letter(
    body: CoverLetterGenerationPayload,
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    """Generate a cover letter. Same `use_ai` contract as the CV endpoint."""
    payload = body.model_dump(exclude_unset=True)
    use_ai = bool(payload.get("use_ai", False))
    try:
        request = CoverLetterGenerationRequest(
            name=str(payload.get("name", "Candidate")),
            company=str(payload.get("company", "Target Company")),
            target_role=str(payload.get("target_role", payload.get("role", "role"))),
            summary=str(payload.get("summary", "")),
            template_id=str(payload.get("template_id", "classic-letter")),
            use_ai=use_ai,
        )
    except ValidationError as exc:
        raise AppValidationError(format_pydantic_errors(exc), internal=str(exc)) from exc

    # RD-03: retrieved guidance is reference-only.
    knowledge_context = get_knowledge_base().retrieve_for_generation(
        query=f"{request.target_role} {request.company} {request.summary}"
    )["context"]

    # RD-05: personalize with the user's own documents
    # when authenticated. Anonymous requests skip
    # retrieval (empty context).
    user_id = current_user["sub"] if current_user is not None else None
    resolved = resolve_template(user_id, request.template_id, "cover_letter")
    personal_context = personal_context_for_generation(
        user_id,
        f"{request.target_role} {request.company} {request.summary}",
        resolved.selected_id if resolved else request.template_id,
        get_document_retrieval(),
    )

    try:
        base = generate_cover_letter_document(
            payload,
            template_id=resolved.render_template_id if resolved else request.template_id,
            knowledge_context=knowledge_context,
            personal_context=personal_context,
        )
    except ValueError as exc:
        raise AppValidationError(str(exc)) from exc

    if not use_ai:
        result = CoverLetterGenerationResult(
            template_id=base["template_id"],
            content=base["content"],
            ai_generated=False,
            review_before_sending=False,
            metadata=base.get("metadata", {}),
        )
        return result.model_dump()

    prompt = build_cover_letter_prompt(
        request.name,
        request.company,
        request.target_role,
        request.summary,
        request.language,
        template_guidance=resolved.guidance if resolved else "",
        reference_context=reference_context(knowledge_context, personal_context),
    )
    adapter = get_adapter()
    try:
        inference = adapter.generate_with_fallback(
            task="cover_letter_generation",
            prompt=prompt,
            token_budget=768,
            preferred_languages=(request.language,),
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning("ai.cover-letter failed, falling back to template: %s", exc)
        log_routing_decision(
            task="cover_letter_generation",
            model_id="none",
            fallback_reason=str(exc)[:500],
            fallback_chain=[],
            routing_score=None,
            required_context=768,
            success=False,
        )
        result = CoverLetterGenerationResult(
            template_id=base["template_id"],
            content=base["content"],
            ai_generated=False,
            review_before_sending=False,
            fallback_reason=str(exc)[:500],
            metadata=base.get("metadata", {}),
        )
        return result.model_dump()

    content = f"{inference['content']}\n\n{AI_REVIEW_NOTICE}"
    log_routing_decision(
        task="cover_letter_generation",
        model_id=inference["model_id"],
        fallback_reason=inference.get("fallback_reason"),
        fallback_chain=inference.get("fallback_chain", []),
        routing_score=inference.get("routing_score"),
        required_context=inference.get("required_context", 768),
        success=True,
    )
    try:
        result = CoverLetterGenerationResult(
            template_id=base["template_id"],
            content=content,
            model_id=inference["model_id"],
            ai_generated=True,
            review_before_sending=True,
            fallback_reason=inference.get("fallback_reason"),
            metadata={**base.get("metadata", {}), "prompt_version": "v1"},
        )
    except ValidationError as exc:
        raise AIProviderError("AI output violated the cover-letter schema.", internal=str(exc)) from exc
    return result.model_dump()


@app.post(
    "/api/v1/documents/resignation/generate",
    tags=["generation"],
    responses=GENERATION_ERROR_RESPONSES,
)
def generate_resignation_letter(
    body: ResignationPayload,
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    payload = body.model_dump(exclude_unset=True)
    tone = str(payload.get("tone") or DEFAULT_RESIGNATION_TONE).strip().lower()
    if tone not in RESIGNATION_TONES:
        raise AppValidationError(f"tone must be one of: {', '.join(RESIGNATION_TONES)}.")
    payload = {**payload, "tone": tone}
    # RD-03: retrieved guidance is reference-only.
    knowledge_context = get_knowledge_base().retrieve_for_generation(
        query=f"{payload.get('company', '')} {payload.get('reason', '')}"
    )["context"]
    # RD-05: personalize with the user's own documents
    # when authenticated. Anonymous requests skip
    # retrieval (empty context).
    personal_context = ""
    if current_user is not None:
        personal_context = get_document_retrieval().retrieve_for_generation(
            user_id=current_user["sub"],
            query=f"{payload.get('company', '')} {payload.get('reason', '')}",
        )["context"]
    try:
        return generate_resignation_letter_document(
            payload,
            template_id=payload.get("template_id", "formal-resignation"),
            knowledge_context=knowledge_context,
            personal_context=personal_context,
        )
    except ValueError as exc:
        raise AppValidationError(str(exc)) from exc


@app.post("/api/v1/resume/extract", tags=["generation"], responses=GENERATION_ERROR_RESPONSES)
async def extract_resume_upload(file: UploadFile = File(...)) -> dict:
    """Extract text from an uploaded CV PDF (multipart `file` field).

    Powers the frontend "upload CV" buttons in ATS review and job search:
    the extracted text fills the resume field, or — in job search — is sent
    back as `candidate_text` for semantic re-ranking. Public (no auth);
    logs filename/size/outcome, never file bytes. Max 5 MB, PDF only.
    """
    filename = file.filename or "upload.pdf"
    logger.info("resume extract upload: filename=%s content_type=%s", filename, file.content_type)
    if not filename.lower().endswith(".pdf"):
        raise AppValidationError("Only PDF files are accepted (filename must end with .pdf).")
    try:
        data = await file.read()
    except Exception as exc:
        logger.warning("resume extract read failed: filename=%s error=%s", filename, exc)
        raise AppValidationError(f"Could not read uploaded file '{filename}'.") from exc
    if not data:
        raise AppValidationError(f"Uploaded file '{filename}' is empty.")
    if len(data) > 5 * 1024 * 1024:
        raise AppValidationError(f"Uploaded file '{filename}' exceeds the 5 MB limit.")
    try:
        result = extract_text_from_pdf_bytes(data, source=filename)
    except ValueError as exc:
        raise AppValidationError(str(exc)) from exc
    if not result["text"]:
        raise AppValidationError(
            f"No readable text in '{filename}'. "
            "Scanned-image PDFs have no text layer — export a text-based PDF instead."
        )
    logger.info(
        "resume extract ok: filename=%s bytes=%d pages=%d chars=%d",
        filename,
        len(data),
        result["pages"],
        result["chars"],
    )
    return {"filename": filename, "text": result["text"], **{k: result[k] for k in ("pages", "chars")}}


@app.post("/api/v1/resume/check", tags=["generation"], responses=GENERATION_ERROR_RESPONSES)
def check_resume(body: ResumeCheckPayload) -> dict:
    payload = body.model_dump(exclude_unset=True)
    resume_text = payload.get("resume_text") or ""
    job_description = payload.get("job_description") or ""
    if not resume_text or not job_description:
        raise AppValidationError("Both resume_text and job_description are required.")
    # RD-04: combine the transparent ATS score with
    # semantic embedding similarity. The ATS score is
    # always present; semantic fields degrade to the
    # ATS-only fallback if embedding fails.
    result = check_resume_against_job(resume_text, job_description)
    result.update(check_resume_semantic(resume_text, job_description, ats_result=result))
    return result


@app.get("/api/v1/jobs/search", tags=["jobs"], responses=GENERATION_ERROR_RESPONSES)
def search_jobs_route(
    query: str = Query(..., min_length=1, max_length=200),
    location: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1, le=100),
    limit: int = Query(default=5, ge=1, le=50),
    candidate_text: str | None = Query(default=None, max_length=20_000),
    radius_km: int | None = Query(default=None, ge=0, le=200),
    published_since_days: int | None = Query(
        default=None,
        ge=0,
        le=100,
        description="Maximum posting age in days. Defaults to JOB_DEFAULT_RECENCY_DAYS (30) for every provider.",
    ),
    include_old: bool = Query(default=False, description="Disable the recency filter entirely."),
    include_applied: bool = Query(
        default=False,
        description="Signed-in users: also list jobs already in the tracker (annotated with their status).",
    ),
    work_time: str | None = Query(default=None, max_length=20),
    contract_type: str | None = Query(default=None, max_length=20),
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    normalized_location = (location or "").strip() or None
    try:
        options = JobSearchOptions(
            radius_km=radius_km,
            published_since_days=published_since_days,
            work_time=work_time,
            contract_type=contract_type,
        )
        # Signed-in users do not see jobs they already applied to (or track)
        # unless they ask for them; anonymous searches are unaffected.
        exclude = None
        applied_scope = ""
        status_lookup = None
        if current_user is not None:
            if include_applied:
                status_lookup = application_tracker.status_by_job(current_user["sub"])
            else:
                exclude, applied_scope = application_tracker.job_match_filter(current_user["sub"])
        payload = search_jobs(
            query=query,
            location=normalized_location,
            page=page,
            limit=limit,
            options=options,
            include_old=include_old,
            exclude=exclude,
            exclude_token=applied_scope,
        )
        if status_lookup is not None:
            for item in payload.get("results") or []:
                item["application_status"] = status_lookup(item)
    except ValueError as exc:
        raise AppValidationError(str(exc)) from exc
    except JobSearchFailed as exc:
        raise ExternalServiceError(
            "All configured job providers are temporarily unavailable.",
            internal=", ".join(f"{item['provider']}:{item['category']}" for item in exc.provider_errors),
        ) from exc
    except RuntimeError as exc:
        raise ConfigurationError(str(exc)) from exc

    # RD-04: when a candidate profile/CV text is
    # supplied, re-rank the results by combined
    # semantic + ATS keyword score.
    if candidate_text and candidate_text.strip():
        results = payload.get("results") or []
        payload["results"] = semantic_matching.rank_jobs(candidate_text, results)
        payload["ranked_by"] = "combined_semantic_ats"
    return payload
