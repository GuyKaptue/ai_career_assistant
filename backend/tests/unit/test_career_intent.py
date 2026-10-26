"""Unit tests for career intent classification."""

from __future__ import annotations

import pytest

from app.application.services.career_intent import (
    Intent,
    _has_cv_token,
    _normalize_text,
    classify_intent,
    has_cv_content,
)
from app.application.services.chat_input import InputAnalysis, InputKind


def test_has_cv_content():
    assert has_cv_content("some cv text")
    assert not has_cv_content("")
    assert not has_cv_content(None)
    assert has_cv_content("x")


def test_normalize_text_umlauts():
    assert _normalize_text("Vorstellungsgespräch") == "vorstellungsgespraech"
    assert _normalize_text("Vorstellungsgespraech") == "vorstellungsgespraech"
    assert _normalize_text("Café") == "cafe"  # all accents are stripped


def test_has_cv_token():
    tokens = {"cv", "job"}
    assert _has_cv_token(tokens)
    tokens = {"lebenslauf", "stelle"}
    assert _has_cv_token(tokens)
    tokens = {"curriculum", "job"}
    assert _has_cv_token(tokens)
    tokens = {"curriculo", "vaga"}
    assert _has_cv_token(tokens)
    tokens = {"job", "search"}
    assert not _has_cv_token(tokens)


def test_search_jobs_english():
    d = classify_intent("please use this cv to help me search a corresponding jobs for me", has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS
    d2 = classify_intent("find jobs that match my CV", has_cv=True)
    assert d2.intent == Intent.SEARCH_JOBS


def test_search_jobs_german():
    d = classify_intent("Suche passende Stellen zu meinem Lebenslauf", has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS


def test_search_jobs_french():
    d = classify_intent("Trouve-moi des offres d'emploi correspondant a mon CV", has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS


def test_summarize_cv():
    d = classify_intent("summarize my CV", has_cv=True)
    assert d.intent == Intent.SUMMARIZE_CV
    d = classify_intent("Fasse meinen Lebenslauf zusammen", has_cv=True)
    assert d.intent == Intent.SUMMARIZE_CV


def test_improve_cv():
    d = classify_intent("improve my CV", has_cv=True)
    assert d.intent == Intent.IMPROVE_CV
    d = classify_intent("Verbessere meinen Lebenslauf", has_cv=True)
    assert d.intent == Intent.IMPROVE_CV


def test_skill_gap():
    d = classify_intent("what skills am I missing for ML engineer roles?", has_cv=True)
    assert d.intent == Intent.SKILL_GAP
    d = classify_intent("what is my skill gap for data science?", has_cv=True)
    assert d.intent == Intent.SKILL_GAP
    d = classify_intent("missing skills for python developer", has_cv=True)
    assert d.intent == Intent.SKILL_GAP


def test_interview_prep():
    d = classify_intent("prepare me for an interview", has_cv=True)
    assert d.intent == Intent.INTERVIEW_PREP
    d = classify_intent("Bereite mich auf ein Vorstellungsgespräch vor", has_cv=True)
    assert d.intent == Intent.INTERVIEW_PREP
    d = classify_intent("Bereite mich auf ein Vorstellungsgespraech vor", has_cv=True)
    assert d.intent == Intent.INTERVIEW_PREP
    d = classify_intent("prepare me for an interview", has_cv=False)
    assert d.intent == Intent.INTERVIEW_PREP


def test_general():
    d = classify_intent("what's a good way to negotiate salary?", has_cv=True)
    assert d.intent == Intent.GENERAL
    d = classify_intent("hello", has_cv=False)
    assert d.intent == Intent.GENERAL
    d = classify_intent("", has_cv=True)
    assert d.intent == Intent.GENERAL
    d = classify_intent("   ", has_cv=True)
    assert d.intent == Intent.GENERAL


def test_missing_cv_clarify():
    d = classify_intent("find jobs that match my CV", has_cv=False)
    assert d.intent == Intent.CLARIFY
    d = classify_intent("summarize my CV", has_cv=False)
    assert d.intent == Intent.CLARIFY
    d = classify_intent("improve my CV", has_cv=False)
    assert d.intent == Intent.CLARIFY
    d = classify_intent("what skills am I missing for ML engineer roles?", has_cv=False)
    assert d.intent == Intent.CLARIFY


def test_precedence_improve_over_search():
    d = classify_intent("improve my CV so I find jobs", has_cv=True)
    assert d.intent == Intent.IMPROVE_CV


def test_mixed_language():
    d = classify_intent("search jobs for my CV", has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS
    d = classify_intent("Suche jobs für meinen CV", has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS


def test_injection_does_not_steer():
    d = classify_intent("summarize my cv", has_cv=True)
    assert d.intent == Intent.SUMMARIZE_CV


def test_very_long_message():
    long_msg = "please help me find a job " * 100
    d = classify_intent(long_msg, has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS


def test_german_interview_without_umlaut():
    d = classify_intent("Vorstellungsgespraech vorbereitung", has_cv=True)
    assert d.intent == Intent.INTERVIEW_PREP


def test_french_interview():
    d = classify_intent("préparation entretien", has_cv=True)
    assert d.intent == Intent.INTERVIEW_PREP


def test_skill_gap_fehlende():
    d = classify_intent("welche fehlende skills habe ich?", has_cv=True)
    assert d.intent == Intent.SKILL_GAP


def test_improve_cv_german():
    d = classify_intent("verbessere meinen Lebenslauf", has_cv=True)
    assert d.intent == Intent.IMPROVE_CV


def test_french_trouve_branch():
    d = classify_intent("trouve offre pour mon cv", has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS
    d = classify_intent("trouve emploi", has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS
    d = classify_intent("trouve offre", has_cv=True)
    assert d.intent == Intent.SEARCH_JOBS
    d = classify_intent("trouve", has_cv=True)
    assert d.intent == Intent.GENERAL


def test_french_trouve_without_cv():
    d = classify_intent("trouve offre pour mon cv", has_cv=False)
    assert d.intent == Intent.CLARIFY
    d = classify_intent("trouve emploi", has_cv=False)
    assert d.intent == Intent.CLARIFY


def test_empty_and_whitespace():
    d = classify_intent("", has_cv=True)
    assert d.intent == Intent.GENERAL
    assert d.rule_id == "empty"
    d = classify_intent("   ", has_cv=True)
    assert d.intent == Intent.GENERAL
    assert d.rule_id == "empty"


def test_fallback_general():
    d = classify_intent("random text that matches nothing", has_cv=True)
    assert d.intent == Intent.GENERAL
    assert d.rule_id == "general"


def test_french_accents_and_resume_synonym():
    from app.application.services.career_intent import Intent, classify_intent

    assert classify_intent("Améliorer mon CV", True).intent is Intent.IMPROVE_CV
    assert classify_intent("improve my résumé", True).intent is Intent.IMPROVE_CV
    assert classify_intent("Quelles compétences me manquent ?", True).intent is Intent.SKILL_GAP


def test_no_substring_false_positives():
    from app.application.services.career_intent import Intent, classify_intent

    assert classify_intent("I did research on remote work, any jobless-rate data?", True).intent is Intent.GENERAL
    assert classify_intent("Erfasse bitte meine Arbeitszeiten", True).intent is Intent.GENERAL


def test_writing_advice_about_a_cv_summary_is_general_not_summarize():
    from app.application.services.career_intent import Intent, classify_intent

    for phrase in (
        "How do I write a strong CV summary?",
        "How do I write my CV summary?",
        "Wie schreibe ich eine gute Zusammenfassung im Lebenslauf?",
        "Give me examples of a good CV summary",
    ):
        assert classify_intent(phrase, True).intent is Intent.GENERAL, phrase
    assert classify_intent("Give me a summary of my CV", True).intent is Intent.SUMMARIZE_CV
    assert classify_intent("Fasse meinen Lebenslauf kurz zusammen", True).intent is Intent.SUMMARIZE_CV


def _analysis(kind: InputKind) -> InputAnalysis:
    return InputAnalysis(
        kind=kind,
        urls=(),
        job_url=None,
        job_text_candidate=None,
        instruction=None,
        signals=[],
        length=0,
    )


@pytest.mark.parametrize(
    ("message", "rule_id"),
    [
        ("Draft a cover letter for this job posting", "cover_letter"),
        ("Erstelle ein Anschreiben für diese Stelle", "cover_letter"),
        ("Rédige une lettre de motivation pour cette offre", "cover_letter"),
    ],
)
def test_cover_letter_needs_generation_verb_trilingual(message: str, rule_id: str):
    decision = classify_intent(message, True)
    assert decision.intent is Intent.COVER_LETTER
    assert decision.rule_id == rule_id


@pytest.mark.parametrize(
    "message",
    [
        "Improve my cover letter",
        "Review my cover letter",
        "Check my cover letter",
        "Proofread my cover letter",
        "Verbessere mein Anschreiben",
    ],
)
def test_cover_letter_without_generation_verb_is_general(message: str):
    assert classify_intent(message, True).intent is Intent.GENERAL


def test_french_relecture_without_generation_verb_is_general():
    # "Relis" (re-read/review) is editing advice, not generation.
    assert classify_intent("Relis ma lettre de motivation", True).intent is Intent.GENERAL
    assert classify_intent("Relis mon lettre de motivation", True).intent is Intent.GENERAL


def test_cover_letter_with_job_in_analysis_without_verb():
    decision = classify_intent(
        "My cover letter for this role",
        True,
        analysis=_analysis(InputKind.JOB_DESCRIPTION),
    )
    assert decision.intent is Intent.COVER_LETTER
    assert decision.rule_id == "cover_letter_from_analysis"


@pytest.mark.parametrize(
    "message",
    [
        "match jobs to my CV",
        "match my CV with open roles",
    ],
)
def test_plural_match_stays_search_jobs(message: str):
    assert classify_intent(message, True).intent is Intent.SEARCH_JOBS


def test_match_against_this_job_without_analysis_is_match_job():
    decision = classify_intent("match my CV against this job", True)
    assert decision.intent is Intent.MATCH_JOB
    assert decision.rule_id == "match_job"


def test_cover_letter_generation_verb_still_wins():
    assert classify_intent("Write a cover letter for this job", True).intent is Intent.COVER_LETTER
    assert classify_intent("Draft my cover letter", True).intent is Intent.COVER_LETTER


@pytest.mark.parametrize(
    ("message", "rule_id"),
    [
        ("Tailor my CV to this job posting", "tailor_cv"),
        ("Passe meinen Lebenslauf an diese Stelle an", "tailor_cv"),
        ("Adapte mon CV à cette offre", "tailor_cv"),
    ],
)
def test_tailor_cv_intent_trilingual(message: str, rule_id: str):
    decision = classify_intent(message, True)
    assert decision.intent is Intent.TAILOR_CV
    assert decision.rule_id == rule_id


@pytest.mark.parametrize(
    ("message", "rule_id"),
    [
        ("Match my CV against this job", "match_job"),
        ("Vergleiche meinen Lebenslauf mit dieser Stelle", "match_job"),
        ("Compare mon CV avec cette offre", "match_job"),
    ],
)
def test_match_job_intent_trilingual(message: str, rule_id: str):
    decision = classify_intent(message, True)
    assert decision.intent is Intent.MATCH_JOB
    assert decision.rule_id == rule_id


def test_writing_advice_stays_general_not_cover_letter():
    assert classify_intent("How do I write a strong CV summary?", True).intent is Intent.GENERAL


def test_find_jobs_for_cv_stays_search_jobs():
    assert classify_intent("find jobs for my CV", True).intent is Intent.SEARCH_JOBS


def test_bare_url_becomes_match_job():
    decision = classify_intent("https://example.com/jobs/123", True, analysis=_analysis(InputKind.JOB_URL))
    assert decision.intent is Intent.MATCH_JOB
    assert decision.rule_id == "match_job_from_analysis"


def test_bare_job_text_becomes_match_job():
    decision = classify_intent("Senior Python Developer ...", True, analysis=_analysis(InputKind.JOB_DESCRIPTION))
    assert decision.intent is Intent.MATCH_JOB
    assert decision.rule_id == "match_job_from_analysis"


def test_existing_signature_without_analysis_keeps_working():
    assert classify_intent("find jobs that match my CV", True).intent is Intent.SEARCH_JOBS
    assert classify_intent("", True).intent is Intent.GENERAL


def test_quick_match_prefill_german_is_match_job():
    # From frontend locale de.js quickMatchPrefill.
    d = classify_intent("Passt mein Lebenslauf zu dieser Stelle?", has_cv=True)
    assert d.intent is Intent.MATCH_JOB


def test_quick_match_prefill_french_is_match_job():
    # From frontend locale fr.js quickMatchPrefill.
    d = classify_intent("Mon CV correspond-il a cette offre ?", has_cv=True)
    assert d.intent is Intent.MATCH_JOB


def test_match_negative_stays_general():
    cases = [
        "Das passt mir nicht",
        "Das passt so",
        "Ça correspond à ma question",
        "Passt das Wetter morgen?",
        "Passt mein Lebenslauf zu dieser Stelle?",  # placeholder replaced below
    ]
    # A match sentence with no CV and no job context in message or session.
    no_context = "Does it match?"
    cases = [
        "Das passt mir nicht",
        "Das passt so",
        "Ça correspond à ma question",
        "Passt das Wetter morgen?",
        no_context,
    ]
    for m in cases:
        d = classify_intent(m, has_cv=True)
        assert d.intent is Intent.GENERAL, (m, d.intent)
