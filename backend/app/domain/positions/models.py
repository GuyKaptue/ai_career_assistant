"""Position: the job posting a project is about.

A position is *extracted* from user-supplied material (URL, pasted text, PDF,
DOCX, image, ZIP) or taken from a job-search result. Fields that cannot be
determined stay ``None`` and are listed in ``warnings`` — nothing is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Position:
    title: str | None
    company: str | None
    location: str | None
    description: str
    url: str | None = None
    source: str = "text"  # text | url | pdf | docx | image | zip:<member> | job_search
    published_at: str | None = None
    employment_type: str | None = None
    keywords: tuple[str, ...] = ()
    extracted_with: str = "heuristic"  # json_ld | heuristic | structured
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "description": self.description,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at,
            "employment_type": self.employment_type,
            "keywords": list(self.keywords),
            "extracted_with": self.extracted_with,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        """Rebuild a position from user-edited / stored data (unknown keys ignored)."""
        return cls(
            title=_clean(data.get("title")),
            company=_clean(data.get("company")),
            location=_clean(data.get("location")),
            description=str(data.get("description") or "").strip(),
            url=_clean(data.get("url")),
            source=str(data.get("source") or "text"),
            published_at=_clean(data.get("published_at")),
            employment_type=_clean(data.get("employment_type")),
            keywords=tuple(str(item) for item in (data.get("keywords") or ())),
            extracted_with=str(data.get("extracted_with") or "structured"),
            warnings=tuple(str(item) for item in (data.get("warnings") or ())),
        )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
