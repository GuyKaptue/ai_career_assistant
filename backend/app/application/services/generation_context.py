"""Template + retrieved context for AI document generation.

Before this module the AI path of ``/documents/cv/generate`` and
``/documents/cover-letter/generate`` ignored both the selected template and the
retrieved (RAG) context: they were only appended to the deterministic fallback.
Now they reach the prompt, with two guarantees:

* **Only the template in the current request is used.** The backend is stateless
  about the selection; the guidance comes solely from ``template_id`` of THIS
  request. Retrieved personal chunks of type ``template`` are dropped unless
  they belong to the selected template, so older selections cannot leak in.
* Retrieved text is untrusted data: sanitized, bounded and placed in the shared
  REFERENCE CONTEXT block by the prompt builders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final

from app.application.services.career_prompts import sanitize_untrusted, truncate_text
from app.application.services.context_budget import build_bounded_context
from app.application.services.document_retrieval import MAX_RETRIEVAL_CONTEXT_CHARS
from app.application.services.tailoring_pipeline import DEFAULT_LETTER_STYLE, LETTER_STYLE
from app.core.errors import AppError
from app.domain.templates.template_registry import TemplateRegistry

logger = logging.getLogger(__name__)

MAX_REFERENCE_CHARS: Final = 2400
PERSONAL_BUDGET: Final = MAX_RETRIEVAL_CONTEXT_CHARS


@dataclass(frozen=True)
class ResolvedTemplate:
    """The template to render with (always a built-in id) plus the guidance for the prompt."""

    render_template_id: str
    guidance: str
    selected_id: str
    source: str  # "builtin" | "user"


def resolve_template(
    user_id: str | None, template_id: str | None, document_type: str, registry: TemplateRegistry | None = None
) -> ResolvedTemplate | None:
    """Resolve ``template_id`` (built-in, or one of the user's own) or ``None`` when unknown.

    A user template renders with its ``base_template_id`` (falling back to the default
    built-in for its kind) and contributes its name, structure and tone as guidance.
    """
    if not template_id:
        template_id = {"cv": "professional", "cover_letter": "classic-letter", "resignation": "formal-resignation"}.get(
            document_type, "professional"
        )
    reg = registry or TemplateRegistry()
    builtin = reg.get(template_id, document_type)
    if builtin is not None:
        layout = str(builtin.metadata.get("layout", ""))
        parts = [f"Template: {builtin.name} — {builtin.description}"]
        if layout:
            parts.append(f"Layout style: {layout}.")
        if document_type == "cover_letter":
            count, tone = LETTER_STYLE.get(layout, DEFAULT_LETTER_STYLE)
            parts.append(f"Use exactly {count} paragraphs; tone: {tone}.")
        return ResolvedTemplate(builtin.id, " ".join(parts), builtin.id, "builtin")
    if not user_id:
        return None
    from app.application.services.template_service import UserTemplateNotFound, get_template_service

    service = get_template_service()
    if not service.user_owns_template(user_id, document_type, template_id):
        return None
    try:
        ctx = service.context_for(user_id, document_type, template_id)
    except UserTemplateNotFound:
        return None
    own = service._templates.get(template_id)  # noqa: SLF001 - same package, read-only
    base = own.base_template_id if own and own.base_template_id else None
    fallback = {"cv": "professional", "cover_letter": "classic-letter"}.get(document_type, "professional")
    parts = [f"Template: {ctx.name} (your own template)."]
    if ctx.structure_type:
        parts.append(f"Structure: {ctx.structure_type}.")
    if ctx.tone:
        parts.append(f"Tone: {ctx.tone}.")
    if document_type == "cover_letter" and ctx.paragraphs:
        parts.append(f"Use exactly {ctx.paragraphs} paragraphs.")
    return ResolvedTemplate(base or fallback, " ".join(parts), template_id, "user")


def personal_context_for_generation(user_id: str | None, query: str, selected_template_id: str, retrieval: Any) -> str:
    """The user's relevant documents as bounded text, minus every template but the selected one."""
    if not user_id or not query.strip():
        return ""
    try:
        rows = retrieval.retrieve(user_id=user_id, query=query)
    except (AppError, RuntimeError, ValueError, OSError):
        logger.info("generation.retrieval_failed")
        return ""
    kept = [r for r in rows if r.get("document_type") != "template" or r.get("document_id") == selected_template_id]
    return build_bounded_context(
        kept,
        PERSONAL_BUDGET,
        attribution=lambda item: (
            f"[Document: {item['document_id']} | {item['document_type']} | {item['similarity']:.2f}]"
        ),
    )


def reference_context(knowledge_context: str, personal_context: str) -> str:
    """Sanitized, bounded reference text for the prompt builders (data, never instructions)."""
    joined = "\n\n".join(part for part in (knowledge_context, personal_context) if part and part.strip())
    text, _ = truncate_text(sanitize_untrusted(joined).strip(), MAX_REFERENCE_CHARS)
    return text
