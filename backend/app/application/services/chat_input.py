"""Chat input analysis: validate, clean and classify the raw user input.

Pure and deterministic — no model call, no I/O. ``analyse_input`` turns one
user message (plus any explicitly supplied job URL / job text) into an
:class:`InputAnalysis` that the intent classifier and the routing layer
consume.

Privacy: nothing in this module logs message, job or CV text — only lengths,
counts, kinds and rule ids.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Final
from urllib.parse import urlsplit

from app.domain.cv.skill_vocabulary import SKILL_VOCABULARY

# --- Limits (Stage A). Over the limit the route answers 400; never truncate. ---
MESSAGE_MAX_CHARS: Final = 20_000
JOB_TEXT_MAX_CHARS: Final = 30_000
DOCUMENT_CONTEXT_MAX_CHARS: Final = 100_000

MAX_URLS: Final = 3

# Job-description detection: enough signals AND long enough AND at least one
# "strong" job marker (a hiring section header or an employment term) so a CV
# pasted by mistake (bullets + name line only) is never mistaken for a job.
JD_MIN_SIGNALS: Final = 3
JD_MIN_CHARS: Final = 400
JD_STRONG_SIGNALS: Final = frozenset({"section_words", "employment"})
SKILL_OVERLAP_MIN: Final = 2
INSTRUCTION_MAX_CHARS: Final = 300
#: A payload must be at least this long before we split a lead-in instruction off it.
INSTRUCTION_PAYLOAD_MIN: Final = 150
#: Over-long URLs are rejected (common practical cap, avoids pathological input).
MAX_URL_CHARS: Final = 2048

_ALLOWED_SCHEMES: Final = ("http://", "https://")
_REJECTED_SCHEMES: Final = ("javascript:", "data:", "file:", "ftp:", "vbscript:")

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_PUNCT: Final = ".,;:!?)]}>\"'"
# Control chars (keeping \t \n \r) plus zero-width / soft-hyphen characters.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u200c\u200d\u2060\ufeff\u00ad]")
_BULLET_RE = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+\S", re.MULTILINE)
_SENT_END_RE = re.compile(r"[:\n]|(?<=[.!?;])\s")

_SECTION_WORDS: Final = (
    "responsibilities",
    "requirements",
    "qualifications",
    "we offer",
    "about the role",
    "we are looking",
    "we're looking",
    "what you'll do",
    "what we offer",
    "your profile",
    "ideal candidate",
    "aufgaben",
    "anforderungen",
    "qualifikationen",
    "wir bieten",
    "ihr profil",
    "wir suchen",
    "deine aufgaben",
    "dein profil",
    "missions",
    "profil recherche",
    "nous offrons",
    "nous recherchons",
    "ce que nous offrons",
    "vos missions",
)
_CV_MARKERS: Final = (
    "experience",
    "education",
    "work history",
    "employment history",
    "curriculum vitae",
    "professional summary",
    "career summary",
    "skills",
    "summary",
)
#: Phrases only an employer writes in a posting. When one is present the
#: ``cv_markers`` veto is skipped: a job description that happens to contain
#: "Education"/"Languages"/"Skills" headers is still a JOB_DESCRIPTION.
_HIRING_PHRASES: Final = (
    "we offer",
    "we are looking",
    "we're looking",
    "what we offer",
    "wir bieten",
    "wir suchen",
    "nous offrons",
    "nous recherchons",
    "ce que nous offrons",
)
_EMPLOYMENT_WORDS: Final = (
    "full-time",
    "full time",
    "part-time",
    "vollzeit",
    "teilzeit",
    "cdi",
    "cdd",
    "m/w/d",
    "(f/h/x)",
    "(m/f/x)",
    "temps plein",
)
# Tokens that mark a lead-in as an instruction ("Match my CV with this job: …")
# rather than the opening line of a pasted posting.
_INSTRUCTION_TOKENS: Final = {
    "match",
    "tailor",
    "adapt",
    "find",
    "search",
    "compare",
    "check",
    "score",
    "fit",
    "write",
    "generate",
    "against",
    "cv",
    "resume",
    "letter",
    "cover",
    "suche",
    "finde",
    "anpasse",
    "passe",
    "adapte",
    "trouve",
    "ecrire",
    "redige",
    "recherche",
}
#: Pronoun/demonstrative markers that must accompany an instruction token. A
#: colon plus an action word alone ("Backend Engineer – Search: …") is a job
#: title, not an instruction.
_INSTRUCTION_PRONOUNS: Final = {
    "my",
    "this",
    "mein",
    "diese",
    "mon",
    "cette",
    "ce",
}


class InputKind(str, Enum):
    """What the message looks like before any intent classification."""

    JOB_URL = "job_url"
    JOB_DESCRIPTION = "job_description"
    QUESTION = "question"
    EMPTY = "empty"


@dataclass(frozen=True)
class InputAnalysis:
    """Result of :func:`analyse_input` — derived facts, never message text.

    ``job_text_candidate`` holds the pasted posting (or the part after a split
    instruction); ``instruction`` is the short lead-in around a URL/description.
    ``signals`` are the rule ids that fired, for the routing audit.
    """

    kind: InputKind
    urls: tuple[str, ...]
    job_url: str | None
    job_text_candidate: str | None
    instruction: str | None
    signals: list[str]
    length: int


_EN_MARKERS: Final = frozenset({"the", "and", "you", "for", "with", "this", "that", "our", "are", "will", "have"})
_DE_MARKERS: Final = frozenset({"der", "die", "das", "und", "ich", "nicht", "mit", "fur", "sie", "auch", "werden"})
_FR_MARKERS: Final = frozenset({"le", "la", "les", "et", "je", "vous", "nous", "est", "pour", "avec", "dans"})


def clean_text(text: str | None) -> str:
    """Normalise for analysis: NFKC, drop control/zero-width chars, collapse space.

    Newlines are kept (bullets and section headers depend on structure). The
    caller keeps the raw string for display; this cleaned form is what analysis
    runs on.
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = _CONTROL_RE.sub("", out)
    out = out.replace("\r\n", "\n").replace("\r", "\n")
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def detect_language(text: str | None, fallback: str = "en") -> str:
    """Best-effort en/de/fr detection; ``fallback`` (session language) breaks ties."""
    if fallback not in {"en", "de", "fr"}:
        fallback = "en"
    words = set(re.findall(r"[a-z]+", _fold(text or "")))
    if not words:
        return fallback
    scores = {
        "en": len(words & _EN_MARKERS),
        "de": len(words & _DE_MARKERS),
        "fr": len(words & _FR_MARKERS),
    }
    top = max(scores.values())
    if top == 0:
        return fallback
    tied = [lang for lang, score in scores.items() if score == top]
    return fallback if fallback in tied else tied[0]


def input_limits_error(
    message: str | None = None,
    job_text: str | None = None,
    document_context: str | None = None,
) -> str | None:
    """Return a clear over-limit message (route → 400) or ``None`` when in limits."""
    if message is not None and len(message) > MESSAGE_MAX_CHARS:
        return f"Message is too long ({len(message)} characters; limit {MESSAGE_MAX_CHARS})."
    if job_text is not None and len(job_text) > JOB_TEXT_MAX_CHARS:
        return f"Job text is too long ({len(job_text)} characters; limit {JOB_TEXT_MAX_CHARS})."
    if document_context is not None and len(document_context) > DOCUMENT_CONTEXT_MAX_CHARS:
        return (
            f"Attached document is too long ({len(document_context)} characters; limit {DOCUMENT_CONTEXT_MAX_CHARS})."
        )
    return None


def _has_word(low: str, phrase: str) -> bool:
    """Word-boundary match on folded text (never substring: ``missions`` ≠ ``submissions``)."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", low) is not None


def valid_http_url(raw: str | None) -> str | None:
    """Return a cleaned http(s) URL, or ``None`` for anything else.

    Accepts only ``http``/``https`` with a real host; explicitly rejects
    ``javascript:``, ``data:``, ``file:``, ``ftp:`` and ``vbscript:``.
    Also rejects embedded whitespace, credentials (``user:pass@``), bare
    schemes with no host, and over-long URLs.
    """
    candidate = (raw or "").strip().rstrip(_TRAILING_PUNCT)
    low = candidate.casefold()
    if any(low.startswith(bad) for bad in _REJECTED_SCHEMES):
        return None
    if not low.startswith(_ALLOWED_SCHEMES):
        return None
    if len(candidate) > MAX_URL_CHARS:
        return None
    if re.search(r"\s", candidate):
        return None
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    if not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    return candidate


def _fold(text: str) -> str:
    """Casefold and strip accents so de/fr keywords match regardless of umlauts."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in unicodedata.normalize("NFD", folded) if not unicodedata.combining(ch))


def _extract_urls(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _URL_RE.findall(text):
        candidate = valid_http_url(match)
        if candidate:
            found.append(candidate)
        if len(found) >= MAX_URLS:
            break
    return tuple(found)


def _count_bullets(text: str) -> int:
    return len(_BULLET_RE.findall(text))


def _has_title_line(text: str) -> bool:
    """A short, non-sentence line among the first three — a title/company line."""
    for line in [ln.strip() for ln in text.splitlines() if ln.strip()][:3]:
        words = line.split()
        if 1 <= len(words) <= 12 and not re.search(r"[.!?;:]$", line) and re.search(r"[A-Za-zÀ-ÿ]", line):
            return True
    return False


_SKILL_PATTERNS: Final = {skill: re.compile(rf"(?<!\w){re.escape(skill)}(?!\w)") for skill in SKILL_VOCABULARY}


def _skills_in(text: str) -> set[str]:
    """Skill tokens present in ``text``, matched on word boundaries (never substrings)."""
    folded = _fold(text)
    return {skill for skill, pattern in _SKILL_PATTERNS.items() if pattern.search(folded)}


def _job_description_signals(text: str, cv_text: str | None = None) -> list[str]:
    """Rule ids for job-description-ness. Deterministic; no model involved."""
    low = _fold(text)
    signals: list[str] = []
    if any(_has_word(low, word) for word in _SECTION_WORDS):
        signals.append("section_words")
    if _count_bullets(text) >= 4:
        signals.append("bullets")
    if any(_has_word(low, word) for word in _EMPLOYMENT_WORDS):
        signals.append("employment")
    if _has_title_line(text):
        signals.append("title_line")
    if any(_has_word(low, word) for word in _CV_MARKERS):
        signals.append("cv_markers")
    if cv_text and len(_skills_in(text) & _skills_in(cv_text)) >= SKILL_OVERLAP_MIN:
        signals.append("skill_overlap")
    return signals


def has_hiring_phrase(text: str) -> bool:
    """True when the text contains an employer hiring phrase ("we offer", ...).

    A hiring phrase proves the text is a posting that merely contains CV-like
    section headers, so the CV veto does not apply to it.
    """
    folded = _fold(text or "")
    return any(_has_word(folded, phrase) for phrase in _HIRING_PHRASES)


def job_signals(text: str, cv_text: str | None = None) -> list[str]:
    """Public view of the job-description signal ids (rule ids only, no content).

    Used by the job-resolution layer to decide whether a fetched page is a job
    posting. Deterministic; never raises.
    """
    return _job_description_signals(text or "", cv_text)


def _first_sentence_break(text: str, limit: int = INSTRUCTION_MAX_CHARS) -> int:
    """Index just after the first sentence/colon/newline break, or ``-1``."""
    match = _SENT_END_RE.search(text)
    if match and match.start() < limit:
        return match.end()
    return -1


def _first_sentence(text: str) -> str | None:
    break_at = _first_sentence_break(text)
    fragment = text[:break_at] if break_at != -1 else text[:INSTRUCTION_MAX_CHARS]
    fragment = fragment.strip().strip(":.;!?").strip()
    return fragment or None


def _looks_like_instruction(fragment: str) -> bool:
    """A lead-in is an instruction only with an action token AND a pronoun marker.

    ``"Match my CV with this job"`` splits; ``"Backend Engineer – Search"``
    has an action word (search) but no pronoun, so a colon alone never splits
    a title off the payload.
    """
    words = set(_fold(fragment).split())
    return bool(words & _INSTRUCTION_TOKENS) and bool(words & _INSTRUCTION_PRONOUNS)


def split_instruction(text: str) -> tuple[str | None, str]:
    """Split ``"<instruction>: <long posting>"`` into ``(instruction, payload)``.

    Only splits when the lead-in looks like an instruction and the payload is a
    substantial posting; a bare posting is returned untouched with no
    instruction (``None``).
    """
    break_at = _first_sentence_break(text)
    if break_at != -1:
        head = text[:break_at]
        # The lead-in must be an explicit "<instruction>:" — a bare title line
        # followed by a newline (e.g. "Backend Engineer – Search Team") never splits.
        if ":" not in head:
            return None, text
        prefix = head.strip().strip(":.;!?").strip()
        payload = text[break_at:].strip()
        if prefix and len(payload) >= INSTRUCTION_PAYLOAD_MIN and _looks_like_instruction(prefix):
            return prefix[:INSTRUCTION_MAX_CHARS], payload
    return None, text


def _surrounding_instruction(text: str, url: str) -> str | None:
    """The short lead-in around a URL (``"Match my CV with this job:"``)."""
    index = text.find(url)
    if index == -1:
        return _first_sentence(text)
    around = f"{text[:index]} {text[index + len(url):]}".strip()
    return _first_sentence(around)


def analyse_input(
    message: str | None = None,
    job_url: str | None = None,
    job_text: str | None = None,
    cv_text: str | None = None,
) -> InputAnalysis:
    """Classify one chat input into an :class:`InputAnalysis`.

    Deterministic and side-effect free. Precedence: an explicitly supplied
    ``job_url``/``job_text`` (from the payload) wins; otherwise the message is
    analysed for a pasted job description first (a long posting with an
    embedded reference link stays a description), then for a bare URL, else it
    is a plain question (or empty). Never raises.
    """
    cleaned = clean_text(message)

    if job_url:
        resolved = valid_http_url(job_url)
        if resolved:
            instruction = (
                _surrounding_instruction(cleaned, resolved) if resolved in cleaned else _first_sentence(cleaned)
            )
            return InputAnalysis(
                kind=InputKind.JOB_URL,
                urls=(resolved,),
                job_url=resolved,
                job_text_candidate=clean_text(job_text) or None,
                instruction=instruction,
                signals=["explicit_job_url"],
                length=len(cleaned),
            )

    if job_text:
        payload = clean_text(job_text)
        if payload:
            return InputAnalysis(
                kind=InputKind.JOB_DESCRIPTION,
                urls=(),
                job_url=None,
                job_text_candidate=payload,
                instruction=_first_sentence(cleaned),
                signals=["explicit_job_text"],
                length=len(cleaned),
            )

    if not cleaned:
        return InputAnalysis(
            kind=InputKind.EMPTY,
            urls=(),
            job_url=None,
            job_text_candidate=None,
            instruction=None,
            signals=["empty"],
            length=0,
        )

    signals = _job_description_signals(cleaned, cv_text)
    if job_url and valid_http_url(job_url) is None and "invalid_explicit_url" not in signals:
        signals = [*signals, "invalid_explicit_url"]
    strong = bool(JD_STRONG_SIGNALS.intersection(signals))
    is_cv = "cv_markers" in signals
    has_hiring_phrase = any(_has_word(_fold(cleaned), phrase) for phrase in _HIRING_PHRASES)
    # A CV pasted by mistake is never a job — unless an employer hiring phrase
    # ("We offer"/"Wir bieten"/…) proves the text is a posting that merely
    # contains CV-like section headers.
    if (
        len(cleaned) >= JD_MIN_CHARS
        and len(signals) >= JD_MIN_SIGNALS
        and strong
        and not (is_cv and not has_hiring_phrase)
    ):
        instruction, payload = split_instruction(cleaned)
        jd_urls = _extract_urls(payload)
        return InputAnalysis(
            kind=InputKind.JOB_DESCRIPTION,
            urls=jd_urls,
            job_url=jd_urls[0] if jd_urls else None,
            job_text_candidate=payload,
            instruction=instruction,
            signals=signals,
            length=len(cleaned),
        )

    urls = _extract_urls(cleaned)
    if urls:
        return InputAnalysis(
            kind=InputKind.JOB_URL,
            urls=urls,
            job_url=urls[0],
            job_text_candidate=None,
            instruction=_surrounding_instruction(cleaned, urls[0]),
            signals=["url"],
            length=len(cleaned),
        )

    return InputAnalysis(
        kind=InputKind.QUESTION,
        urls=(),
        job_url=None,
        job_text_candidate=None,
        instruction=None,
        signals=signals,
        length=len(cleaned),
    )
