"""Career intent classification for chat completions (RD-06)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Final

from app.application.services.chat_input import InputAnalysis, InputKind


class Intent(Enum):
    SEARCH_JOBS = "search_jobs"
    SUMMARIZE_CV = "summarize_cv"
    IMPROVE_CV = "improve_cv"
    SKILL_GAP = "skill_gap"
    INTERVIEW_PREP = "interview_prep"
    MATCH_JOB = "match_job"
    TAILOR_CV = "tailor_cv"
    COVER_LETTER = "cover_letter"
    CLARIFY = "clarify"
    GENERAL = "general"


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    confidence: float
    rule_id: str


HAS_CV_MIN_CHARS: Final = 1

_SEARCH_ACTIONS = {"search", "find", "look", "suche", "finde", "trouve", "cherche"}
_JOB_OBJECTS = {
    "job",
    "jobs",
    "position",
    "positions",
    "role",
    "roles",
    "opening",
    "openings",
    "vacancy",
    "vacancies",
    "stelle",
    "stellen",
    "offre",
    "offres",
    "emploi",
    "emplois",
}
# "summary"/"brief"/"kurz" are nouns/adjectives: they only mean "summarize my CV" when the
# message refers to the user's own CV and is not about WRITING one ("write a strong CV summary").
_SUMMARIZE_NOUNS = {"summary", "brief", "kurz"}
_OWN_CV_MARKERS = {"my", "this", "mein", "meinen", "meinem", "meiner", "mon", "ma", "mes", "ce", "cet", "diesen"}
_WRITING_VERBS = {
    "write",
    "draft",
    "create",
    "craft",
    "make",
    "schreiben",
    "schreibe",
    "erstellen",
    "ecrire",
    "rediger",
    "creer",
    "how",
    "wie",
    "comment",
    "tips",
    "example",
    "examples",
    "beispiel",
    "exemple",
}
_SUMMARIZE_ACTIONS = {
    "summarize",
    "summarise",
    "summariser",
    "fasse",
    "zusammenfassen",
    "resume",
    "resumer",
    "resumez",
}
_IMPROVE_ACTIONS = {"improve", "improving", "verbessern", "verbessere", "ameliorer", "ameliore", "ameliorez"}
_SKILL_GAP_ACTIONS = {"missing", "gap", "gaps", "skills", "fehlen", "fehlende", "manquer", "manquantes"}
_INTERVIEW_ACTIONS = {
    "interview",
    "interviews",
    "vorstellungsgespraech",
    "vorstellungsgesprach",
    "entrevue",
    "entretien",
}

_CV_SYNONYMS = {"cv", "lebenslauf", "curriculum", "curriculo", "resume", "resumes"}

#: "cover letter" in en/de/fr — normalized (accents stripped, e.g. "lettre"
#: still matches, "motivation" covers "lettre de motivation").
_COVER_LETTER_NOUNS = {"letter", "letters", "anschreiben", "motivation"}
#: Explicit cover-letter verbs; bare "write a letter" is still COVER_LETTER.
_COVER_LETTER_VERBS = {
    "write",
    "draft",
    "create",
    "generate",
    "schreiben",
    "schreibe",
    "erstelle",
    "erstellen",
    "verfasse",
    "redige",
    "rediger",
    "ecrire",
    "ecris",
}
#: "tailor/adapt my CV to this job" in en/de/fr.
_TAILOR_ACTIONS = {
    "tailor",
    "adapt",
    "customize",
    "customise",
    "anpassen",
    "anpasse",
    "adapte",
    "adapter",
    "optimise",
    "optimieren",
    "passe",
}
#: "match/compare/score my CV against this job" in en/de/fr.
_MATCH_ACTIONS = {
    "match",
    "compare",
    "score",
    "fit",
    "check",
    "vergleichen",
    "vergleiche",
    "abgleichen",
    "gleiche",
    "evalue",
    "evaluer",
    "comparez",
    "passt",
    "passen",
    "entspricht",
    "entsprechen",
    "correspond",
    "corresponds",
    "correspondent",
    "correspondre",
}
#: Pronoun/demonstrative markers that tie the action to *this* job/CV pair.
_JOB_PRONOUNS = {"this", "that", "these", "diese", "dieser", "diesen", "cette", "ce", "cet"}
_MY_MARKERS = {"my", "mein", "meinen", "meinem", "meiner", "mon", "ma", "mes"}
_JOB_NOUNS = {
    "job",
    "jobs",
    "position",
    "posting",
    "stelle",
    "stellenanzeige",
    "offre",
    "poste",
    "annonce",
}
_ACTION_WORDS = frozenset(
    {
        *_IMPROVE_ACTIONS,
        *_SUMMARIZE_ACTIONS,
        *_SKILL_GAP_ACTIONS,
        *_INTERVIEW_ACTIONS,
        *_TAILOR_ACTIONS,
        *_MATCH_ACTIONS,
        *_COVER_LETTER_VERBS,
        "search",
        "find",
        "suche",
        "finde",
        "trouve",
        "cherche",
    }
)


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    t = text.casefold()
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    # Strip every remaining accent (é, à, ç, ...) so French input matches.
    t = "".join(c for c in unicodedata.normalize("NFD", t) if not unicodedata.combining(c))
    t = re.sub(r"['\"’`]", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def has_cv_content(document_context: str | None) -> bool:
    if not document_context:
        return False
    return len(document_context.strip()) >= HAS_CV_MIN_CHARS


def _has_cv_token(tokens: set[str]) -> bool:
    return bool(tokens & _CV_SYNONYMS)


def _cover_letter_decision(user_task: str, analysis: InputAnalysis | None) -> IntentDecision | None:
    """The COVER_LETTER decision, or ``None`` when the message does not ask for one.

    Extracted from :func:`classify_intent` so the two-pipeline turn (match a job
    *and* write a cover letter) can ask the same question without duplicating
    the rules.
    """
    norm = _normalize_text(user_task)
    tokens = set(norm.split())
    cover_verb = bool(tokens & _COVER_LETTER_VERBS) or (
        "lettre" in tokens and bool(tokens & {"redige", "rediger", "ecrire", "ecris", "creer"})
    )
    cover_noun = bool(tokens & _COVER_LETTER_NOUNS)
    if cover_noun and cover_verb:
        return IntentDecision(Intent.COVER_LETTER, 0.95, "cover_letter")
    if cover_noun and analysis is not None and getattr(analysis, "kind", None) is not None:
        if getattr(analysis, "kind", None) in {InputKind.JOB_URL, InputKind.JOB_DESCRIPTION}:
            return IntentDecision(Intent.COVER_LETTER, 0.9, "cover_letter_from_analysis")
    return None


def _match_job_decision(user_task: str, has_cv: bool) -> IntentDecision | None:
    """The explicit MATCH_JOB decision ("match my CV against this job"), or ``None``.

    The bare-URL / bare-job-text fallback is *not* part of this predicate: it
    only fires when the message carries no other action word, so it stays in
    :func:`classify_intent` where the search branch is checked first.
    """
    norm = _normalize_text(user_task)
    tokens = set(norm.split())
    singular_job = bool(tokens & _JOB_PRONOUNS) or (
        bool(tokens & _JOB_NOUNS - {"jobs", "roles"}) and "jobs" not in tokens and "roles" not in tokens
    )
    match_keywords = (
        _has_cv_token(tokens)
        and bool(tokens & _MATCH_ACTIONS)
        and not bool(tokens & (_SEARCH_ACTIONS - {"match"}))
        and singular_job
        and (
            "against" in tokens
            or "avec" in tokens
            or "mit" in tokens
            or bool(tokens & _MY_MARKERS)
            or bool(tokens & _JOB_PRONOUNS)
        )
    )
    if match_keywords:
        return IntentDecision(Intent.MATCH_JOB, 0.95, "match_job")
    return None


def _bare_input_match_decision(user_task: str, analysis: InputAnalysis | None) -> IntentDecision | None:
    """A bare URL / bare job text with no other action word means MATCH_JOB."""
    if analysis is None or getattr(analysis, "kind", None) is None:
        return None
    tokens = set(_normalize_text(user_task).split())
    if getattr(analysis, "kind", None) in {InputKind.JOB_URL, InputKind.JOB_DESCRIPTION} and not (
        tokens & _ACTION_WORDS
    ):
        return IntentDecision(Intent.MATCH_JOB, 0.9, "match_job_from_analysis")
    return None


def _tailor_cv_decision(user_task: str) -> IntentDecision | None:
    """The TAILOR_CV decision ("tailor my CV to this job"), or ``None``."""
    norm = _normalize_text(user_task)
    tokens = set(norm.split())
    tailor_match = (
        _has_cv_token(tokens)
        and bool(tokens & _TAILOR_ACTIONS)
        and (bool(tokens & _JOB_PRONOUNS) or bool(tokens & _JOB_NOUNS))
    )
    if tailor_match:
        return IntentDecision(Intent.TAILOR_CV, 0.95, "tailor_cv")
    return None


def classify_intents(
    user_task: str,
    has_cv: bool,
    mode: str | None = None,
    analysis: InputAnalysis | None = None,
) -> tuple[IntentDecision, ...]:
    """Every intent this message asks for, in pipeline order.

    A single-intent message returns exactly one decision, identical to
    :func:`classify_intent`. A message that asks to match a job *and* to write
    a cover letter (or to tailor the CV) returns the match first, then the
    document (at most two pipelines per turn).
    """
    if not user_task or not user_task.strip():
        return (classify_intent(user_task, has_cv, mode, analysis),)
    match = _match_job_decision(user_task, has_cv)
    if match is None:
        return (classify_intent(user_task, has_cv, mode, analysis),)
    cover = _cover_letter_decision(user_task, analysis)
    if cover is not None:
        return (match, cover)
    tailor = _tailor_cv_decision(user_task)
    if tailor is not None:
        return (match, tailor)
    return (classify_intent(user_task, has_cv, mode, analysis),)


def classify_intent(
    user_task: str,
    has_cv: bool,
    mode: str | None = None,
    analysis: InputAnalysis | None = None,
) -> IntentDecision:
    """Classify intent from the user message only (``mode`` is reserved, currently unused).

    ``analysis`` (optional :class:`InputAnalysis`) only supplies the
    bare-URL/bare-job-text MATCH_JOB fallback — never CV/job availability.
    Missing CV or missing job for the new intents is decided later in stage E.
    """
    if not user_task or not user_task.strip():
        return IntentDecision(Intent.GENERAL, 0.9, "empty")

    norm = _normalize_text(user_task)
    tokens = set(norm.split())

    # Cover letter — needs a generation verb (or "lettre" with a French
    # generation verb), or a job present in the analysis. "Relis" (re-read)
    # is editing advice → GENERAL.
    cover = _cover_letter_decision(user_task, analysis)
    if cover is not None:
        return cover

    # Tailor CV to this job — before IMPROVE/SUMMARIZE/SKILL_GAP.
    tailor_match = (
        _has_cv_token(tokens)
        and bool(tokens & _TAILOR_ACTIONS)
        and (bool(tokens & _JOB_PRONOUNS) or bool(tokens & _JOB_NOUNS))
    )
    if tailor_match:
        return IntentDecision(Intent.TAILOR_CV, 0.95, "tailor_cv")

    # Improve CV - check first for precedence over search
    improve_match = _has_cv_token(tokens) and (
        tokens.intersection(_IMPROVE_ACTIONS) or "improve" in norm or "verbessere" in norm
    )
    if improve_match:
        if not has_cv:
            return IntentDecision(Intent.CLARIFY, 0.95, "clarify_missing_cv")
        return IntentDecision(Intent.IMPROVE_CV, 0.95, "improve_cv")

    # Summarize CV
    summarize_match = _has_cv_token(tokens) and (
        tokens.intersection(_SUMMARIZE_ACTIONS)
        or "zusammenfassen" in tokens
        or "resumer" in tokens
        or (
            tokens.intersection(_SUMMARIZE_NOUNS)
            and tokens.intersection(_OWN_CV_MARKERS)
            and not tokens.intersection(_WRITING_VERBS)
        )
    )
    if summarize_match:
        if not has_cv:
            return IntentDecision(Intent.CLARIFY, 0.95, "clarify_missing_cv")
        return IntentDecision(Intent.SUMMARIZE_CV, 0.95, "summarize_cv")
    summarize_phrase = ("summarize" in norm and _has_cv_token(tokens)) or ("fasse" in tokens)
    if summarize_phrase:
        if not has_cv:
            return IntentDecision(Intent.CLARIFY, 0.95, "clarify_missing_cv")
        return IntentDecision(Intent.SUMMARIZE_CV, 0.95, "summarize_cv")

    # Skill gap - check before search for precedence
    skill_phrases = (
        ("skills am i missing" in norm)
        or ("skill gap" in norm)
        or ("skills missing" in norm)
        or ("missing skills" in norm)
    )
    if skill_phrases:
        if not has_cv:
            return IntentDecision(Intent.CLARIFY, 0.95, "clarify_missing_cv")
        return IntentDecision(Intent.SKILL_GAP, 0.95, "skill_gap")
    fr_skill = "competences" in tokens and ("manquent" in tokens or "manquantes" in tokens)
    skill_tokens = fr_skill or "skill" in tokens and ("missing" in tokens or "gap" in tokens or "gaps" in tokens)
    if skill_tokens or ("fehlende" in tokens):
        if not has_cv:
            return IntentDecision(Intent.CLARIFY, 0.95, "clarify_missing_cv")
        return IntentDecision(Intent.SKILL_GAP, 0.95, "skill_gap")

    # Match job — after IMPROVE/SUMMARIZE/SKILL_GAP, before SEARCH_JOBS:
    # singular "this job" with a match verb is MATCH_JOB; plural "jobs/roles"
    # with no singular pronoun falls through to SEARCH_JOBS.
    match = _match_job_decision(user_task, has_cv)
    if match is not None:
        return match

    # Search jobs (plural "jobs/roles" always searches, even with "match").
    search_match = tokens.intersection(_SEARCH_ACTIONS) and tokens.intersection(_JOB_OBJECTS)
    plural_match_search = "match" in tokens and bool(tokens & {"jobs", "roles", "openings", "offres", "emplois"})
    fr_search = "search" in tokens and "job" in tokens
    de_search = "suche" in tokens and "stelle" in tokens
    fr_trouve = "trouve" in tokens and bool(tokens & {"offre", "offres", "emploi", "emplois"})
    if search_match or plural_match_search or fr_search or de_search or fr_trouve:
        if not has_cv:
            return IntentDecision(Intent.CLARIFY, 0.95, "clarify_missing_cv")
        return IntentDecision(Intent.SEARCH_JOBS, 0.95, "search_jobs")

    # Bare URL / bare job text with no other action word → MATCH_JOB.
    bare = _bare_input_match_decision(user_task, analysis)
    if bare is not None:
        return bare

    # Interview prep
    if tokens.intersection(_INTERVIEW_ACTIONS) or "vorbereitung" in tokens or "vorstellungsgespraech" in tokens:
        return IntentDecision(Intent.INTERVIEW_PREP, 0.95, "interview_prep")

    return IntentDecision(Intent.GENERAL, 0.8, "general")
