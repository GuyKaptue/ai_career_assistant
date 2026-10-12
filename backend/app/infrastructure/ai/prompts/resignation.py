"""Versioned prompts for resignation letters (TODO BE-02).

Tone selector: formal (default), warm, or brief. Each tone keeps the
same facts but adjusts the register. Never invent resignation dates,
roles, or reasons.
"""

from __future__ import annotations

PROMPT_VERSION = "v1"


def build_resignation_prompt(
    name: str,
    company: str,
    role: str,
    last_working_day: str,
    notice_period: str,
    reason: str = "",
    language: str = "en",
    tone: str = "formal",
) -> str:
    """Build a resignation-letter generation prompt with tone selection."""
    tone = tone.lower()
    if tone == "warm":
        opening = (
            f"Write a warm, appreciative resignation letter from {name} to {company} "
            f"for the '{role}' role (language: {language})."
        )
    elif tone == "brief":
        opening = (
            f"Write a concise resignation letter from {name} to {company} "
            f"for the '{role}' role (language: {language})."
        )
    else:
        opening = (
            f"Write a formal resignation letter from {name} to {company} "
            f"for the '{role}' role (language: {language})."
        )

    reason_text = reason.strip()
    if reason_text:
        reason_block = f"Reason for leaving: {reason_text}.\n\n"
    else:
        reason_block = ""

    return (
        f"{opening}\n"
        f"Candidate: {name}\n"
        f"Company: {company}\n"
        f"Role: {role}\n"
        f"Last working day: {last_working_day}\n"
        f"Notice period: {notice_period}\n"
        f"{reason_block}"
        f"Required elements:\n"
        f"- State the resignation and last working day clearly and concisely.\n"
        f"- Express gratitude for the experience and support received.\n"
        f"- Note the notice period and willingness to support a smooth transition.\n"
        f"- Close with the appropriate tone ({tone}).\n"
        f"STRICT RULES: Use ONLY the facts above. Do NOT invent dates, roles, or reasons. "
        f"Output plain text."
    )
