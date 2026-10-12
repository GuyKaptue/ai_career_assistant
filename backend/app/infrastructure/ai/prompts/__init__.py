"""Public prompt builders (TODO BE-02).

Rules: never invent employment, education, metrics, certifications, or
skills. If a metric is not provided, omit it — do not fabricate one.
"""

from __future__ import annotations

from .cv import build_cover_letter_prompt, build_cv_prompt
from .resignation import build_resignation_prompt
from .resume_analysis import build_resume_analysis_prompt

__all__ = [
    "build_cv_prompt",
    "build_cover_letter_prompt",
    "build_resume_analysis_prompt",
    "build_resignation_prompt",
]
