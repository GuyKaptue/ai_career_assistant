"""Persistence and validation for application projects."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.config import settings
from app.core.persistence import SupabaseRepository
from app.domain.projects.models import (
    DEFAULT_COVER_LETTER_TEMPLATE,
    DEFAULT_CV_TEMPLATE,
    MAX_PROJECT_NAME_LENGTH,
    VALID_PROJECT_STATUSES,
    Project,
)
from app.domain.templates.template_registry import TemplateRegistry

# Fields the *user* may change through the API. Link fields (documents,
# application, position, match) are set only by the services that own them.
USER_EDITABLE_FIELDS = ("name", "status", "template_id", "cover_letter_template_id")
_LINK_FIELDS = ("position", "match", "cv_document_id", "cover_letter_document_id", "application_id")


def _use_supabase() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def clean_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("name is required.")
    name = " ".join(value.split())
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError(f"name must be at most {MAX_PROJECT_NAME_LENGTH} characters.")
    return name


class ProjectStore:
    def __init__(self) -> None:
        self._backend: SupabaseRepository | None = (
            SupabaseRepository("projects", Project, "id") if _use_supabase() else None
        )
        self._projects: dict[str, Project] = {}
        self._registry = TemplateRegistry()
        #: ``(user_id, kind, template_id) -> bool``; lets a project use the user's own templates.
        self.user_template_exists: Callable[[str, str, str], bool] | None = None

    # -- validation -----------------------------------------------------
    def _template_ok(self, user_id: str, kind: str, template_id: str) -> bool:
        if self._registry.supports(template_id, kind):
            return True
        check = self.user_template_exists
        return bool(check and check(user_id, kind, template_id))

    def _validate_templates(self, user_id: str, cv_template: str | None, letter_template: str | None) -> None:
        if cv_template is not None and not self._template_ok(user_id, "cv", cv_template):
            raise ValueError(f"Unknown CV template '{cv_template}'.")
        if letter_template is not None and not self._template_ok(user_id, "cover_letter", letter_template):
            raise ValueError(f"Unknown cover-letter template '{letter_template}'.")

    # -- CRUD -----------------------------------------------------------
    def create(
        self,
        user_id: str,
        name: str,
        *,
        template_id: str | None = None,
        cover_letter_template_id: str | None = None,
        position: dict[str, Any] | None = None,
        status: str = "draft",
    ) -> Project:
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required for project creation.")
        if status not in VALID_PROJECT_STATUSES:
            raise ValueError(f"Unsupported status '{status}'.")
        self._validate_templates(user_id, template_id, cover_letter_template_id)
        project = Project(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=clean_name(name),
            status=status,
            template_id=template_id or DEFAULT_CV_TEMPLATE,
            cover_letter_template_id=cover_letter_template_id or DEFAULT_COVER_LETTER_TEMPLATE,
            position=position,
        )
        backend = self._backend
        if backend is not None:
            stored = backend.create(project.to_dict())
            self._projects[stored.id] = stored
            return stored  # type: ignore[no-any-return]
        self._projects[project.id] = project
        return project

    def get(self, project_id: str) -> Project | None:
        backend = self._backend
        if backend is not None:
            found = backend.get(project_id)
            if found is not None:
                self._projects[project_id] = found
            return found  # type: ignore[no-any-return]
        return self._projects.get(project_id)

    def list_for_user(self, user_id: str) -> list[Project]:
        backend = self._backend
        if backend is not None:
            rows = backend.list_for_user(user_id)
            for row in rows:
                self._projects[row.id] = row
        else:
            rows = [project for project in self._projects.values() if project.user_id == user_id]
        return sorted(rows, key=lambda project: project.updated_at, reverse=True)

    def update(self, project_id: str, changes: dict[str, Any], *, internal: bool = False) -> Project:
        """Apply ``changes``. ``internal`` unlocks link fields for services."""
        allowed = USER_EDITABLE_FIELDS + (_LINK_FIELDS if internal else ())
        clean = {key: value for key, value in changes.items() if key in allowed}
        if not clean:
            raise ValueError("No editable fields were provided.")
        if "name" in clean:
            clean["name"] = clean_name(clean["name"])
        if "status" in clean and clean["status"] not in VALID_PROJECT_STATUSES:
            raise ValueError(f"Unsupported status '{clean['status']}'.")
        if "template_id" in clean or "cover_letter_template_id" in clean:
            existing = self.get(project_id)
            if existing is None:
                raise KeyError(project_id)
            self._validate_templates(existing.user_id, clean.get("template_id"), clean.get("cover_letter_template_id"))
        clean["updated_at"] = datetime.now(timezone.utc).isoformat()

        backend = self._backend
        if backend is not None:
            updated = backend.update(project_id, clean)
            self._projects[project_id] = updated
            return updated  # type: ignore[no-any-return]
        project = self._projects[project_id]
        for key, value in clean.items():
            setattr(project, key, value)
        return project

    def delete(self, project_id: str) -> bool:
        backend = self._backend
        if backend is not None:
            deleted = bool(backend.delete(project_id))
            if deleted:
                self._projects.pop(project_id, None)
            return deleted
        return self._projects.pop(project_id, None) is not None


project_store = ProjectStore()
