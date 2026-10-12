from __future__ import annotations

from html import escape
from io import BytesIO

from app.domain.templates.template_registry import TemplateRegistry

# BE-05 resignation tone selector (PROJ §5.4): formal, warm, or brief.
RESIGNATION_TONES: tuple[str, ...] = ("formal", "warm", "brief")
DEFAULT_RESIGNATION_TONE = "formal"


def _render_summary(document: dict) -> str:
    summary = document.get("summary", "")
    target_role = document.get("target_role", "")
    return f"{target_role}\n\n{summary}".strip()


def _render_experience(document: dict) -> str:
    experience = document.get("experience", [])
    if not experience:
        return "No experience entries provided."

    lines = ["Professional Experience"]
    for job in experience:
        role = job.get("role", "Role")
        company = job.get("company", "Company")
        lines.append(f"- {role} | {company}")
        for highlight in job.get("highlights", [])[:3]:
            lines.append(f"  • {highlight}")
    return "\n".join(lines)


def _render_education(document: dict) -> str:
    education = document.get("education", [])
    if not education:
        return "Education\n- Not provided"

    lines = ["Education"]
    for entry in education:
        school = entry.get("school", "School")
        degree = entry.get("degree", "Degree")
        lines.append(f"- {degree} | {school}")
    return "\n".join(lines)


def _render_skills(document: dict) -> str:
    skills = document.get("skills", [])
    if not skills:
        return "Skills\n- Not provided"
    return "Skills\n- " + "\n- ".join(str(skill) for skill in skills)


def _render_cover_letter(document: dict) -> str:
    name = document.get("name", "Candidate")
    company = document.get("company", "Target Company")
    role = document.get("target_role", "role")
    summary = document.get("summary", "")
    return (
        f"{name}\n"
        f"Dear Hiring Manager,\n\n"
        f"I am excited to apply for the {role} position at {company}. {summary}\n\n"
        "I would welcome the opportunity to contribute and discuss how my experience aligns with your needs.\n\n"
        "Sincerely,\n"
        f"{name}"
    )


def _render_resignation_letter(document: dict) -> str:
    name = document.get("name", "Candidate")
    company = document.get("company", "Target Company")
    role = document.get("role", "your role")
    last_working_day = document.get("last_working_day", "[last working day]")
    notice_period = document.get("notice_period", "the required notice period")
    reason = document.get("reason", "pursuing a new opportunity")
    tone = str(document.get("tone") or DEFAULT_RESIGNATION_TONE).strip().lower()
    if tone not in RESIGNATION_TONES:
        tone = DEFAULT_RESIGNATION_TONE

    if tone == "brief":
        return (
            f"{name}\n\n"
            f"I am writing to resign from {company}, with my final day on {last_working_day}.\n\n"
            f"This decision is based on {reason}. I will ensure a complete handover "
            f"over the remaining {notice_period}.\n\n"
            "Sincerely,\n"
            f"{name}"
        )

    if tone == "warm":
        return (
            f"{name}\n\n"
            "Dear Hiring Manager,\n\n"
            f"Please accept my resignation from {company}, effective {last_working_day}. "
            f"Serving as {role} has been a genuine pleasure, and I am thankful for the "
            "support, trust, and opportunities I have received.\n\n"
            f"This decision is based on {reason}. Over the remaining {notice_period} I will "
            "do everything I can to ensure a smooth and well-prepared transition.\n\n"
            "With sincere appreciation,\n"
            f"{name}"
        )

    # formal (default)
    return (
        f"{name}\n\n"
        "Dear Hiring Manager,\n\n"
        f"Please accept this letter as formal notice of my resignation from {company}. "
        f"My final day of employment will be {last_working_day}. I have appreciated "
        f"the opportunity to contribute in my role as {role} and to work with the "
        "team over this period.\n\n"
        f"This decision is based on {reason}. I am grateful for the support, "
        f"guidance, and opportunities provided during my time here. I will do my best "
        f"to support a smooth transition over the remaining {notice_period}.\n\n"
        "Thank you for your understanding and for the opportunity to be part of the "
        "organization.\n\n"
        "Sincerely,\n"
        f"{name}"
    )


def _render_knowledge_guidance(knowledge_context: str) -> str:
    """Render retrieved knowledge as reference-only guidance.

    RD-03 acceptance criterion: retrieved knowledge must
    never override user-provided information, so the
    guidance is appended after the user's content under
    an explicit notice.
    """
    return "\n\nCareer guidance (reference only — your provided " f"information takes precedence):\n{knowledge_context}"


def _render_personal_guidance(personal_context: str) -> str:
    """Render retrieved personal documents as reference-only context.

    RD-05 acceptance criterion: retrieved personal documents
    must never override user-provided information, so the
    context is appended after the user's content under an
    explicit notice with per-chunk source attribution.
    """
    return (
        "\n\nRelevant personal history (reference only — your provided "
        f"information takes precedence):\n{personal_context}"
    )


def generate_document_content(
    document: dict,
    template_id: str = "professional",
    document_type: str = "cv",
    knowledge_context: str | None = None,
    personal_context: str | None = None,
) -> dict:
    registry = TemplateRegistry()
    template = registry.get(template_id, document_type)
    if template is None:
        raise ValueError(f"Unknown template '{template_id}' for document type '{document_type}'.")

    if document_type == "cover_letter":
        body = _render_cover_letter(document)
    elif document_type == "resignation":
        body = _render_resignation_letter(document)
    else:
        body = "\n\n".join(
            [
                document.get("name", "Candidate"),
                document.get("target_role", "Target Role"),
                _render_summary(document),
                _render_experience(document),
                _render_education(document),
                _render_skills(document),
            ]
        )

    if knowledge_context:
        body += _render_knowledge_guidance(knowledge_context)
    if personal_context:
        body += _render_personal_guidance(personal_context)

    metadata = {
        "template_name": template.name,
        "description": template.description,
        "supported_locales": list(template.supported_locales),
    }
    if document_type == "resignation":
        metadata["tone"] = str(document.get("tone") or DEFAULT_RESIGNATION_TONE).strip().lower()

    return {
        "template_id": template.id,
        "document_type": template.document_type,
        "content": body,
        "metadata": metadata,
    }


def generate_cv_document(
    document: dict,
    template_id: str = "professional",
    knowledge_context: str | None = None,
    personal_context: str | None = None,
) -> dict:
    return generate_document_content(
        document,
        template_id=template_id,
        document_type="cv",
        knowledge_context=knowledge_context,
        personal_context=personal_context,
    )


def generate_cover_letter_document(
    document: dict,
    template_id: str = "classic-letter",
    knowledge_context: str | None = None,
    personal_context: str | None = None,
) -> dict:
    return generate_document_content(
        document,
        template_id=template_id,
        document_type="cover_letter",
        knowledge_context=knowledge_context,
        personal_context=personal_context,
    )


def generate_resignation_letter_document(
    document: dict,
    template_id: str = "formal-resignation",
    knowledge_context: str | None = None,
    personal_context: str | None = None,
) -> dict:
    return generate_document_content(
        document,
        template_id=template_id,
        document_type="resignation",
        knowledge_context=knowledge_context,
        personal_context=personal_context,
    )


def render_document_to_html(document: dict) -> str:
    title = escape(str(document.get("title") or "Document"))
    content = escape(str(document.get("content") or "")).replace("\n", "<br />")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        '<head><meta charset="utf-8" /><title>{title}</title></head>\n'
        "<body>\n"
        "<h1>{title}</h1>\n"
        "<div>{content}</div>\n"
        "</body>\n"
        "</html>\n"
    ).format(title=title, content=content)


def render_document_to_pdf(document: dict) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    style_sheet = getSampleStyleSheet()
    styles = [style_sheet["Title"], style_sheet["BodyText"]]
    story = [Paragraph(str(document.get("title") or "Document"), styles[0]), Spacer(1, 12)]

    for line in str(document.get("content") or "").splitlines() or [""]:
        if not line.strip():
            story.append(Spacer(1, 6))
            continue
        story.append(Paragraph(line, styles[1]))

    doc.build(story)
    return buffer.getvalue()


def render_document_to_docx(document: dict) -> bytes:
    from docx import Document

    if str(document.get("document_type") or "") == "cover_letter" or str(document.get("template_id") or "").startswith(
        "formal-"
    ):
        try:
            from app.infrastructure.document_export.cover_letter_docx import (
                render_cover_letter_to_docx,
            )

            return render_cover_letter_to_docx(document)
        except ImportError:
            pass

    doc = Document()
    doc.add_heading(str(document.get("title") or "Document"), level=1)

    content = str(document.get("content") or "")
    if content:
        for line in content.splitlines():
            if line.strip():
                doc.add_paragraph(line)
    else:
        doc.add_paragraph("No content available.")

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
