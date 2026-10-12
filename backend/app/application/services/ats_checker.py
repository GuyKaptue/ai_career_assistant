"""ATS resume checker with transparent scoring pipeline (BE-03).

Scoring methodology (§19):

    ATS score = w_kw * S_keyword + w_fmt * S_format + w_read * S_readability

where w_kw + w_fmt + w_read = 1.

Each sub-score is computed deterministically from the resume text and
job description — no LLM is involved in scoring, so the result is
reproducible and explainable. The LLM (when enabled) only contributes
narrative suggestions, never the numeric score.

Sub-scores:
    S_keyword   = |K_r ∩ K_j| / |K_j|           (keyword overlap)
    S_format    = structure heuristics (headings, sections, length)
    S_readability = sentence length + word complexity

All scores are in [0, 100]. The final score is clamped to [0, 100].
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Aggregation weights (§19). These are the documented weights used by
# the implementation — they are configuration, not invented benchmarks.
WEIGHT_KEYWORD = 0.5
WEIGHT_FORMAT = 0.25
WEIGHT_READABILITY = 0.25

# Readability thresholds.
MAX_SENTENCE_LENGTH = 25  # words per sentence (ideal)
MAX_WORD_LENGTH = 12  # characters per word (ideal)

# Formatting thresholds.
MIN_SECTIONS = 3  # expected resume sections
MIN_LENGTH_CHARS = 200  # minimum resume length
MAX_LENGTH_CHARS = 20000  # maximum resume length


@dataclass(frozen=True)
class ATSSubScores:
    """Individual sub-scores with their raw evidence (§19)."""

    keyword_score: float
    format_score: float
    readability_score: float
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    strengths: tuple[str, ...]
    suggestions: tuple[str, ...]


def _normalise_tokens(text: str) -> set[str]:
    """Lowercased token set with / and - treated as separators."""
    return {token.lower() for token in text.replace("/", " ").replace("-", " ").split() if token.strip()}


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using punctuation boundaries."""
    sentences = re.split(r"[.!?]+", text)
    return [s.strip() for s in sentences if s.strip()]


def _avg_sentence_length(text: str) -> float:
    """Average words per sentence."""
    sentences = _split_sentences(text)
    if not sentences:
        return 0.0
    total_words = sum(len(s.split()) for s in sentences)
    return total_words / len(sentences)


def _avg_word_length(text: str) -> float:
    """Average characters per word."""
    words = text.split()
    if not words:
        return 0.0
    total_chars = sum(len(w.strip(".,;:!?()[]{}")) for w in words)
    return total_chars / len(words)


def _count_sections(text: str) -> int:
    """Count likely resume sections (headings).

    Heuristic: lines that are short, title-cased or ALL-CAPS, and
    followed by content. Common section names are also counted.
    """
    section_names = {
        "summary",
        "experience",
        "education",
        "skills",
        "work",
        "employment",
        "projects",
        "certifications",
        "achievements",
        "references",
        "profile",
        "objective",
        "career",
        "about",
    }
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    count = 0
    for line in lines:
        lower = line.lower().rstrip(":")
        if lower in section_names:
            count += 1
        elif len(line) <= 60 and (line.isupper() or line.istitle()) and not line.endswith("."):
            count += 1
    return count


def _compute_keyword_score(resume_text: str, job_description: str) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    """Keyword overlap: |K_r ∩ K_j| / |K_j|."""
    resume_tokens = _normalise_tokens(resume_text)
    job_tokens = _normalise_tokens(job_description)

    if not job_tokens:
        return 0.0, (), ()

    matched = sorted(resume_tokens & job_tokens)
    missing = sorted(job_tokens - resume_tokens)
    overlap_ratio = len(matched) / len(job_tokens)
    score = max(0.0, min(100.0, overlap_ratio * 100.0))
    return score, tuple(matched), tuple(missing)


def _compute_format_score(resume_text: str) -> float:
    """Formatting score from structure heuristics.

    Components (each 0-100, averaged):
        - section_count: how many resume sections are present
        - length: is the resume within a reasonable length range
        - structure: does it have line breaks and structure
    """
    # Section coverage
    sections = _count_sections(resume_text)
    section_score = min(100.0, (sections / MIN_SECTIONS) * 100.0) if sections < MIN_SECTIONS else 100.0

    # Length appropriateness
    length = len(resume_text)
    if length < MIN_LENGTH_CHARS:
        length_score = (length / MIN_LENGTH_CHARS) * 100.0
    elif length > MAX_LENGTH_CHARS:
        length_score = max(0.0, 100.0 - ((length - MAX_LENGTH_CHARS) / 1000.0))
    else:
        length_score = 100.0

    # Structure: line breaks indicate formatting
    line_count = len([line for line in resume_text.splitlines() if line.strip()])
    structure_score = min(100.0, (line_count / 10.0) * 100.0) if line_count < 10 else 100.0

    return (section_score + length_score + structure_score) / 3.0


def _compute_readability_score(resume_text: str) -> float:
    """Readability score from sentence and word complexity.

    Components (each 0-100, averaged):
        - sentence_length: shorter sentences score higher
        - word_length: shorter words score higher
    """
    if not resume_text.strip():
        return 0.0

    avg_sent = _avg_sentence_length(resume_text)
    avg_word = _avg_word_length(resume_text)

    # Sentence length: ideal is <= MAX_SENTENCE_LENGTH
    if avg_sent <= MAX_SENTENCE_LENGTH:
        sent_score = 100.0
    else:
        sent_score = max(0.0, 100.0 - ((avg_sent - MAX_SENTENCE_LENGTH) * 2.0))

    # Word length: ideal is <= MAX_WORD_LENGTH
    if avg_word <= MAX_WORD_LENGTH:
        word_score = 100.0
    else:
        word_score = max(0.0, 100.0 - ((avg_word - MAX_WORD_LENGTH) * 5.0))

    return (sent_score + word_score) / 2.0


def _build_strengths(
    matched: tuple[str, ...],
    keyword_score: float,
    format_score: float,
    readability_score: float,
) -> tuple[str, ...]:
    """Evidence-based strengths (never invented)."""
    strengths: list[str] = []
    if matched:
        strengths.append(f"Matches {len(matched)} job keywords: {', '.join(matched[:5])}")
    if keyword_score >= 70:
        strengths.append("Strong keyword alignment with the job description")
    elif keyword_score >= 40:
        strengths.append("Moderate keyword alignment with the job description")
    if format_score >= 70:
        strengths.append("Resume has clear section structure")
    if readability_score >= 70:
        strengths.append("Resume text is readable with appropriate sentence length")
    return tuple(strengths[:5])


def _build_suggestions(
    missing: tuple[str, ...],
    keyword_score: float,
    format_score: float,
    readability_score: float,
) -> tuple[str, ...]:
    """Actionable suggestions based only on the resume and role."""
    suggestions: list[str] = []
    if missing:
        suggestions.append(f"Add missing keywords: {', '.join(missing[:5])}")
    if keyword_score < 50:
        suggestions.append("Increase keyword coverage to improve ATS matching")
    if format_score < 50:
        suggestions.append("Add clear section headings (Summary, Experience, Education, Skills)")
    if readability_score < 50:
        suggestions.append("Use shorter sentences and simpler words for better readability")
    if not suggestions:
        suggestions.append("Resume is well-optimized for the target role")
    return tuple(suggestions[:5])


def _aggregate(keyword: float, format: float, readability: float) -> float:
    """Weighted aggregation: w_kw*S_kw + w_fmt*S_fmt + w_read*S_read."""
    raw = WEIGHT_KEYWORD * keyword + WEIGHT_FORMAT * format + WEIGHT_READABILITY * readability
    return max(0.0, min(100.0, raw))


def _build_explanation(
    score: float,
    keyword: float,
    format: float,
    readability: float,
    matched_count: int,
    missing_count: int,
) -> str:
    """Human-readable explanation of how the score was produced."""
    return (
        f"ATS score {score:.0f}/100 = "
        f"{WEIGHT_KEYWORD:.0%}×keyword({keyword:.0f}) + "
        f"{WEIGHT_FORMAT:.0%}×format({format:.0f}) + "
        f"{WEIGHT_READABILITY:.0%}×readability({readability:.0f}). "
        f"Matched {matched_count} keywords, missing {missing_count}."
    )


def check_resume_against_job(resume_text: str, job_description: str) -> dict:
    """Run the transparent ATS scoring pipeline (§19).

    Returns an 8-key result:
        score, matched_keywords, missing_keywords, strengths,
        suggestions, keyword_overlap, formatting_score,
        readability_score, explanation
    """
    if not job_description.strip():
        raise ValueError("A job description is required to calculate an ATS score.")

    keyword_score, matched, missing = _compute_keyword_score(resume_text, job_description)
    format_score = _compute_format_score(resume_text)
    readability_score = _compute_readability_score(resume_text)

    score = _aggregate(keyword_score, format_score, readability_score)
    job_tokens = _normalise_tokens(job_description)
    overlap_ratio = len(matched) / len(job_tokens) if job_tokens else 0.0

    strengths = _build_strengths(matched, keyword_score, format_score, readability_score)
    suggestions = _build_suggestions(missing, keyword_score, format_score, readability_score)
    explanation = _build_explanation(
        score,
        keyword_score,
        format_score,
        readability_score,
        len(matched),
        len(missing),
    )

    return {
        "score": int(round(score)),
        "matched_keywords": list(matched[:10]),
        "missing_keywords": list(missing[:10]),
        "strengths": list(strengths),
        "suggestions": list(suggestions),
        "keyword_overlap": round(overlap_ratio, 3),
        "formatting_score": int(round(format_score)),
        "readability_score": int(round(readability_score)),
        "explanation": explanation,
    }
