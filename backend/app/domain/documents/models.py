from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DocumentRecord:
    id: str
    user_id: str
    title: str
    document_type: str
    template_id: str
    content: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # BE-05 document versioning (MASTER §17/§23): version starts at 1 and
    # increments on every content change; previous snapshots are retained.
    version: int = 1
    version_history: list[dict] = field(default_factory=list)

    def snapshot(self) -> dict:
        """Immutable snapshot of this document at its current version."""
        return {
            "version": self.version,
            "title": self.title,
            "document_type": self.document_type,
            "template_id": self.template_id,
            "content": self.content,
            "saved_at": self.updated_at,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "document_type": self.document_type,
            "template_id": self.template_id,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "version_history": list(self.version_history),
        }
