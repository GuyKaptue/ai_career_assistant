"""Resolve a chat-supplied job into a validated position (sub-step 3 wrapper).

Chat path accepts html / text / pdf only — never images (no OCR), DOCX or
ZIP. Every failure maps to a ResolvedJob status; mock transports only.
Privacy: no URL path, query, page text or CV text is ever logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import httpx

from app.application.services import position_extraction as px
from app.application.services.chat_input import has_hiring_phrase, job_signals
from app.core.errors import ConfigurationError, ExternalServiceError, ValidationError
from app.domain.positions.models import Position

logger = logging.getLogger(__name__)

CHAT_ALLOWED_KINDS: Final = frozenset({"html", "text", "pdf"})

#: Signals that only prove the page has a headline — never enough on their own.
_TITLE_ONLY_SIGNALS: Final = frozenset({"title_line"})

#: A fetched page needs at least this many non-title signals to count as a posting.
_MIN_PAGE_SIGNALS: Final = 2

_LOGIN_WALL_MARKERS: Final = (
    "sign in to view",
    "log in to view",
    "login to view",
    "create an account to view",
    "please log in",
    "please sign in",
    "members only",
    "anmelden, um",
    "melde dich an",
    "connectez-vous pour voir",
    "veuillez vous connecter",
)
_NOT_A_JOB_MARKERS: Final = (
    "404 not found",
    "page not found",
    "cookie policy",
    "privacy policy",
    "terms of service",
    "all rights reserved",
)


@dataclass(frozen=True)
class ResolvedJob:
    """Outcome of resolving one chat-supplied job URL or pasted text."""

    status: str
    position: Position | None = None
    final_url: str | None = None
    detail: str | None = None


def _looks_like_login_wall(text: str) -> bool:
    return any(m in text.casefold() for m in _LOGIN_WALL_MARKERS)


def _looks_like_not_a_job(text: str) -> bool:
    """Kept for the pasted-text path: pasted text is never rejected by signals.

    Only the length check applies there (too short / too long), because the
    user explicitly pasted the text as a job description.
    """
    return False


def _page_is_not_a_job(position: Position) -> bool:
    """Whether a fetched page is not a job posting.

    * a page with JSON-LD job markup is trusted (it is a job);
    * otherwise the page needs at least two non-title job signals;
    * the CV veto still applies: a page that only looks like a CV is not a
      posting unless an employer hiring phrase proves otherwise.
    """
    if position.extracted_with == "json_ld":
        return False
    signals = job_signals(position.description or "")
    strong = [signal for signal in signals if signal not in _TITLE_ONLY_SIGNALS]
    if len(strong) >= _MIN_PAGE_SIGNALS:
        is_cv = "cv_markers" in signals
        if not (is_cv and not has_hiring_phrase(position.description or "")):
            return False
    return True


def _disabled_ocr(content: bytes) -> str:
    """Explicitly disabled OCR for the chat path: images never yield text."""
    return ""


def _unsupported(kind: str) -> ResolvedJob:
    return ResolvedJob(status="unsupported_type", detail=f"Content type '{kind}' is not supported in chat.")


def resolve_job_from_text(text: str, *, url: str | None = None) -> ResolvedJob:
    """Resolve pasted job text (chat path: html/text only, never OCR)."""
    try:
        result = px.extract_from_text(text, url=url)
    except ValidationError as exc:
        msg = exc.message.casefold()
        if "too short" in msg:
            return ResolvedJob(status="not_a_job_posting", detail=exc.message)
        if "too long" in msg:
            return ResolvedJob(status="too_large", detail=exc.message)
        return ResolvedJob(status="invalid_url" if url else "not_a_job_posting", detail=exc.message)
    position = result.positions[0]
    if _looks_like_login_wall(position.description):
        return ResolvedJob(status="login_wall", position=position, final_url=url)
    logger.info("job_resolved status=ok kind=text")
    return ResolvedJob(status="ok", position=position, final_url=url)


def resolve_job_from_url(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    resolver: px.Resolver | None = None,
) -> ResolvedJob:
    """Resolve a job URL; tests inject a mock transport, production passes ``None``."""
    try:
        content, _ctype, final_url = px.fetch_url(url, resolver=resolver, transport=transport)
    except ValidationError as exc:
        msg = exc.message.casefold()
        if "too large" in msg:
            return ResolvedJob(status="too_large", detail=exc.message)
        if "redirected too many times" in msg:
            return ResolvedJob(status="fetch_failed", detail=exc.message)
        return ResolvedJob(status="invalid_url", detail=exc.message)
    except ExternalServiceError as exc:
        return ResolvedJob(status="fetch_failed", detail=exc.message)
    if not content:
        return ResolvedJob(status="fetch_failed", detail="The page is empty.")
    try:
        kind = px.detect_kind(content)
    except ValidationError as exc:
        return ResolvedJob(status="unsupported_type", detail=exc.message)
    if kind == "zip":
        return ResolvedJob(status="unsupported_type", detail="The URL does not point to a job posting page.")
    if kind not in CHAT_ALLOWED_KINDS:
        return _unsupported(kind)
    try:
        position = px._extract_single(content, kind, source="url", url=final_url, ocr=_disabled_ocr)
    except ValidationError as exc:
        msg = exc.message.casefold()
        if "too large" in msg or "too long" in msg:
            return ResolvedJob(status="too_large", detail=exc.message)
        return ResolvedJob(status="not_a_job_posting", detail=exc.message)
    except (ConfigurationError, ExternalServiceError) as exc:
        return ResolvedJob(status="fetch_failed", detail=exc.message)
    if _looks_like_login_wall(position.description):
        return ResolvedJob(status="login_wall", position=position, final_url=final_url)
    if _page_is_not_a_job(position):
        return ResolvedJob(status="not_a_job_posting", position=position, final_url=final_url)
    logger.info("job_resolved status=ok kind=%s", kind)
    return ResolvedJob(status="ok", position=position, final_url=final_url)
