"""Project domain model.

A project groups everything for ONE application: the target position, the
chosen CV / cover-letter templates, the CV match result, the generated
documents and — once applied — the tracker entry. Template choices live here,
independent of document content (switching templates never edits content).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

VALID_PROJECT_STATUSES = ("draft", "researching", "applied", "archived")
DEFAULT_CV_TEMPLATE = "professional"
DEFAULT_COVER_LETTER_TEMPLATE = "classic-letter"
MAX_PROJECT_NAME_LENGTH = 120


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Project:
    id: str
    user_id: str
    name: str
    status: str = "draft"
    template_id: str = DEFAULT_CV_TEMPLATE
    cover_letter_template_id: str = DEFAULT_COVER_LETTER_TEMPLATE
    position: dict[str, Any] | None = None
    match: dict[str, Any] | None = None
    cv_document_id: str | None = None
    cover_letter_document_id: str | None = None
    application_id: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "status": self.status,
            "template_id": self.template_id,
            "cover_letter_template_id": self.cover_letter_template_id,
            "position": self.position,
            "match": self.match,
            "cv_document_id": self.cv_document_id,
            "cover_letter_document_id": self.cover_letter_document_id,
            "application_id": self.application_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
