from __future__ import annotations

from pathlib import Path

import pytest

from app.application.services.ai_model_router import (
    MODEL_UNAVAILABLE,
    QUOTA_EXCEEDED,
    RATE_LIMITED,
    HuggingFaceInferenceAdapter,
    HuggingFaceModelRouter,
    ModelMetadata,
    classify_failure,
)
from app.application.services.cv_pdf_extractor import extract_resume_text_from_pdf, extract_text_from_pdf_bytes
from app.domain.documents.schemas import CVGenerationResult
from app.infrastructure.ai.prompts.cv import build_cv_prompt
from app.infrastructure.ai.prompts.resignation import (
    build_resignation_prompt,
)
from app.infrastructure.ai.prompts.resume_analysis import (
    build_resume_analysis_prompt,
)


def test_huggingface_router_selects_best_model_for_cv_generation() -> None:
    router = HuggingFaceModelRouter(
        models=[
            ModelMetadata(
                model_id="mistralai/Mistral-7B-Instruct-v0.3",
                task_capabilities=("cv-generation", "cover-letter", "resume-analysis"),
                context_window=32768,
                quality_score=0.92,
                health_status="healthy",
                license="apache-2.0",
                enabled=True,
            ),
            ModelMetadata(
                model_id="google/gemma-2-9b-it",
                task_capabilities=("resume-analysis",),
                context_window=8192,
                quality_score=0.84,
                health_status="healthy",
                enabled=True,
            ),
        ]
    )

    selected = router.select_model(task="cv-generation", token_budget=3500)

    assert selected.model_id == "mistralai/Mistral-7B-Instruct-v0.3"
    assert selected.health_status == "healthy"


def test_huggingface_router_falls_back_when_first_model_is_unhealthy() -> None:
    router = HuggingFaceModelRouter(
        models=[
            ModelMetadata(
                model_id="mistralai/Mistral-7B-Instruct-v0.3",
                task_capabilities=("cv-generation",),
                context_window=32768,
                quality_score=0.91,
                health_status="degraded",
                license="apache-2.0",
                enabled=True,
            ),
            ModelMetadata(
                model_id="microsoft/Phi-3-mini-4k-instruct",
                task_capabilities=("cv-generation", "resume-analysis"),
                context_window=4096,
                quality_score=0.79,
                health_status="healthy",
                license="mit",
                enabled=True,
            ),
        ]
    )

    selected = router.select_model(task="cv-generation", token_budget=2500)

    assert selected.model_id == "microsoft/Phi-3-mini-4k-instruct"


def test_cv_prompt_never_fabricates_facts() -> None:
    prompt = build_cv_prompt("Jane", "Analyst", "", [], [], [], "en")

    assert "Not provided" in prompt
    assert "Do NOT invent" in prompt


def test_inference_adapter_fails_closed_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    adapter = HuggingFaceInferenceAdapter(
        router=HuggingFaceModelRouter(
            models=[
                ModelMetadata(
                    model_id="test/model",
                    task_capabilities=("cv_generation",),
                    license="apache-2.0",
                    context_window=8192,
                ),
            ]
        )
    )

    with pytest.raises(RuntimeError, match=MODEL_UNAVAILABLE):
        adapter.generate_with_fallback(task="cv_generation", prompt="hello")


def test_inference_adapter_uses_fake_client_with_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "test-token")
    adapter = HuggingFaceInferenceAdapter(
        router=HuggingFaceModelRouter(
            models=[
                ModelMetadata(
                    model_id="test/model",
                    task_capabilities=("cv_generation",),
                    context_window=8192,
                    max_output_tokens=512,
                    quality_score=0.9,
                    health_status="healthy",
                    license="apache-2.0",
                ),
            ]
        )
    )

    def fake_call(self: object, model: ModelMetadata, prompt: str, max_new_tokens: int) -> str:
        assert prompt
        return "Summary\nExperienced analyst."

    monkeypatch.setattr(HuggingFaceInferenceAdapter, "_call_model", fake_call)
    result = adapter.generate_with_fallback(task="cv_generation", prompt="make cv")

    assert result["model_id"] == "test/model"
    assert "Experienced analyst" in result["content"]
    # Contract validation: adapter output must fit the result schema.
    validated = CVGenerationResult(
        template_id="professional",
        content=result["content"],
        model_id=result["model_id"],
        ai_generated=True,
        review_before_sending=True,
    )
    assert validated.ai_generated is True


def test_classify_error_maps_rate_limit() -> None:
    err = HuggingFaceInferenceAdapter._classify_error(RuntimeError("429 rate limit exceeded"))
    assert "RATE_LIMITED" in str(err)


def test_classify_failure_maps_typed_and_unknown_errors() -> None:
    # Already-typed messages pass through unchanged.
    assert classify_failure(RuntimeError(f"{QUOTA_EXCEEDED}: billing stopped")) == QUOTA_EXCEEDED
    # Raw provider errors are matched by keyword.
    assert classify_failure(RuntimeError("429 rate limit exceeded")) == RATE_LIMITED
    # Unknown errors fail closed as MODEL_UNAVAILABLE (never fail open).
    assert classify_failure(RuntimeError("something exploded")) == MODEL_UNAVAILABLE


def test_model_unavailable_opens_circuit_without_blind_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def failing_call(self: object, model: ModelMetadata, prompt: str, max_new_tokens: int) -> str:
        calls["count"] += 1
        raise RuntimeError(f"{MODEL_UNAVAILABLE}: endpoint down")

    monkeypatch.setattr(HuggingFaceInferenceAdapter, "_call_model", failing_call)
    adapter = HuggingFaceInferenceAdapter(
        router=HuggingFaceModelRouter(
            models=[
                ModelMetadata(
                    model_id="test/down",
                    task_capabilities=("cv_generation",),
                    license="apache-2.0",
                    context_window=8192,
                )
            ]
        )
    )

    with pytest.raises(RuntimeError, match=MODEL_UNAVAILABLE):
        adapter.generate_with_fallback(task="cv_generation", prompt="hello")

    # §14 action for MODEL_UNAVAILABLE: no retry, circuit open, model unhealthy.
    assert calls["count"] == 1
    assert adapter._circuit_breakers["test/down"].state == "OPEN"
    assert adapter._circuit_breakers["test/down"].last_failure_type == MODEL_UNAVAILABLE
    assert adapter.models[0].health_status == "unhealthy"


def test_rate_limited_failure_is_retried_with_bounded_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def limited_call(self: object, model: ModelMetadata, prompt: str, max_new_tokens: int) -> str:
        calls["count"] += 1
        raise RuntimeError(f"{RATE_LIMITED}: 429 Too Many Requests")

    monkeypatch.setattr(HuggingFaceInferenceAdapter, "_call_model", limited_call)
    adapter = HuggingFaceInferenceAdapter(
        router=HuggingFaceModelRouter(
            models=[
                ModelMetadata(
                    model_id="test/limited",
                    task_capabilities=("cv_generation",),
                    license="apache-2.0",
                    context_window=8192,
                )
            ]
        )
    )

    with pytest.raises(RuntimeError, match="All Hugging Face model candidates failed"):
        adapter.generate_with_fallback(
            task="cv_generation",
            prompt="hello",
            max_retries=2,
            base_backoff_seconds=0.0,
        )

    # §14 action for RATE_LIMITED: bounded retry on the same model, then give up.
    assert calls["count"] == 2


def test_extract_resume_text_from_real_pdf() -> None:
    pdf_path = Path(__file__).resolve().parents[1] / "fixtures" / "Guy K. CV.pdf"
    text = extract_resume_text_from_pdf(pdf_path)

    assert "Data Scientist" in text
    assert "Python" in text
    assert "Machine Learning" in text


class TestRealCvExtraction:
    """Extraction against the two real CVs in tests/fixtures/.

    These are the user's own documents (`Guy K. CV.pdf`, English;
    `Guy kaptue Lebenslauf.pdf`, German) and double as the manual
    "upload CV → ATS check / job search" fixtures: upload either file
    through the ATS-review or job-search CV button and the extracted
    text below is what should fill the form / re-rank results.
    Debug via the `cv_pdf_extractor` logger (path, pages, chars).
    """

    EN_CV = Path(__file__).resolve().parents[1] / "fixtures" / "Guy K. CV.pdf"
    DE_CV = Path(__file__).resolve().parents[1] / "fixtures" / "Guy kaptue Lebenslauf.pdf"

    def test_english_cv_extracts_expected_profile(self) -> None:
        text = extract_resume_text_from_pdf(self.EN_CV)
        assert len(text) > 3000
        for marker in ("Kaptue", "Data Scientist", "Python", "SQL", "Machine Learning"):
            assert marker in text

    def test_german_cv_extracts_expected_profile(self) -> None:
        text = extract_resume_text_from_pdf(self.DE_CV)
        assert len(text) > 3000
        for marker in ("Kaptue", "Data Scientist", "Python", "Zusammenfassung", "Projekte"):
            assert marker in text

    def test_both_cvs_share_owner_identity(self) -> None:
        english = extract_resume_text_from_pdf(self.EN_CV)
        german = extract_resume_text_from_pdf(self.DE_CV)
        assert "Kaptue" in english and "Kaptue" in german
        assert "Winsen" in english and "Winsen" in german

    def test_bytes_path_matches_file_path(self) -> None:
        """The upload endpoint reads bytes, not paths — both must agree."""
        for pdf_path in (self.EN_CV, self.DE_CV):
            from_path = extract_resume_text_from_pdf(pdf_path)
            result = extract_text_from_pdf_bytes(pdf_path.read_bytes(), source=pdf_path.name)
            assert result["text"] == from_path
            assert result["pages"] >= 1
            assert result["chars"] == len(from_path)

    def test_bytes_path_rejects_non_pdf(self) -> None:
        with pytest.raises(ValueError, match="Could not read PDF"):
            extract_text_from_pdf_bytes(b"this is not a pdf", source="fake.pdf")

    def test_missing_path_raises_filenotfound(self) -> None:
        with pytest.raises(FileNotFoundError):
            extract_resume_text_from_pdf(self.EN_CV.parent / "does-not-exist.pdf")


class TestResignationPrompt:
    def test_formal_tone_is_default(self) -> None:
        prompt = build_resignation_prompt("Jane", "Acme", "Analyst", "2026-12-31", "30 days")
        assert "formal resignation letter" in prompt
        assert "Jane" in prompt
        assert "Acme" in prompt
        assert "2026-12-31" in prompt
        assert "30 days" in prompt

    def test_tone_selector_changes_register(self) -> None:
        warm = build_resignation_prompt("Jane", "Acme", "Analyst", "2026-12-31", "30 days", tone="warm")
        brief = build_resignation_prompt("Jane", "Acme", "Analyst", "2026-12-31", "30 days", tone="brief")
        assert "warm, appreciative resignation letter" in warm
        assert "concise resignation letter" in brief

    def test_reason_included_only_when_provided(self) -> None:
        with_reason = build_resignation_prompt(
            "Jane",
            "Acme",
            "Analyst",
            "2026-12-31",
            "30 days",
            reason="relocation",
        )
        without_reason = build_resignation_prompt("Jane", "Acme", "Analyst", "2026-12-31", "30 days")
        assert "Reason for leaving: relocation" in with_reason
        assert "Reason for leaving" not in without_reason

    def test_never_invents_facts(self) -> None:
        prompt = build_resignation_prompt("Jane", "Acme", "Analyst", "2026-12-31", "30 days")
        assert "Do NOT invent" in prompt


class TestResumeAnalysisPrompt:
    def test_includes_structured_inputs(self) -> None:
        prompt = build_resume_analysis_prompt(
            "Jane",
            "Data Scientist",
            "Summary text",
            [{"role": "Analyst", "company": "Acme", "highlights": ["shipped model"]}],
            [{"degree": "MSc", "school": "University"}],
            ["Python"],
            job_description="Build models.",
            keyword_list=["Python", "SQL"],
        )
        assert "Data Scientist" in prompt
        assert "Summary text" in prompt
        assert "Analyst at Acme: shipped model" in prompt
        assert "MSc | University" in prompt
        assert "Python" in prompt
        assert "Build models." in prompt
        assert "Python, SQL" in prompt

    def test_empty_inputs_render_not_provided(self) -> None:
        prompt = build_resume_analysis_prompt("Jane", "Analyst", "", [], [], [])
        assert "Not provided" in prompt

    def test_experience_capped_at_six_highlights_at_three(self) -> None:
        experience = [
            {"role": f"Role {i}", "company": "Acme", "highlights": [f"h{j}" for j in range(5)]} for i in range(8)
        ]
        prompt = build_resume_analysis_prompt("Jane", "Analyst", "", experience, [], [])
        assert "Role 5" in prompt
        assert "Role 6" not in prompt
        # Only the first three highlights are rendered.
        assert "h0; h1; h2" in prompt
        assert "h3" not in prompt

    def test_education_capped_at_four(self) -> None:
        education = [{"degree": f"Degree {i}", "school": "University"} for i in range(6)]
        prompt = build_resume_analysis_prompt("Jane", "Analyst", "", [], education, [])
        assert "Degree 3" in prompt
        assert "Degree 4" not in prompt

    def test_requires_json_output_contract(self) -> None:
        prompt = build_resume_analysis_prompt("Jane", "Analyst", "", [], [], [])
        assert "Return a JSON object" in prompt
        assert "matched_keywords" in prompt
        assert "keyword_overlap" in prompt
        assert "Do NOT invent" in prompt

    def test_keyword_list_none_renders_not_provided(self) -> None:
        prompt = build_resume_analysis_prompt("Jane", "Analyst", "", [], [], [], keyword_list=None)
        assert "Keywords to check: Not provided" in prompt
