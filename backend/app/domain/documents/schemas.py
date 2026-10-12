"""Typed contracts for AI-assisted document generation (TODO AI-09 / BE-01).

Every model fallback must produce the SAME schema. The application layer
validates model output against these models and rejects invalid output
instead of silently converting it into fake-valid content.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CVGenerationRequest(BaseModel):
    name: str = "Candidate"
    target_role: str = "Target Role"
    summary: str = ""
    experience: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    template_id: str = "professional"
    use_ai: bool = False
    language: Literal["en", "de", "fr"] = "en"


class CVGenerationResult(BaseModel):
    template_id: str
    document_type: Literal["cv"] = "cv"
    content: str
    model_id: str | None = None
    ai_generated: bool = False
    review_before_sending: bool = False
    fallback_reason: str | None = None
    metadata: dict = Field(default_factory=dict)


class CoverLetterGenerationRequest(BaseModel):
    name: str = "Candidate"
    company: str = "Target Company"
    target_role: str = "role"
    summary: str = ""
    template_id: str = "classic-letter"
    use_ai: bool = False
    language: Literal["en", "de", "fr"] = "en"
    # Optional structured formal-letter blocks (T-01). When absent, the
    # renderer derives sender/subject/body from name/company/role/summary.
    sender_street: str = ""
    sender_city: str = ""
    sender_phone: str = ""
    sender_email: str = ""
    recipient_lines: list[str] = Field(default_factory=list)
    subject: str = ""
    reference_no: str = ""
    salutation: str = ""
    body_paragraphs: list[str] = Field(default_factory=list)
    closing: str = ""
    signature: str = ""
    letter_date: str = ""


class CoverLetterGenerationResult(BaseModel):
    template_id: str
    document_type: Literal["cover_letter"] = "cover_letter"
    content: str
    model_id: str | None = None
    ai_generated: bool = False
    review_before_sending: bool = False
    fallback_reason: str | None = None
    metadata: dict = Field(default_factory=dict)


class ResumeAnalysisResult(BaseModel):
    score: int = Field(ge=0, le=100)
    matched_keywords: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    keyword_overlap: float = Field(ge=0.0, le=1.0)
    model_id: str | None = None
    ai_generated: bool = False


class JobMatchResult(BaseModel):
    job_id: str
    score: int = Field(ge=0, le=100)
    rationale: str = ""
    model_id: str | None = None


class ResumeAnalysisRequest(BaseModel):
    """Input for resume-analysis (TODO BE-01 / AI-09).

    Every model fallback must produce the SAME schema. The analyzer
    derives a default keyword list from target_role + skills when
    the caller omits job_description / keyword_list.
    """

    name: str = "Candidate"
    target_role: str = "target role"
    summary: str = ""
    experience: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    template_id: str = "professional"
    use_ai: bool = False
    language: Literal["en", "de", "fr"] = "en"
    # Optional structured analysis overrides.
    job_description: str = ""
    keyword_list: list[str] = Field(default_factory=list)
