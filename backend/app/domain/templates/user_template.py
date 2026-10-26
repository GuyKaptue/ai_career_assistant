"""User-created or edited document templates (stored in ``user_templates``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

TEMPLATE_KINDS = ("cv", "cover_letter")
TEMPLATE_LANGUAGES = ("en", "de", "fr")
MAX_TEMPLATE_NAME = 80
MAX_TEMPLATE_CONTENT_CHARS = 20_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class UserTemplate:
    """A template owned by one user, optionally derived from a built-in one."""

    id: str
    user_id: str
    kind: str
    name: str
    base_template_id: str | None = None
    structure_type: str | None = None
    tone: str | None = None
    language: str | None = None
    content: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "kind": self.kind,
            "name": self.name,
            "base_template_id": self.base_template_id,
            "structure_type": self.structure_type,
            "tone": self.tone,
            "language": self.language,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
