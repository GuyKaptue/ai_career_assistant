from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extract_text_from_pdf_bytes(data: bytes, *, source: str = "<upload>") -> dict:
    """Extract text from in-memory PDF bytes (upload path).

    Returns a debug-friendly dict with ``text`` plus per-page character
    counts. File bytes are logged by size only — never by content.
    """
    logger.info("extract start: source=%s bytes=%d", source, len(data))
    try:
        from io import BytesIO

        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        logger.warning("extract failed: source=%s error=%s: %s", source, type(exc).__name__, exc)
        raise ValueError(f"Could not read PDF '{source}': {exc}") from exc
    pages: list[str] = []
    page_chars: list[int] = []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # one bad page must not kill the upload
            logger.warning("extract page %d failed: source=%s error=%s", index, source, exc)
            text = ""
        pages.append(text)
        page_chars.append(len(text))
    logger.debug(
        "extract pages: source=%s pages=%d chars_per_page=%s",
        source,
        len(pages),
        page_chars,
    )
    text = " ".join(" ".join(pages).split())
    logger.info(
        "extract done: source=%s pages=%d total_chars=%d empty=%s",
        source,
        len(pages),
        len(text),
        not text,
    )
    if not text:
        logger.warning("extract empty: source=%s — scanned-image PDFs have no text layer", source)
    return {"text": text, "pages": len(pages), "chars": len(text), "chars_per_page": page_chars}


def extract_resume_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract human-readable text from a CV PDF for ATS and resume-analysis workflows."""
    path = Path(pdf_path)
    logger.debug("extract from path: %s", path)
    if not path.exists():
        logger.warning("extract path missing: %s", path)
        raise FileNotFoundError(f"CV PDF not found: {path}")

    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        logger.debug("extract page %d: path=%s chars=%d", index, path.name, len(text))
        if text:
            pages.append(text)

    if not pages:
        logger.warning("extract empty: path=%s — scanned-image PDFs have no text layer", path)
        return ""

    text = "\n".join(pages)
    result = " ".join(text.split())
    logger.info("extract done: path=%s pages=%d total_chars=%d", path.name, len(pages), len(result))
    return result
