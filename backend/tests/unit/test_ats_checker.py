"""Unit tests for the ATS checker scoring pipeline (BE-03)."""

from __future__ import annotations

import pytest

from app.application.services.ats_checker import (
    _aggregate,
    _avg_sentence_length,
    _avg_word_length,
    _build_explanation,
    _compute_format_score,
    _compute_keyword_score,
    _compute_readability_score,
    _count_sections,
    _normalise_tokens,
    check_resume_against_job,
)


class TestNormaliseTokens:
    def test_lowercases_and_splits(self):
        tokens = _normalise_tokens("Python SQL Analytics")
        assert tokens == {"python", "sql", "analytics"}

    def test_treats_slashes_and_dashes_as_separators(self):
        tokens = _normalise_tokens("data/analytics machine-learning")
        assert "data" in tokens
        assert "analytics" in tokens
        assert "machine" in tokens
        assert "learning" in tokens

    def test_empty_text(self):
        assert _normalise_tokens("") == set()


class TestKeywordScore:
    def test_perfect_match(self):
        score, matched, missing = _compute_keyword_score("Python SQL analytics", "Python SQL analytics")
        assert score == 100.0
        assert matched == ("analytics", "python", "sql")
        assert missing == ()

    def test_partial_match(self):
        score, matched, missing = _compute_keyword_score("Python SQL", "Python SQL analytics")
        assert score == pytest.approx(200.0 / 3.0, abs=0.1)
        assert "analytics" in missing

    def test_no_match(self):
        score, matched, missing = _compute_keyword_score("java rust", "Python SQL")
        assert score == 0.0
        assert matched == ()
        assert set(missing) == {"python", "sql"}

    def test_empty_job_description(self):
        score, matched, missing = _compute_keyword_score("Python", "")
        assert score == 0.0
        assert matched == ()
        assert missing == ()


class TestFormatScore:
    def test_well_structured_resume(self):
        text = (
            "Summary\nExperienced analyst.\n\n"
            "Experience\nBuilt dashboards.\n\n"
            "Education\nBS Computer Science.\n\n"
            "Skills\nPython, SQL"
        )
        score = _compute_format_score(text)
        assert score >= 70

    def test_short_text_scores_low(self):
        score = _compute_format_score("Python SQL")
        assert score < 50

    def test_empty_text(self):
        score = _compute_format_score("")
        assert score == 0.0


class TestReadabilityScore:
    def test_short_sentences_score_high(self):
        text = "I am a developer. I write code. It works well."
        score = _compute_readability_score(text)
        assert score >= 80

    def test_long_sentences_score_low(self):
        text = (
            "This is a very long sentence that contains many words and "
            "goes on and on without any punctuation to break it up at all "
            "which makes it hard to read and understand for most people "
            "because it just keeps adding more and more words to the "
            "sentence without ever stopping to take a breath or pause "
            "which is why it is so difficult to follow the thread of "
            "the argument that is being presented here in this way."
        )
        score = _compute_readability_score(text)
        assert score < 80

    def test_empty_text(self):
        score = _compute_readability_score("")
        assert score == 0.0


class TestSentenceAndWordLength:
    def test_avg_sentence_length(self):
        text = "One two three. Four five."
        assert _avg_sentence_length(text) == pytest.approx(2.5)

    def test_avg_word_length(self):
        text = "cat dog elephant"
        assert _avg_word_length(text) == pytest.approx((3 + 3 + 8) / 3)


class TestCountSections:
    def test_counts_known_sections(self):
        text = "Summary\nSome text.\nExperience\nMore text.\nSkills\nPython"
        assert _count_sections(text) >= 3

    def test_counts_title_case_headings(self):
        text = "Professional Experience\nSome text here."
        assert _count_sections(text) >= 1


class TestAggregate:
    def test_perfect_scores(self):
        assert _aggregate(100.0, 100.0, 100.0) == 100.0

    def test_zero_scores(self):
        assert _aggregate(0.0, 0.0, 0.0) == 0.0

    def test_weighted_average(self):
        # 0.5*80 + 0.25*60 + 0.25*40 = 40 + 15 + 10 = 65
        assert _aggregate(80.0, 60.0, 40.0) == pytest.approx(65.0)

    def test_clamps_to_100(self):
        assert _aggregate(100.0, 100.0, 100.0) == 100.0


class TestBuildExplanation:
    def test_contains_components(self):
        explanation = _build_explanation(75.0, 80.0, 70.0, 60.0, 5, 2)
        assert "75" in explanation
        assert "keyword" in explanation.lower()
        assert "format" in explanation.lower()
        assert "readability" in explanation.lower()
        assert "5" in explanation
        assert "2" in explanation


class TestCheckResumeAgainstJob:
    def test_returns_all_eight_keys(self):
        result = check_resume_against_job(
            "Summary\nPython developer.\nExperience\nBuilt apps.\nSkills\nPython",
            "Python developer",
        )
        assert set(result.keys()) == {
            "score",
            "matched_keywords",
            "missing_keywords",
            "strengths",
            "suggestions",
            "keyword_overlap",
            "formatting_score",
            "readability_score",
            "explanation",
        }

    def test_requires_job_description(self):
        with pytest.raises(ValueError, match="job description is required"):
            check_resume_against_job("Python", "")

    def test_high_keyword_match_scores_well(self):
        resume = (
            "Summary\nExperienced Python developer with SQL skills.\n\n"
            "Experience\nBuilt analytics dashboards.\n\n"
            "Education\nBS Computer Science.\n\n"
            "Skills\nPython, SQL, analytics, dashboard"
        )
        job = "Python SQL analytics dashboard"
        result = check_resume_against_job(resume, job)
        assert result["score"] >= 70
        assert "python" in result["matched_keywords"]

    def test_missing_keywords_are_reported(self):
        result = check_resume_against_job("Python", "Python SQL analytics")
        assert "sql" in result["missing_keywords"]
        assert "analytics" in result["missing_keywords"]

    def test_scores_are_in_range(self):
        result = check_resume_against_job(
            "Summary\nPython developer.\nExperience\nBuilt apps.",
            "Python developer",
        )
        assert 0 <= result["score"] <= 100
        assert 0 <= result["formatting_score"] <= 100
        assert 0 <= result["readability_score"] <= 100
        assert 0.0 <= result["keyword_overlap"] <= 1.0
