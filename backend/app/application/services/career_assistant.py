"""Intent-aware career turn (RD-06 + RD-08): the single insertion point for the chat flow.

``run_career_turn`` classifies the user's message (code, never the CV text) and
either returns ``None`` (``general`` intent: the existing chat path runs
untouched) or a :class:`CareerTurn` with an on-intent, validated, code-rendered
answer:

* ``clarify``      -> asks for the missing CV (no model call);
* ``search_jobs``  -> analysis stage -> RAG -> real providers -> code ranking.
  The model only analyses the CV; jobs, URLs and scores come from code/providers;
* other intents    -> compact intent prompt, strict JSON validation, one repair,
  skill grounding, code rendering. If the model cannot produce a valid answer the
  function returns ``None`` and the existing chat path answers as before.

Nothing from the CV, the message or any answer is logged.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Final
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from app.application.services import job_resolution
from app.application.services.candidate_analysis import (
    AnalysisResult,
    normalize_for_match,
    parse_and_validate_model,
    run_analysis,
    skill_in_text,
)
from app.application.services.career_intent import Intent, classify_intents, has_cv_content
from app.application.services.career_prompts import build_career_messages
from app.application.services.chat_input import InputAnalysis, analyse_input
from app.application.services.chat_store import chat_store
from app.application.services.document_retrieval import get_document_retrieval
from app.application.services.generation_context import personal_context_for_generation, resolve_template
from app.application.services.job_resolution import ResolvedJob
from app.application.services.job_search_pipeline import JobSearchOutcome, run_job_search, score_job
from app.application.services.job_target import JobTarget, build_job_target
from app.application.services.model_router_facade import ModelRouter
from app.application.services.profile_service import profile_store
from app.application.services.rag_enrichment import enrich
from app.application.services.tailoring_pipeline import (
    JobTarget as TailoringJobTarget,
)
from app.application.services.tailoring_pipeline import (
    job_gaps,
    tailor_cv,
    write_cover_letter,
)
from app.core.errors import AIProviderError, ConfigurationError, ValidationError
from app.domain.chat.models import ChatSession
from app.domain.users.user_core import UserCore, core_from_payload

logger = logging.getLogger(__name__)

TOKEN_BUDGET: Final = 600
LIST_MAX: Final = 8


@dataclass(frozen=True)
class CareerTurn:
    """Everything the chat service needs to store and return one career answer."""

    intent: str
    content: str
    structured: dict[str, Any]
    ai_generated: bool
    prompt_version: str
    models: tuple[dict[str, Any], ...] = ()
    notices: tuple[str, ...] = ()
    attempts: int = 0
    task: str = "career_advice"
    #: Routing audit (ids, counts and lengths only — never content).
    rule_id: str = ""
    input_kind: str = ""
    job_ingest_status: str = ""
    source_host: str = ""
    text_len: int = 0
    job_len: int = 0


# ---------------------------------------------------------------------------
# Output schemas for the non-search intents (shapes from career_prompts)
# ---------------------------------------------------------------------------
_Str = Field(default="", max_length=400)


class _SummarizeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str = _Str
    years_experience: int = Field(default=0, ge=0, le=60)
    top_skills: list[str] = Field(default_factory=list, max_length=LIST_MAX)
    strengths: list[str] = Field(default_factory=list, max_length=LIST_MAX)
    gaps: list[str] = Field(default_factory=list, max_length=LIST_MAX)


class _Improvement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: str = _Str
    issue: str = _Str
    suggestion: str = _Str


class _ImproveOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    improvements: list[_Improvement] = Field(default_factory=list, max_length=LIST_MAX)
    missing_keywords: list[str] = Field(default_factory=list, max_length=LIST_MAX)
    overall_score: int = Field(default=0, ge=0, le=100)


class _SkillGapOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_role: str = _Str
    matched_skills: list[str] = Field(default_factory=list, max_length=LIST_MAX)
    missing_skills: list[str] = Field(default_factory=list, max_length=LIST_MAX)
    learning_path: list[str] = Field(default_factory=list, max_length=LIST_MAX)


class _Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = _Str
    why: str = _Str
    sample_answer: str = _Str


class _InterviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[_Question] = Field(default_factory=list, max_length=LIST_MAX)
    focus_areas: list[str] = Field(default_factory=list, max_length=LIST_MAX)


_MODELS: Final[dict[str, type[BaseModel]]] = {
    "summarize_cv": _SummarizeOut,
    "improve_cv": _ImproveOut,
    "skill_gap": _SkillGapOut,
    "interview_prep": _InterviewOut,
}
_ROUTER_INTENT: Final = {
    "summarize_cv": "summarize_cv",
    "improve_cv": "improve_cv",
    "skill_gap": "skill_gap",
    "interview_prep": "interview_prep",
}

# ---------------------------------------------------------------------------
# Localized, code-owned text (en/de/fr)
# ---------------------------------------------------------------------------
_T: Final[dict[str, dict[str, str]]] = {
    "en": {
        "need_cv": "I need your CV for this. Please upload it or paste its text, then ask again.",
        "need_job": "I need the job description for this. Paste the posting text or share the link.",
        "job_unreadable": "I could not read that page. Please paste the job description text.",
        "profile": "Your profile",
        "titles": "Suggested job titles",
        "skills": "Skills found in your CV",
        "matches": "Matching jobs (live listings)",
        "none": "No live listings could be fetched right now.",
        "queries": "Search queries to try",
        "questions": "Questions to sharpen the search",
        "next": "Next steps",
        "not_ai": "This answer was not AI-generated (the AI service was unavailable).",
        "q_location": "Which city or country do you want to work in?",
        "q_remote": "Are you open to remote roles?",
        "q_seniority": "Which seniority level are you aiming for (junior, mid, senior, lead)?",
        "n_review": "Open the listings and tailor your CV to the ones you like.",
        "n_titles": "Tell me your preferred job titles to refine the search.",
        "match": "Match",
        "label_strong": "strong match",
        "label_partial": "partial match",
        "label_weak": "weak match",
        "matched": "You already have",
        "missing": "The job asks for",
        "n_tailor": "Tailor your CV to this job.",
        "n_cover": "Write a cover letter for this job.",
        "company_unverified": "I could not verify the company name, so I left it out.",
        "role_fallback": "I could not verify the job title, so I am speaking about the role.",
    },
    "de": {
        "need_cv": "Dafür brauche ich deinen Lebenslauf. Lade ihn hoch oder füge den Text ein und frage dann erneut.",
        "need_job": "Dafür brauche ich die Stellenanzeige. Füge den Text ein oder teile den Link.",
        "job_unreadable": "Diese Seite konnte ich nicht lesen. Bitte füge den Text der Stellenanzeige ein.",
        "profile": "Dein Profil",
        "titles": "Vorgeschlagene Jobtitel",
        "skills": "Im Lebenslauf gefundene Fähigkeiten",
        "matches": "Passende Stellen (aktuelle Anzeigen)",
        "none": "Aktuell konnten keine Anzeigen abgerufen werden.",
        "queries": "Suchanfragen zum Ausprobieren",
        "questions": "Fragen zur Verfeinerung der Suche",
        "next": "Nächste Schritte",
        "not_ai": "Diese Antwort wurde nicht von der KI erzeugt (der KI-Dienst war nicht verfügbar).",
        "q_location": "In welcher Stadt oder welchem Land möchtest du arbeiten?",
        "q_remote": "Bist du offen für Remote-Stellen?",
        "q_seniority": "Welches Level strebst du an (Junior, Mid, Senior, Lead)?",
        "n_review": "Öffne die Anzeigen und passe deinen Lebenslauf an die passenden an.",
        "n_titles": "Nenne mir deine bevorzugten Jobtitel, um die Suche zu verfeinern.",
        "match": "Passung",
        "label_strong": "gute Passung",
        "label_partial": "teilweise Passung",
        "label_weak": "geringe Passung",
        "matched": "Das kannst du bereits",
        "missing": "Die Stelle verlangt",
        "n_tailor": "Passe deinen Lebenslauf an diese Stelle an.",
        "n_cover": "Schreibe ein Anschreiben für diese Stelle.",
        "company_unverified": "Den Firmennamen konnte ich nicht prüfen, deshalb habe ich ihn weggelassen.",
        "role_fallback": "Die Stellenbezeichnung konnte ich nicht prüfen, deshalb spreche ich von der Stelle.",
    },
    "fr": {
        "need_cv": "J'ai besoin de ton CV pour cela. Importe-le ou colle son texte, puis redemande.",
        "need_job": "J'ai besoin de l'annonce pour cela. Colle le texte ou partage le lien.",
        "job_unreadable": "Je n'ai pas pu lire cette page. Colle le texte de l'annonce.",
        "profile": "Ton profil",
        "titles": "Intitulés de poste suggérés",
        "skills": "Compétences trouvées dans ton CV",
        "matches": "Offres correspondantes (annonces actuelles)",
        "none": "Aucune annonce n'a pu être récupérée pour le moment.",
        "queries": "Requêtes de recherche à essayer",
        "questions": "Questions pour affiner la recherche",
        "next": "Prochaines étapes",
        "not_ai": "Cette réponse n'a pas été générée par l'IA (le service d'IA était indisponible).",
        "q_location": "Dans quelle ville ou quel pays veux-tu travailler ?",
        "q_remote": "Es-tu ouvert au télétravail ?",
        "q_seniority": "Quel niveau vises-tu (junior, confirmé, senior, lead) ?",
        "n_review": "Ouvre les annonces et adapte ton CV à celles qui te plaisent.",
        "n_titles": "Indique-moi tes intitulés de poste préférés pour affiner la recherche.",
        "match": "Correspondance",
        "label_strong": "forte correspondance",
        "label_partial": "correspondance partielle",
        "label_weak": "faible correspondance",
        "matched": "Tu as déjà",
        "missing": "Le poste demande",
        "n_tailor": "Adapte ton CV à ce poste.",
        "n_cover": "Rédige une lettre de motivation pour ce poste.",
        "company_unverified": "Je n'ai pas pu vérifier le nom de l'entreprise, je l'ai donc omis.",
        "role_fallback": "Je n'ai pas pu vérifier l'intitulé du poste, je parle donc du poste.",
    },
}


def _t(language: str) -> dict[str, str]:
    return _T.get(language, _T["en"])


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


# ---------------------------------------------------------------------------
# Job intake (stage C) — the job the user is talking about
# ---------------------------------------------------------------------------
def _source_host(url: str | None) -> str:
    """Host of a job URL only (no path, no query, no credentials)."""
    if not url:
        return ""
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def _job_dict(target: JobTarget) -> dict[str, Any]:
    """The provider-shaped job dict the scoring formula expects."""
    return {
        "title": target.title or "",
        "company": target.company or "",
        "description": target.description or "",
        "url": target.url or "",
        "location": target.location or "",
    }


#: Maximum number of characters of the job posting kept in the session context.
JOB_CONTEXT_MAX_CHARS: Final = 30_000


def _job_context_payload(target: JobTarget) -> dict[str, Any]:
    """What is remembered about the last job of a session.

    The posting text (capped) plus the verified fields. It never holds CV text.
    """
    description = (target.description or "")[:JOB_CONTEXT_MAX_CHARS]
    return {
        "title": target.title or "",
        "company": target.company or "",
        "location": target.location or "",
        "employment_type": target.employment_type or "",
        "skills": list(target.skills),
        "url": target.url or "",
        "source_host": _source_host(target.url),
        "description": description,
        "text_hash": hashlib.sha256(description.encode("utf-8")).hexdigest(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "company_unverified": target.company_unverified,
        "the_role_fallback": target.the_role_fallback,
    }


def _target_from_session(payload: dict[str, Any] | None) -> JobTarget | None:
    """Rebuild a job target from the persisted session context (never from untrusted input)."""
    if not payload:
        return None
    title = str(payload.get("title") or "")
    if not title:
        return None
    return JobTarget(
        title=title,
        company=str(payload.get("company") or ""),
        location=str(payload.get("location") or ""),
        employment_type=str(payload.get("employment_type") or ""),
        description=str(payload.get("description") or ""),
        url=str(payload.get("url") or ""),
        skills=tuple(str(item) for item in payload.get("skills") or ()),
        the_role_fallback=bool(payload.get("the_role_fallback")),
        company_unverified=bool(payload.get("company_unverified")),
    )


# ---------------------------------------------------------------------------
# clarify
# ---------------------------------------------------------------------------
def _clarify_turn(language: str) -> CareerTurn:
    text = _t(language)["need_cv"]
    return CareerTurn(
        intent="clarify",
        content=text,
        structured={"intent": "clarify", "questions": [text]},
        ai_generated=False,
        prompt_version="rd08-code",
        task="career_advice",
    )


def _clarify_turn_for(
    language: str,
    *,
    missing: list[str],
    job_ingest_status: str = "",
    input_kind: str = "",
    used_session_job: bool = False,
) -> CareerTurn:
    """A clarifying reply for a missing CV / job, or an unreadable job page.

    No model call: the answer is code-owned and says exactly what is missing.
    """
    t = _t(language)
    parts: list[str] = []
    if "cv" in missing:
        parts.append(t["need_cv"])
    if "job" in missing:
        parts.append(t["need_job"])
    if job_ingest_status and job_ingest_status not in ("ok", "session", ""):
        parts.append(t["job_unreadable"])
    text = " ".join(parts) or t["need_cv"]
    structured: dict[str, Any] = {
        "intent": "clarify",
        "questions": parts or [text],
        "missing": list(missing),
        "input": {
            "kind": input_kind,
            "job_ingest_status": job_ingest_status,
            "used_session_job": used_session_job,
        },
    }
    if job_ingest_status:
        structured["job_ingest_status"] = job_ingest_status
    return CareerTurn(
        intent="clarify",
        content=text,
        structured=structured,
        ai_generated=False,
        prompt_version="rd08-code",
        task="career_advice",
        input_kind=input_kind,
        job_ingest_status=job_ingest_status,
    )


# ---------------------------------------------------------------------------
# search_jobs
# ---------------------------------------------------------------------------
def _clarifying_questions(core: UserCore, analysis_seniority: str, language: str) -> list[str]:
    t = _t(language)
    questions: list[str] = []
    if not core.preferred_locations:
        questions.append(t["q_location"])
    if not core.remote_policy:
        questions.append(t["q_remote"])
    if not core.seniority and not analysis_seniority:
        questions.append(t["q_seniority"])
    return questions[:3]


def _job_row(match: Any) -> dict[str, Any]:
    job = match.job
    return {
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "url": job.get("url"),
        "source": job.get("source"),
        "job_key": job.get("job_key"),
        "match_score": match.score,
        "matched_skills": list(match.matched_skills),
    }


def _render_search(structured: dict[str, Any], language: str, ai_generated: bool) -> str:
    t = _t(language)
    profile = structured["candidate_profile"]
    parts = [f"## {t['profile']}"]
    meta = ", ".join(
        str(x) for x in (profile.get("role_archetype"), profile.get("seniority"), profile.get("years_experience")) if x
    )
    if meta:
        parts.append(meta)
    if profile["skills"]:
        parts += [f"\n## {t['skills']}", ", ".join(profile["skills"])]
    if profile["titles"]:
        parts += [f"\n## {t['titles']}", _bullets(profile["titles"])]
    parts.append(f"\n## {t['matches']}")
    if structured["job_matches"]:
        parts.append(
            "\n".join(
                f"- {m['title']} — {m['company'] or '?'} ({m['location'] or '?'}) "
                f"[{round(m['match_score'] * 100)}%] {m['url'] or ''}".rstrip()
                for m in structured["job_matches"]
            )
        )
    else:
        parts.append(t["none"])
    if structured["search_queries"]:
        parts += [f"\n## {t['queries']}", _bullets(structured["search_queries"])]
    if structured["clarifying_questions"]:
        parts += [f"\n## {t['questions']}", _bullets(structured["clarifying_questions"])]
    parts += [f"\n## {t['next']}", _bullets(structured["next_steps"])]
    if structured.get("caveats"):
        parts.append(f"\n_{structured['caveats']}_")
    if not ai_generated:
        parts.append(f"\n{t['not_ai']}")
    return "\n".join(parts)


def _search_turn(
    core: UserCore, model_id: str | None, router: ModelRouter, *, search_fn: Any | None = None
) -> CareerTurn:
    generator = router.generator_for("analysis", preferred_model_id=model_id)
    result: AnalysisResult = run_analysis(core, generator, preferred_model_id=model_id)
    analysis = result.analysis
    rag = enrich(core, analysis, get_document_retrieval()) if core.user_id else None
    outcome: JobSearchOutcome = (
        run_job_search(core, analysis, search=search_fn) if search_fn else run_job_search(core, analysis)
    )
    t = _t(core.language)
    queries = [f"{q.keywords} — {q.location}" if q.location else q.keywords for q in outcome.queries]
    titles = list(core.target_titles) or ([analysis.role_archetype] if analysis.role_archetype else [])
    ai_generated = result.source != "heuristic"
    structured: dict[str, Any] = {
        "intent": "search_jobs",
        "candidate_profile": {
            "titles": titles,
            "role_archetype": analysis.role_archetype,
            "seniority": core.seniority or analysis.target_seniority,
            "years_experience": analysis.years_experience,
            "skills": analysis.skills,
            "domains": analysis.domain_keywords,
            "locations": list(core.preferred_locations) or analysis.location_signals,
        },
        "job_matches": [_job_row(m) for m in outcome.matches],
        "search_queries": queries,
        "clarifying_questions": _clarifying_questions(core, analysis.target_seniority, core.language),
        "skill_gaps": [],
        "next_steps": [t["n_review"]] if outcome.matches else [t["n_titles"]],
        "caveats": analysis.caveats,
        "provider_status": {"failed": outcome.provider_failed, "partial": outcome.partial},
        "analysis_source": result.source,
        "rag_sources": len(rag.sources) if rag else 0,
    }
    return CareerTurn(
        intent="search_jobs",
        content=_render_search(structured, core.language, ai_generated),
        structured=structured,
        ai_generated=ai_generated,
        prompt_version=result.prompt_version,
        models=tuple(c.metadata() for c in generator.completions),
        notices=tuple(generator.notices()),
        attempts=len(generator.completions),
        task="job_matching",
    )


# ---------------------------------------------------------------------------
# summarize / improve / skill_gap / interview_prep
# ---------------------------------------------------------------------------
def _ground_list(items: list[str], normalized_cv: str) -> tuple[list[str], int]:
    kept = [item for item in items if skill_in_text(item, normalized_cv)]
    return kept, len(items) - len(kept)


def _render_simple(intent: str, data: dict[str, Any]) -> str:
    if intent == "summarize_cv":
        out = [data["headline"]]
        if data["years_experience"]:
            out.append(f"{data['years_experience']} years")
        for title, key in (("Top skills", "top_skills"), ("Strengths", "strengths"), ("Gaps", "gaps")):
            if data[key]:
                out += [f"\n## {title}", _bullets(data[key])]
        return "\n".join(out)
    if intent == "improve_cv":
        out = [f"Score: {data['overall_score']}/100"] if data["overall_score"] else []
        for item in data["improvements"]:
            out.append(f"- **{item['section']}** — {item['issue']} → {item['suggestion']}")
        if data["missing_keywords"]:
            out += ["\n## Missing keywords", _bullets(data["missing_keywords"])]
        return "\n".join(out)
    if intent == "skill_gap":
        out = [f"Target role: {data['target_role']}"] if data["target_role"] else []
        for title, key in (
            ("Matched", "matched_skills"),
            ("Missing", "missing_skills"),
            ("Learning path", "learning_path"),
        ):
            if data[key]:
                out += [f"\n## {title}", _bullets(data[key])]
        return "\n".join(out)
    out = []
    for item in data["questions"]:
        out += [f"- **{item['question']}**", f"  Why: {item['why']}", f"  Sample answer: {item['sample_answer']}"]
    if data["focus_areas"]:
        out += ["\n## Focus areas", _bullets(data["focus_areas"])]
    return "\n".join(out)


def _simple_turn(
    intent: str, text: str, core: UserCore, model_id: str | None, router: ModelRouter
) -> CareerTurn | None:
    model = _MODELS[intent]
    prompt = build_career_messages(intent, text, core.cv_text, core.language)
    system, user = prompt.messages[0]["content"], prompt.messages[1]["content"]
    generator = router.generator_for(_ROUTER_INTENT[intent], preferred_model_id=model_id)
    options: dict[str, Any] = {
        "token_budget": TOKEN_BUDGET,
        "system_prompt": system,
        "preferred_languages": (core.language,),
    }
    attempts = 0
    parsed = None
    next_prompt = user
    for attempt in range(2):  # first try + at most one repair
        try:
            raw = generator.generate_with_fallback(intent, next_prompt, **options)
        except AIProviderError:
            return None
        attempts += 1
        parsed, errors = parse_and_validate_model(str(raw.get("content") or ""), model)
        if parsed is not None:
            break
        paths = "\n".join(f"- {p}" for p in errors[:10]) or "- (not valid JSON)"
        next_prompt = (
            f"Your previous answer was invalid JSON for the schema. Problems at:\n{paths}\n"
            "Return ONE corrected JSON object only."
        )
    if parsed is None:
        return None
    data = parsed.model_dump()
    normalized_cv = normalize_for_match(core.cv_text)
    dropped = 0
    for key in ("top_skills", "matched_skills"):
        if key in data:
            data[key], count = _ground_list(data[key], normalized_cv)
            dropped += count
    data["intent"] = intent
    if dropped:
        data["caveats"] = f"{dropped} skill(s) not found in the CV were removed."
    return CareerTurn(
        intent=intent,
        content=_render_simple(intent, data),
        structured=data,
        ai_generated=True,
        prompt_version=prompt.prompt_version,
        models=tuple(c.metadata() for c in generator.completions),
        notices=tuple(generator.notices()),
        attempts=attempts,
        task=generator.completions[-1].task if generator.completions else "career_advice",
    )


# ---------------------------------------------------------------------------
# match_job / tailor_cv / cover_letter
# ---------------------------------------------------------------------------
def _match_label(score: int, language: str) -> str:
    """A plain-language label for a 0-100 match score (code-owned)."""
    t = _t(language)
    if score >= 70:
        return t["label_strong"]
    if score >= 40:
        return t["label_partial"]
    return t["label_weak"]


def _match_reasons(matched: list[str], missing: list[str], language: str) -> list[str]:
    """Explanations built only from the verified matched and missing skills."""
    t = _t(language)
    reasons: list[str] = []
    if matched:
        reasons.append(f"{t['matched']}: {', '.join(matched)}")
    if missing:
        reasons.append(f"{t['missing']}: {', '.join(missing)}")
    return reasons


def _render_match(structured: dict[str, Any], language: str) -> str:
    t = _t(language)
    match = structured["match"]
    job = structured["job"]
    parts = [f"## {t['match']}: {match['score']}/100 ({match['label']})"]
    headline = " — ".join(part for part in (job.get("title"), job.get("company")) if part)
    if headline:
        parts.append(headline)
    if job.get("location"):
        parts.append(job["location"])
    if match["reasons"]:
        parts += ["", _bullets(match["reasons"])]
    if structured.get("next_steps"):
        parts += [f"\n## {t['next']}", _bullets(structured["next_steps"])]
    notes = structured.get("notes") or []
    if notes:
        parts += ["", _bullets(notes)]
    return "\n".join(parts)


def _match_turn(
    core: UserCore,
    result: AnalysisResult,
    target: JobTarget,
    *,
    model_id: str | None,
    generator: Any,
    input_meta: dict[str, Any],
) -> CareerTurn:
    """Match the CV against one job. The score comes from ``score_job`` only."""
    analysis = result.analysis
    job_dict = _job_dict(target)
    score, matched = score_job(job_dict, core, analysis)
    tailoring_job = TailoringJobTarget(
        title=target.title or "",
        company=target.company or "",
        description=target.description or "",
    )
    gaps = list(job_gaps(result.analysis, core.cv_text, tailoring_job))
    score_100 = int(round(score * 100))
    t = _t(core.language)
    structured: dict[str, Any] = {
        "intent": "match_job",
        "input": input_meta,
        "match": {
            "score": score_100,
            "label": _match_label(score_100, core.language),
            "matched_skills": list(matched),
            "missing_skills": gaps,
            "reasons": _match_reasons(list(matched), gaps, core.language),
        },
        "job": {
            # Safe summary only: never the posting text, the url or the path.
            "title": target.title or "",
            "company": target.company or "",
            "source_host": _source_host(target.url),
            "company_unverified": target.company_unverified,
            "the_role_fallback": target.the_role_fallback,
        },
        "next_steps": [t["n_tailor"], t["n_cover"]],
    }
    notes: list[str] = []
    if target.company_unverified:
        notes.append(t["company_unverified"])
    if target.the_role_fallback:
        notes.append(t["role_fallback"])
    if notes:
        structured["notes"] = notes
    return CareerTurn(
        intent="match_job",
        content=_render_match(structured, core.language),
        structured=structured,
        ai_generated=result.source != "heuristic",
        prompt_version=result.prompt_version,
        models=tuple(c.metadata() for c in generator.completions),
        notices=tuple(generator.notices()),
        attempts=len(generator.completions),
        task="job_matching",
        input_kind=str(input_meta.get("kind") or ""),
        job_ingest_status=str(input_meta.get("job_ingest_status") or ""),
        source_host=_source_host(target.url),
        text_len=int(input_meta.get("text_len") or 0),
        job_len=len(target.description or ""),
    )


def _document_turn(
    intent: str,
    core: UserCore,
    analysis_result: AnalysisResult,
    target: JobTarget,
    *,
    model_id: str | None,
    router: ModelRouter,
    input_meta: dict[str, Any],
    template_id: str | None,
    rag_block: str,
) -> CareerTurn:
    """Tailor the CV or write the cover letter for one job."""
    t = _t(core.language)
    analysis = analysis_result.analysis
    tailoring_job = TailoringJobTarget(
        title=target.title or "",
        company=target.company or "",
        description=target.description or "",
    )
    if intent == "tailor_cv":
        generator = router.generator_for("tailor_cv", preferred_model_id=model_id)
        tailoring_result = tailor_cv(
            core,
            analysis,
            tailoring_job,
            generator,
            rag_block=rag_block,
            preferred_model_id=model_id,
        )
        document_type = "cv"
    else:
        generator = router.generator_for("cover_letter", preferred_model_id=model_id)
        tailoring_result = write_cover_letter(
            core,
            analysis,
            tailoring_job,
            generator,
            rag_block=rag_block,
            preferred_model_id=model_id,
        )
        document_type = "cover_letter"
    content = "\n".join(
        part
        for part in (
            tailoring_result.document.get("headline", ""),
            tailoring_result.document.get("summary", ""),
            *tailoring_result.document.get("paragraphs", []),
        )
        if part
    )
    structured: dict[str, Any] = {
        "intent": intent,
        "input": input_meta,
        "document": {
            "type": document_type,
            "content": content,
            "template_id": template_id or "",
        },
        "grounding": {"removed": tailoring_result.removed_claims},
        "gaps": list(tailoring_result.gaps),
    }
    notes: list[str] = []
    if target.company_unverified:
        notes.append(t["company_unverified"])
    if target.the_role_fallback:
        notes.append(t["role_fallback"])
    if notes:
        structured["notes"] = notes
    parts = [f"## {t['match']}"]
    if content:
        parts.append(content)
    if tailoring_result.gaps:
        parts += ["", f"## {t['missing']}", _bullets(list(tailoring_result.gaps))]
    if notes:
        parts += ["", _bullets(notes)]
    return CareerTurn(
        intent=intent,
        content="\n".join(parts),
        structured=structured,
        ai_generated=tailoring_result.ai_generated,
        prompt_version=tailoring_result.prompt_version,
        models=tuple(c.metadata() for c in generator.completions),
        notices=tuple(generator.notices()),
        attempts=len(generator.completions),
        task="cv_rewriting" if intent == "tailor_cv" else "cover_letter_generation",
        input_kind=str(input_meta.get("kind") or ""),
        job_ingest_status=str(input_meta.get("job_ingest_status") or ""),
        source_host=_source_host(target.url),
        text_len=int(input_meta.get("text_len") or 0),
        job_len=len(target.description or ""),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _document_context(
    user_id: str | None,
    document_intent: str,
    template_id: str | None,
    target: JobTarget,
) -> tuple[str, str]:
    """Resolve the template and the user's own context, exactly as ``/generate/cv`` does.

    Returns ``(template_id, rag_block)``. The template id falls back to the
    built-in default for the document type when the caller did not pick one.
    """
    document_type = "cover_letter" if document_intent == "cover_letter" else "cv"
    wanted = template_id or ("professional" if document_type == "cv" else "classic-letter")
    resolved = resolve_template(user_id, wanted, document_type)
    selected = resolved.selected_id if resolved else wanted
    query = " ".join(part for part in (target.title, target.company) if part)
    rag_block = personal_context_for_generation(
        user_id,
        query,
        selected,
        get_document_retrieval(),
    )
    return selected, rag_block


def _resolve_job(
    text: str,
    analysis: InputAnalysis,
    *,
    job_url: str | None,
    job_text: str | None,
) -> tuple[ResolvedJob | None, str]:
    """Resolve the job the user is talking about (stage C).

    An explicitly supplied job text wins, then a pasted description, then the
    URL. Returns ``(resolved, status)``; ``resolved`` is ``None`` when there is
    no job at all.
    """
    candidate = (job_text or analysis.job_text_candidate or "").strip()
    if candidate:
        return job_resolution.resolve_job_from_text(candidate), "ok"
    url = job_url or analysis.job_url
    if not url:
        return None, ""
    resolved = job_resolution.resolve_job_from_url(url)
    return resolved, resolved.status


def run_career_turn(
    text: str,
    *,
    mode: str,
    language: str,
    user_id: str | None,
    model_id: str | None,
    document_context: str,
    preferences: dict[str, Any] | None = None,
    router: ModelRouter | None = None,
    search_fn: Any | None = None,
    job_url: str | None = None,
    job_text: str | None = None,
    session: ChatSession | None = None,
    document_type: str | None = None,
    template_id: str | None = None,
) -> CareerTurn | None:
    """Return an on-intent :class:`CareerTurn`, or ``None`` to let the existing chat path answer.

    The routing rule that fired is stamped on the turn, so the audit records
    *why* this intent was chosen (a constant rule id, never message content).
    """
    return _run_career_turn(
        text,
        mode=mode,
        language=language,
        user_id=user_id,
        model_id=model_id,
        document_context=document_context,
        preferences=preferences,
        router=router,
        search_fn=search_fn,
        job_url=job_url,
        job_text=job_text,
        session=session,
        document_type=document_type,
        template_id=template_id,
    )


def _run_career_turn(
    text: str,
    *,
    mode: str,
    language: str,
    user_id: str | None,
    model_id: str | None,
    document_context: str,
    preferences: dict[str, Any] | None = None,
    router: ModelRouter | None = None,
    search_fn: Any | None = None,
    job_url: str | None = None,
    job_text: str | None = None,
    session: ChatSession | None = None,
    document_type: str | None = None,
    template_id: str | None = None,
) -> CareerTurn | None:
    """The routing and pipeline execution behind :func:`run_career_turn`."""
    has_cv = has_cv_content(document_context)
    analysis = analyse_input(text, job_url=job_url, job_text=job_text, cv_text=document_context)
    decisions = classify_intents(text, has_cv, mode, analysis)
    decision = decisions[0]
    logger.info(
        "career.intent intent=%s rule=%s input_kind=%s intents=%d",
        decision.intent.value,
        decision.rule_id,
        analysis.kind.value,
        len(decisions),
    )

    def _stamp(turn: CareerTurn) -> CareerTurn:
        """Attach the routing rule id (a constant label, never message content)."""
        if turn.rule_id:
            return turn
        return replace(turn, rule_id=decision.rule_id)

    if decision.intent is Intent.GENERAL:
        return None
    if decision.intent is Intent.CLARIFY:
        return _stamp(_clarify_turn(language))

    profile = profile_store.get(user_id) if user_id else None
    core_preferences = {key: value for key, value in (preferences or {}).items() if key != "treat_as_plain_text"}
    core, unmapped = core_from_payload(
        {**core_preferences, "language": language},
        user_id=user_id or "",
        cv_text=document_context,
        profile=profile,
    )
    if unmapped:
        logger.info("career.preferences_unmapped count=%d", len(unmapped))
    active_router = router or ModelRouter()

    if decision.intent is Intent.SEARCH_JOBS:
        return _stamp(_search_turn(core, model_id, active_router, search_fn=search_fn))

    # --- job-aware intents --------------------------------------------------
    needs_job = decision.intent in {Intent.MATCH_JOB, Intent.TAILOR_CV, Intent.COVER_LETTER}
    if not needs_job:
        simple = _simple_turn(decision.intent.value, text, core, model_id, active_router)
        return _stamp(simple) if simple is not None else None

    resolved, ingest_status = _resolve_job(text, analysis, job_url=job_url, job_text=job_text)
    used_session_job = False
    target: JobTarget | None = None
    if resolved is not None and resolved.status == "ok" and resolved.position is not None:
        try:
            target = build_job_target(resolved.position, router=active_router)
        except (ValidationError, ConfigurationError) as exc:
            logger.info("career.job_target_failed category=%s", type(exc).__name__)
            target = None
        if target is not None and session is not None:
            chat_store.set_session_job(session, _job_context_payload(target))
    elif resolved is None and session is not None:
        remembered = _target_from_session(session.job_context or session.session_job)
        if remembered is not None:
            target = remembered
            used_session_job = True
            ingest_status = "session"

    input_meta = {
        "kind": analysis.kind.value,
        "job_ingest_status": ingest_status or "",
        "used_session_job": used_session_job,
        "text_len": len(text or ""),
    }

    if ingest_status and ingest_status not in ("ok", "session", ""):
        return _stamp(
            _clarify_turn_for(
                language,
                missing=[],
                job_ingest_status=ingest_status,
                input_kind=analysis.kind.value,
                used_session_job=used_session_job,
            )
        )

    missing: list[str] = []
    if not has_cv:
        missing.append("cv")
    if target is None:
        missing.append("job")
    if missing:
        return _stamp(
            _clarify_turn_for(
                language,
                missing=missing,
                job_ingest_status=ingest_status,
                input_kind=analysis.kind.value,
                used_session_job=used_session_job,
            )
        )

    if target is None:
        # Guarded above (a missing job always returns a clarifying reply).
        return _stamp(
            _clarify_turn_for(
                language,
                missing=["job"],
                job_ingest_status=ingest_status,
                input_kind=analysis.kind.value,
                used_session_job=used_session_job,
            )
        )
    analysis_generator = active_router.generator_for("analysis", preferred_model_id=model_id)
    analysis_result = run_analysis(core, analysis_generator, preferred_model_id=model_id)

    if len(decisions) == 1:
        if decision.intent is Intent.MATCH_JOB:
            return _stamp(
                _match_turn(
                    core,
                    analysis_result,
                    target,
                    model_id=model_id,
                    generator=analysis_generator,
                    input_meta=input_meta,
                )
            )
        document_intent = "tailor_cv" if decision.intent is Intent.TAILOR_CV else "cover_letter"
        resolved_template, rag_block = _document_context(
            user_id,
            document_intent,
            template_id,
            target,
        )
        return _stamp(
            _document_turn(
                document_intent,
                core,
                analysis_result,
                target,
                model_id=model_id,
                router=active_router,
                input_meta=input_meta,
                template_id=resolved_template,
                rag_block=rag_block,
            )
        )
    return _stamp(
        _two_pipeline_turn(
            decisions,
            core,
            analysis_result,
            target,
            model_id=model_id,
            router=active_router,
            analysis_generator=analysis_generator,
            input_meta=input_meta,
            template_id=template_id,
        )
    )


def _two_pipeline_turn(
    decisions: tuple[Any, ...],
    core: UserCore,
    analysis_result: AnalysisResult,
    target: JobTarget,
    *,
    model_id: str | None,
    router: ModelRouter,
    analysis_generator: Any,
    input_meta: dict[str, Any],
    template_id: str | None,
) -> CareerTurn:
    """Run at most two pipelines: match the job, then write the document."""
    match_turn = _match_turn(
        core,
        analysis_result,
        target,
        model_id=model_id,
        generator=analysis_generator,
        input_meta=input_meta,
    )
    document_intent = decisions[1].intent.value
    document_turn = _document_turn(
        document_intent,
        core,
        analysis_result,
        target,
        model_id=model_id,
        router=router,
        input_meta=input_meta,
        template_id=template_id,
        rag_block="",
    )
    steps = [match_turn.structured, document_turn.structured]
    structured = {
        "intent": match_turn.intent,
        "input": input_meta,
        "steps": steps,
        "match": match_turn.structured["match"],
        "job": match_turn.structured["job"],
        "document": document_turn.structured["document"],
        "grounding": document_turn.structured["grounding"],
        "gaps": document_turn.structured["gaps"],
    }
    content = f"{match_turn.content}\n\n{document_turn.content}"
    return CareerTurn(
        intent=match_turn.intent,
        content=content,
        structured=structured,
        ai_generated=match_turn.ai_generated or document_turn.ai_generated,
        prompt_version=document_turn.prompt_version,
        models=match_turn.models + document_turn.models,
        notices=match_turn.notices + document_turn.notices,
        attempts=match_turn.attempts + document_turn.attempts,
        task=document_turn.task,
        input_kind=match_turn.input_kind,
        job_ingest_status=match_turn.job_ingest_status,
        source_host=match_turn.source_host,
    )
