"""Versioned prompts for CV generation (TODO BE-02).

Rules: never invent employment, education, metrics, certifications, or
skills. If a metric is not provided, omit it — do not fabricate one.
"""

from __future__ import annotations

PROMPT_VERSION = "v1"


def build_cv_prompt(
    name: str,
    target_role: str,
    summary: str,
    experience: list[dict],
    education: list[dict],
    skills: list[str],
    language: str = "en",
) -> str:
    exp_lines = []
    for job in experience[:6]:
        role = job.get("role", "Role")
        company = job.get("company", "Company")
        highlights = "; ".join(str(h) for h in job.get("highlights", [])[:3])
        exp_lines.append(f"- {role} at {company}" + (f": {highlights}" if highlights else ""))
    edu_lines = [f"- {e.get('degree', 'Degree')} | {e.get('school', 'School')}" for e in education[:4]]
    return (
        f"Write a tailored professional CV summary and experience section for {name} "
        f"applying to '{target_role}' (language: {language}).\n"
        f"Candidate summary: {summary or 'Not provided.'}\n"
        "Experience:\n" + ("\n".join(exp_lines) if exp_lines else "Not provided.") + "\n"
        "Education:\n" + ("\n".join(edu_lines) if edu_lines else "Not provided.") + "\n"
        f"Skills: {', '.join(skills) if skills else 'Not provided.'}\n"
        "STRICT RULES: Use ONLY the facts above. Do NOT invent job titles, companies, "
        "dates, metrics, certifications, or skills. If information is missing, write "
        "'Not provided' instead of guessing. Output plain text with sections: "
        "Summary, Experience, Education, Skills."
    )


def build_cover_letter_prompt(name: str, company: str, target_role: str, summary: str, language: str = "en") -> str:
    return (
        f"Write a concise professional cover letter from {name} to {company} "
        f"for the '{target_role}' role (language: {language}).\n"
        f"Candidate background: {summary or 'Not provided.'}\n"
        "STRICT RULES: Use ONLY the facts above. Do NOT invent achievements, "
        "metrics, or employment history. Keep it under 250 words. Plain text."
    )
