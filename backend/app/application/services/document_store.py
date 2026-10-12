from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.core.persistence import InMemoryRepository, SupabaseRepository
from app.domain.documents.models import DocumentRecord

# Bounded history (§17: "versioning where justified") — keep the most recent
# snapshots so a document row never grows without limit.
MAX_DOCUMENT_VERSIONS = 20


class DocumentStore:
    def __init__(self) -> None:
        self._backend: SupabaseRepository | InMemoryRepository
        if settings.supabase_url and settings.supabase_service_role_key:
            self._backend = SupabaseRepository("documents", DocumentRecord, "id")
        else:
            self._backend = InMemoryRepository()
        self._documents: dict[str, DocumentRecord] = {}

    def create(self, payload: dict) -> DocumentRecord:
        user_id = payload.get("user_id")
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required for document creation.")

        document_id = payload.get("id") or str(uuid.uuid4())
        record = DocumentRecord(
            id=document_id,
            user_id=user_id,
            title=payload.get("title", "Untitled Document"),
            document_type=payload.get("document_type", "cv"),
            template_id=payload.get("template_id", "professional"),
            content=payload.get("content", ""),
        )
        if settings.supabase_url and settings.supabase_service_role_key:
            stored = self._backend.create(record.to_dict())
            self._documents[stored.id] = stored
            return stored

        self._documents[record.id] = record
        return record

    def get(self, document_id: str) -> DocumentRecord | None:
        if settings.supabase_url and settings.supabase_service_role_key:
            record = self._backend.get(document_id)
            if record is not None:
                self._documents[document_id] = record
            return record
        return self._documents.get(document_id)

    def list_for_user(self, user_id: str) -> list[DocumentRecord]:
        if settings.supabase_url and settings.supabase_service_role_key:
            rows = self._backend.list_for_user(user_id)
            for row in rows:
                self._documents[row.id] = row
            return rows
        return [record for record in self._documents.values() if record.user_id == user_id]

    def update(self, document_id: str, payload: dict) -> DocumentRecord:
        record = self._documents.get(document_id)
        if record is None:
            record = self.get(document_id)
        if record is None:
            raise KeyError(document_id)

        payload = dict(payload)
        # Version fields are owned by the store; clients cannot set them.
        payload.pop("version", None)
        payload.pop("version_history", None)

        # BE-05: a content change snapshots the current state and bumps the
        # version; metadata-only edits (title/template) keep the version.
        if "content" in payload and payload["content"] != record.content:
            history = [*record.version_history, record.snapshot()][-MAX_DOCUMENT_VERSIONS:]
            payload["version"] = record.version + 1
            payload["version_history"] = history

        if settings.supabase_url and settings.supabase_service_role_key:
            updated = self._backend.update(document_id, payload)
            self._documents[document_id] = updated
            return updated

        for key, value in payload.items():
            if hasattr(record, key):
                setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc).isoformat()
        return record

    def list_versions(self, document_id: str) -> list[dict]:
        """Return all retained versions (oldest first), current version last."""
        record = self.get(document_id)
        if record is None:
            raise KeyError(document_id)
        versions = [*record.version_history, record.snapshot()]
        versions.sort(key=lambda item: int(item.get("version", 0)))
        return versions

    def get_version(self, document_id: str, version: int) -> dict:
        """Return one snapshot: the live state for the current version, or a
        retained history entry for older ones."""
        record = self.get(document_id)
        if record is None:
            raise KeyError(document_id)
        if version == record.version:
            return record.snapshot()
        for snapshot in record.version_history:
            if int(snapshot.get("version", -1)) == version:
                return snapshot
        raise KeyError(f"{document_id}:{version}")

    def restore_version(self, document_id: str, version: int) -> DocumentRecord:
        """Restore an older version's state as a NEW version (history kept)."""
        snapshot = self.get_version(document_id, version)
        return self.update(
            document_id,
            {
                "title": snapshot["title"],
                "document_type": snapshot["document_type"],
                "template_id": snapshot["template_id"],
                "content": snapshot["content"],
            },
        )

    def delete(self, document_id: str) -> bool:
        """Delete a document and its retained version history.

        Ownership is enforced by the route layer (DELETE only on
        documents the caller owns); RLS also blocks foreign deletes.
        """
        record = self._documents.get(document_id)
        if record is None:
            record = self.get(document_id)
        if record is None:
            return False

        if settings.supabase_url and settings.supabase_service_role_key:
            deleted = self._backend.delete(document_id)
            if deleted:
                self._documents.pop(document_id, None)
            return deleted

        if document_id in self._documents:
            del self._documents[document_id]
            return True
        return False


document_store = DocumentStore()
