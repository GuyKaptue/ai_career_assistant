"""Unit tests for chat input analysis (Stage A + B): validate, clean, classify.

All job/CV samples here are synthetic strings written for the test — never real
user data.
"""

import pytest

from app.application.services import chat_input as ci
from app.application.services.chat_input import InputKind

EN_JOB = """Senior Python Developer (m/w/d)
Acme GmbH, Berlin

Responsibilities:
- Design and build FastAPI services used by thousands of customers
- Review pull requests and mentor junior engineers on the team
- Operate services in production with Docker and Kubernetes
- Document the APIs and keep them observable with metrics

Requirements:
- Five or more years of Python in a production environment
- Strong FastAPI and PostgreSQL knowledge, REST and messaging
- Comfortable with CI/CD pipelines, Git and code review
- Excellent written and spoken English

We offer a full-time position with an attractive salary, flexible hours
and a modern stack. Apply now with your CV and a short introduction.
"""

DE_JOB = """Softwareentwickler Backend (m/w/d)
Müller & Söhne AG, Köln

Aufgaben:
- Entwicklung von Schnittstellen mit Python und FastAPI
- Code-Reviews schreiben und Tests durchführen
- Betrieb der Dienste mit Docker unterstützen
- Dokumentation der Architektur pflegen

Anforderungen:
- Berufserfahrung mit Python und SQL in Produktion
- Sicherer Umgang mit Git, CI/CD und PostgreSQL
- Gute Deutschkenntnisse und Teamfähigkeit

Wir bieten ein Vollzeit-Verhältnis mit unbefristeter Anstellung,
attraktiver Vergütung und flexibler Arbeitszeit. Jetzt bewerben.
"""

FR_JOB = """Développeur Python (H/F/X)
Nova SAS, Paris

Missions:
- Développer des API robustes en Python et FastAPI
- Réaliser les revues de code et les tests
- Assurer la maintenance des services avec Docker
- Documenter les interfaces et les métriques

Profil recherché:
- Python et SQL maîtrisés, notions de REST
- Anglais technique courant
- Esprit d'équipe et autonomie

Nous offrons un CDI temps plein, un salaire attrayant et le télétravail.
Postulez dès maintenant avec votre CV.
"""

CV_SAMPLE = """John Smith
Python Developer

Summary
Backend developer with six years of experience designing, building and
operating reliable web services for product teams.

Experience
- Built internal tools at Acme Corp using Python and FastAPI
- Maintained CI pipelines, releases and automated deployments
- Wrote API documentation and mentored junior developers
- Improved query performance across several PostgreSQL databases

Education
Bachelor of Science in Computer Science, Technical University, 2018.

Skills
Python, FastAPI, PostgreSQL, Docker, Git, communication and mentoring.
"""


class TestUrlDetection:
    def test_bare_url_is_a_job_url(self):
        analysis = ci.analyse_input("Check this job https://example.com/jobs/123")
        assert analysis.kind is InputKind.JOB_URL
        assert analysis.job_url == "https://example.com/jobs/123"
        assert analysis.urls == ("https://example.com/jobs/123",)
        assert analysis.instruction == "Check this job"

    @pytest.mark.parametrize("trailing", [".", ",", "!", "?", ")", ";"])
    def test_trailing_punctuation_is_stripped(self, trailing):
        analysis = ci.analyse_input(f"See https://example.com/job{trailing}")
        assert analysis.job_url == "https://example.com/job"

    @pytest.mark.parametrize(
        "bad",
        ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "ftp://x/y", "vbscript:x"],
    )
    def test_bad_schemes_are_rejected(self, bad):
        assert ci.valid_http_url(bad) is None

    def test_bad_scheme_in_message_yields_no_url(self):
        analysis = ci.analyse_input("run javascript:alert(1) now")
        assert analysis.kind is InputKind.QUESTION
        assert analysis.job_url is None

    def test_urls_are_capped_at_three(self):
        message = " ".join(f"https://example.com/{index}" for index in range(1, 5))
        analysis = ci.analyse_input(message)
        assert len(analysis.urls) == 3
        assert analysis.kind is InputKind.JOB_URL

    def test_explicit_invalid_job_url_falls_through(self):
        analysis = ci.analyse_input("hello", job_url="ftp://example.com/x")
        assert analysis.kind is InputKind.QUESTION
        assert analysis.job_url is None

    def test_explicit_valid_job_url_wins(self):
        analysis = ci.analyse_input("look at this", job_url="https://example.com/a.")
        assert analysis.kind is InputKind.JOB_URL
        assert analysis.job_url == "https://example.com/a"


class TestJobDescriptionDetection:
    @pytest.mark.parametrize("sample", [EN_JOB, DE_JOB, FR_JOB], ids=["en", "de", "fr"])
    def test_long_pasted_posting_is_a_job_description(self, sample):
        analysis = ci.analyse_input(sample)
        assert analysis.kind is InputKind.JOB_DESCRIPTION
        assert analysis.job_text_candidate is not None
        assert len(analysis.job_text_candidate) >= ci.JD_MIN_CHARS
        assert ci.JD_STRONG_SIGNALS.intersection(analysis.signals)

    @pytest.mark.parametrize("sample", [EN_JOB, DE_JOB, FR_JOB], ids=["en", "de", "fr"])
    def test_bare_posting_has_no_forced_instruction(self, sample):
        analysis = ci.analyse_input(sample)
        assert analysis.instruction is None

    def test_short_message_is_a_question(self):
        analysis = ci.analyse_input("How should I structure my CV?")
        assert analysis.kind is InputKind.QUESTION
        assert analysis.job_text_candidate is None

    def test_cv_pasted_by_mistake_is_not_a_job(self):
        analysis = ci.analyse_input(CV_SAMPLE)
        assert len(CV_SAMPLE) >= ci.JD_MIN_CHARS
        assert analysis.kind is not InputKind.JOB_DESCRIPTION
        assert analysis.kind is InputKind.QUESTION

    def test_skill_overlap_signal_when_shared_with_cv(self):
        analysis = ci.analyse_input(EN_JOB, cv_text="Python FastAPI")
        assert "skill_overlap" in analysis.signals

    def test_explicit_job_text_wins(self):
        analysis = ci.analyse_input("match please", job_text=EN_JOB)
        assert analysis.kind is InputKind.JOB_DESCRIPTION
        assert analysis.signals == ["explicit_job_text"]
        assert analysis.job_text_candidate == EN_JOB.strip()


class TestInstructionSplit:
    def test_instruction_before_posting_is_split_off(self):
        analysis = ci.analyse_input(f"Match my CV with this job:\n{EN_JOB}")
        assert analysis.kind is InputKind.JOB_DESCRIPTION
        assert analysis.instruction == "Match my CV with this job"
        assert analysis.job_text_candidate == EN_JOB.strip()

    def test_split_helper_returns_lead_in_and_payload(self):
        instruction, payload = ci.split_instruction(f"Tailor my CV for this role: {EN_JOB}")
        assert instruction == "Tailor my CV for this role"
        assert payload.strip() == EN_JOB.strip()

    def test_bare_posting_is_not_split(self):
        instruction, payload = ci.split_instruction(EN_JOB)
        assert instruction is None
        assert payload == EN_JOB


class TestCleanAndLanguage:
    def test_zero_width_and_control_chars_are_removed(self):
        assert ci.clean_text("a\u200bb\x00c") == "abc"

    def test_whitespace_is_collapsed(self):
        assert ci.clean_text("  too   many \t spaces  ") == "too many spaces"

    def test_newlines_are_preserved_but_blank_runs_collapsed(self):
        assert ci.clean_text("a\n\n\n\nb") == "a\n\nb"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("This is the job for you and we will hire", "en"),
            ("Das ist die Stelle und ich nicht mit Ihnen", "de"),
            ("Le travail et vous avec nous dans la equipe", "fr"),
        ],
    )
    def test_language_detection(self, text, expected):
        assert ci.detect_language(text) == expected

    def test_language_fallback_breaks_ties_and_empty(self):
        assert ci.detect_language("   ", fallback="de") == "de"
        assert ci.detect_language("!!?!", fallback="fr") == "fr"

    def test_invalid_fallback_defaults_to_english(self):
        assert ci.detect_language("zzz", fallback="xx") == "en"


class TestEmptyAndLimits:
    @pytest.mark.parametrize("raw", [None, "", "   \n\t "])
    def test_empty_input(self, raw):
        analysis = ci.analyse_input(raw)
        assert analysis.kind is InputKind.EMPTY
        assert analysis.length == 0

    def test_message_limit_returns_clear_error(self):
        too_long = "x" * (ci.MESSAGE_MAX_CHARS + 1)
        error = ci.input_limits_error(message=too_long)
        assert error is not None
        assert str(ci.MESSAGE_MAX_CHARS) in error

    def test_job_text_limit(self):
        error = ci.input_limits_error(job_text="y" * (ci.JOB_TEXT_MAX_CHARS + 1))
        assert error is not None

    def test_document_context_limit(self):
        error = ci.input_limits_error(document_context="z" * (ci.DOCUMENT_CONTEXT_MAX_CHARS + 1))
        assert error is not None

    def test_within_limits_returns_none(self):
        assert ci.input_limits_error("short", EN_JOB, CV_SAMPLE) is None


LONG_URL_POSTING = EN_JOB + "\nSee the original posting at https://example.com/jobs/123 for details.\n"

SYNTHETIC_CV = """Alex Rivera
Backend Engineer

Key responsibilities:
- Built internal APIs used by support teams
- Maintained deployment pipelines and dashboards
- Wrote design docs and mentored new joiners
- Improved database queries for reporting tools
- Automated routine checks across environments

Work history
Six years building backend services for product teams in Berlin.
Focused on reliability, testing and clear documentation habits.

Education
Bachelor of Science in Computer Science, 2018.

Skills
Python, SQL, Docker, Git, communication and mentoring.
"""


class TestReviewFixes:
    """Failing-first tests for the chat_input.py review (five bugs + extras)."""

    def test_description_wins_over_embedded_url(self):
        assert len(LONG_URL_POSTING) >= ci.JD_MIN_CHARS
        analysis = ci.analyse_input(LONG_URL_POSTING)
        assert analysis.kind is InputKind.JOB_DESCRIPTION
        assert analysis.instruction is None
        assert analysis.job_url == "https://example.com/jobs/123"
        assert analysis.urls == ("https://example.com/jobs/123",)
        assert analysis.job_text_candidate is not None
        assert "Responsibilities" in analysis.job_text_candidate

    @pytest.mark.parametrize("word", ["permissions", "admissions", "submissions"])
    def test_substrings_do_not_fire_section_words(self, word):
        assert "section_words" not in ci._job_description_signals(f"User {word} review")
        analysis = ci.analyse_input(f"How do {word} work?")
        assert "section_words" not in analysis.signals

    def test_synthetic_cv_with_responsibilities_header_is_question(self):
        assert len(SYNTHETIC_CV) >= ci.JD_MIN_CHARS
        analysis = ci.analyse_input(SYNTHETIC_CV)
        assert analysis.kind is InputKind.QUESTION
        assert "cv_markers" in analysis.signals

    def test_title_first_line_is_not_split_off(self):
        text = f"Backend Engineer \u2013 Search Team\n{EN_JOB}"
        instruction, payload = ci.split_instruction(text)
        assert instruction is None
        assert payload == text

    def test_colon_title_without_pronoun_is_not_split(self):
        text = f"Backend Engineer \u2013 Search: join our team and build great things.\n{EN_JOB}"
        instruction, payload = ci.split_instruction(text)
        assert instruction is None
        assert payload == text

    def test_cv_markers_veto_skipped_with_hiring_phrase(self):
        posting = (
            "Backend Engineer \u2013 Platform Team\n"
            + EN_JOB
            + "\nEducation\nBachelor of Science in Computer Science, 2018.\n"
            "Languages\nEnglish fluent, German basic.\n"
            "Skills\nPython, SQL, Docker, Git and clear documentation habits.\n"
        )
        assert len(posting) >= ci.JD_MIN_CHARS
        analysis = ci.analyse_input(posting)
        assert "cv_markers" in analysis.signals
        assert analysis.kind is InputKind.JOB_DESCRIPTION

    @pytest.mark.parametrize(
        "bad",
        [
            "http://",
            "https://user:pass@host/x",
            f"https://example.com/{'a' * 3000}",
            "https://exa mple.com",
        ],
    )
    def test_strict_url_validation_rejects(self, bad):
        assert ci.valid_http_url(bad) is None

    def test_invalid_explicit_job_url_adds_signal(self):
        analysis = ci.analyse_input("hello", job_url="ftp://example.com/x")
        assert analysis.kind is InputKind.QUESTION
        assert analysis.job_url is None
        assert "invalid_explicit_url" in analysis.signals

    def test_folded_umlaut_counts_for_language_detection(self):
        assert ci.detect_language("F\u00fcr", fallback="en") == "de"

    def test_urls_is_a_tuple(self):
        analysis = ci.analyse_input("Check this job https://example.com/jobs/123")
        assert isinstance(analysis.urls, tuple)
        assert analysis.urls == ("https://example.com/jobs/123",)

    def test_skill_vocabulary_is_casefold_normalized(self):
        from app.domain.cv.skill_vocabulary import SKILL_VOCABULARY

        assert [s for s in SKILL_VOCABULARY if s != s.casefold()] == []
        assert {"python", "fastapi"} <= ci._skills_in("PYTHON and FastAPI")
