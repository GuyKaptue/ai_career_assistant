"""Synthetic sample documents and PNG previews for the template gallery.

Samples use an invented persona only; no user data is involved. PNG previews are drawn
with Pillow from the same theme the PDF/DOCX/HTML renderers use, so a card's image
matches what the user will download.
"""

from __future__ import annotations

import textwrap
from functools import lru_cache
from io import BytesIO

from app.infrastructure.document_export.styled import (
    Parsed,
    Theme,
    parse_content,
    render_styled_docx,
    render_styled_html,
    render_styled_pdf,
)

_SAMPLE: dict[str, dict[str, str]] = {
    "en": {
        "role": "Senior Software Engineer",
        "exp": "Professional Experience",
        "edu": "Education",
        "skills": "Skills",
        "dear": "Dear Hiring Manager,",
        "bye": "Sincerely,",
    },
    "de": {
        "role": "Senior Softwareentwickler",
        "exp": "Berufserfahrung",
        "edu": "Ausbildung",
        "skills": "Kenntnisse",
        "dear": "Sehr geehrte Damen und Herren,",
        "bye": "Mit freundlichen Grüßen",
    },
    "fr": {
        "role": "Ingénieur logiciel senior",
        "exp": "Expérience professionnelle",
        "edu": "Formation",
        "skills": "Compétences",
        "dear": "Madame, Monsieur,",
        "bye": "Cordialement,",
    },
}


def sample_content(document_type: str, locale: str) -> str:
    s = _SAMPLE.get(locale, _SAMPLE["en"])
    if document_type == "cover_letter":
        return (
            "Alex Example\n"
            f"{s['dear']}\n\n"
            "I am excited to apply for the Senior Software Engineer role at Example Corp. "
            "I build reliable data products and enjoy working with small, focused teams.\n\n"
            "In my current role I led a migration that cut processing time by half while keeping the platform stable. "
            "I would welcome the opportunity to discuss how this experience fits your needs.\n\n"
            f"{s['bye']}\nAlex Example"
        )
    return (
        f"Alex Example\n\n{s['role']}\n\n{s['role']}\n\n"
        "Engineer focused on dependable backend systems and clear communication.\n\n"
        f"{s['exp']}\n- {s['role']} | Example Corp\n  • Led a platform migration across three services\n"
        "  • Mentored four engineers and introduced code review guidelines\n- Software Engineer | Sample Labs\n"
        "  • Built an internal reporting tool used by 200 colleagues\n\n"
        f"{s['edu']}\n- BSc Computer Science | Example University\n\n"
        f"{s['skills']}\n- Python\n- SQL\n- Distributed systems\n- Technical writing"
    )


def _pil_font(size: int, bold: bool = False):
    from PIL import ImageFont

    for name in ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def render_png(content: str, document_type: str, theme: Theme, width: int = 600) -> bytes:
    if theme.columns == 2 and document_type == "cv":
        from app.infrastructure.document_export.styled_columns import png_two_column

        return png_two_column(content, theme, width)
    from PIL import Image, ImageDraw

    height = int(width * 1.414)
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    p: Parsed = parse_content(content, document_type)
    m = int(width * 0.07)
    y = 0
    band = theme.header == "band"
    head_h = int(width * 0.2) if band else int(width * 0.16)
    if band:
        d.rectangle([0, 0, width, head_h], fill=theme.accent)
    name_font, small, body_font = (
        _pil_font(int(width * 0.05), True),
        _pil_font(int(width * 0.026)),
        _pil_font(int(width * 0.024)),
    )
    from app.infrastructure.document_export.styled_columns import on_color

    band_fg = on_color(theme.accent) if theme.palette else "white"
    fg = band_fg if band else theme.heading_color

    def x_for(text: str, font) -> int:
        w = d.textlength(text, font=font)
        return int((width - w) / 2) if theme.header == "center" else m

    y = int(width * 0.05)
    d.text((x_for(p.name, name_font), y), p.name, font=name_font, fill=fg)
    y += int(width * 0.07)
    if p.subtitle:
        d.text((x_for(p.subtitle, small), y), p.subtitle, font=small, fill=band_fg if band else "#666666")
    y = head_h + int(width * 0.03)
    if not band:
        d.line([m, head_h - 4, width - m, head_h - 4], fill=theme.accent, width=3)
    line_h = int(width * 0.034) if theme.compact else int(width * 0.04)
    for sec in p.sections:
        if sec.heading:
            text = sec.heading.upper() if theme.heading == "caps" else sec.heading
            hx = m + (12 if theme.heading == "bar" else 0)
            if theme.heading == "bar":
                d.rectangle([m, y, m + 5, y + int(width * 0.03)], fill=theme.accent)
            d.text((hx, y), text, font=_pil_font(int(width * 0.03), True), fill=theme.heading_color)
            y += int(width * 0.04)
            if theme.heading == "rule":
                d.line([m, y - 4, width - m, y - 4], fill=theme.accent, width=2)
        for ln in sec.lines:
            if y > height - m:
                break
            if not ln.strip():
                y += line_h // 3
                continue
            text = ln.strip().lstrip("-•* ").strip()
            indent = m + (28 if ln.startswith("  ") else 10 if ln.lstrip()[:1] in "-•*" else 0)
            if indent > m:
                d.ellipse([indent - 9, y + 7, indent - 4, y + 12], fill="#555555")
            max_chars = max(20, int((width - m - indent) / (width * 0.0135)))
            for part in textwrap.wrap(text, max_chars) or [""]:
                if y > height - m:
                    break
                d.text((indent, y), part, font=body_font, fill="#222222")
                y += line_h
        y += int(width * 0.015)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


SAMPLE_FORMATS = {
    "png": "image/png",
    "pdf": "application/pdf",
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@lru_cache(maxsize=512)
def render_sample(
    template_id: str,
    document_type: str,
    locale: str,
    fmt: str,
    metadata_key: tuple[tuple[str, str], ...],
    theme_id: str = "",
    country: str = "",
    sidebar: str = "",
) -> bytes:
    from app.infrastructure.document_export.styled import theme_from_template

    theme = theme_from_template(
        dict(metadata_key), document_type, theme_id=theme_id, country=country, sidebar=sidebar, locale=locale
    )
    content = sample_content(document_type, locale)
    title = f"Sample {template_id}"
    if fmt == "png":
        return render_png(content, document_type, theme)
    if fmt == "pdf":
        return render_styled_pdf(title, content, document_type, theme)
    if fmt == "docx":
        return render_styled_docx(title, content, document_type, theme)
    return render_styled_html(title, content, document_type, theme).encode("utf-8")
