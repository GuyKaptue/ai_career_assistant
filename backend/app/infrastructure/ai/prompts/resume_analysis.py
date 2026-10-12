"""Versioned prompts for resume analysis (TODO BE-02).

Rules: never overstate. Derive skill/keyword evidence strictly from the
resume text; if the model cannot match a keyword, mark it absent rather
than inventing it.
"""

from __future__ import annotations

PROMPT_VERSION = "v1"


def build_resume_analysis_prompt(
    name: str,
    target_role: str,
    summary: str,
    experience: list[dict],
    education: list[dict],
    skills: list[str],
    job_description: str = "",
    keyword_list: list[str] | None = None,
    language: str = "en",
) -> str:
    """Build a resume-analysis prompt from structured inputs."""
    if keyword_list is None:
        keyword_list = []
    if experience:
        exp_lines = []
        for job in experience[:6]:
            role = job.get("role", "Role")
            company = job.get("company", "Company")
            highlights = "; ".join(str(h) for h in job.get("highlights", [])[:3])
            exp_lines.append(f"- {role} at {company}" + (f": {highlights}" if highlights else ""))
        exp_text = "\n".join(exp_lines)
    else:
        exp_text = "Not provided."
    if education:
        edu_lines = [f"- {e.get('degree', 'Degree')} | {e.get('school', 'School')}" for e in education[:4]]
        edu_text = "\n".join(edu_lines)
    else:
        edu_text = "Not provided."

    job_desc = job_description.strip()
    if job_desc:
        job_desc = f"Job description:\n{job_desc}\n\n"
    else:
        job_desc = ""

    kw_list = ", ".join(keyword_list) if keyword_list else "Not provided."
    return (
        f"Analyze the following resume against the target role (language: {language}).\n"
        f"Target role: {target_role}\n"
        f"{job_desc}"
        f"Resume summary: {summary or 'Not provided.'}\n"
        f"Experience:\n{exp_text}\n"
        f"Education:\n{edu_text}\n"
        f"Skills: {skills if skills else 'Not provided.'}\n"
        f"Keywords to check: {kw_list}\n\n"
        f"Return a JSON object (no markdown fences) with exactly these keys:\n"
        f"  score: integer 0-100\n"
        f"  matched_keywords: list of strings (only keywords present in the resume text)\n"
        f"  strengths: list of strings (evidence-based, concise)\n"
        f"  suggestions: list of strings (actionable, based only on the resume and role)\n"
        f"  keyword_overlap: float 0.0-1.0 = matched_keywords count / keyword_list count\n\n"
        f"STRICT RULES: Use ONLY the facts above. Do NOT invent skills, metrics, or "
        f"achievements. If a keyword is not present, omit it from matched_keywords. "
        f"Do not fabricate experience or education dates. Output JSON only."
    )
