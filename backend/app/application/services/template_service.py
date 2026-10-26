"""Template persistence, defaults and per-job overrides (RD-08 §6).

Rules enforced here (and tested):

* A user can create/edit their own templates (``user_templates``), derived from a
  built-in one. Saving indexes the template text into RAG (entity type
  ``template``, user-scoped) so later generations can retrieve it. Indexing is
  fail-soft: the template is saved even when the embedding service is down.
* A user has a default CV template and a default cover-letter template
  (``profile_preferences``). Defaults seed NEW projects only.
* A per-job override is a project's own ``template_id`` / ``cover_letter_template_id``.
  Setting an override writes only the project; changing a default never touches
  existing projects. Resolution order: project override > user default > built-in default.
* A user can only select built-in templates or templates they own.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Protocol

from app.application.services.tailoring_pipeline import DEFAULT_LETTER_STYLE, LETTER_STYLE
from app.core.config import settings
from app.core.errors import AppError
from app.core.persistence import InMemoryRepository, SupabaseRepository
from app.domain.projects.models import DEFAULT_COVER_LETTER_TEMPLATE, DEFAULT_CV_TEMPLATE
from app.domain.templates.template_registry import TemplateRegistry
from app.domain.templates.user_template import (
    MAX_TEMPLATE_CONTENT_CHARS,
    MAX_TEMPLATE_NAME,
    TEMPLATE_KINDS,
    TEMPLATE_LANGUAGES,
    UserTemplate,
)

logger = logging.getLogger(__name__)

BUILTIN_DEFAULTS: Final = {"cv": DEFAULT_CV_TEMPLATE, "cover_letter": DEFAULT_COVER_LETTER_TEMPLATE}
_DEFAULT_FIELD: Final = {"cv": "default_cv_template_id", "cover_letter": "default_cover_letter_template_id"}
_PROJECT_FIELD: Final = {"cv": "template_id", "cover_letter": "cover_letter_template_id"}


class _Indexer(Protocol):
    def index_document(self, user_id: str, document_type: str, document_id: str, content: str) -> dict: ...

    def remove_document(self, user_id: str, document_type: str, document_id: str) -> int: ...


class _Projects(Protocol):
    user_template_exists: Any

    def get(self, project_id: str) -> Any: ...

    def update(self, project_id: str, changes: dict[str, Any], *, internal: bool = False) -> Any: ...


class UserTemplateNotFound(KeyError):
    """The template does not exist or belongs to another user (indistinguishable on purpose)."""


@dataclass(frozen=True)
class TemplateContext:
    """What prompts need to know about a selected template."""

    template_id: str
    kind: str
    name: str
    source: str  # "builtin" | "user"
    structure_type: str
    tone: str
    language: str
    paragraphs: int


class UserTemplateStore:
    """Supabase ``user_templates`` when configured, memory otherwise."""

    def __init__(self) -> None:
        self._backend: SupabaseRepository | InMemoryRepository = (
            SupabaseRepository("user_templates", UserTemplate, "id")
            if settings.supabase_url and settings.supabase_service_role_key
            else InMemoryRepository()
        )

    def create(self, template: UserTemplate) -> UserTemplate:
        if isinstance(self._backend, SupabaseRepository):
            return self._backend.create(template.to_dict())  # type: ignore[no-any-return]
        return self._backend.create(template)  # type: ignore[no-any-return]

    def get(self, template_id: str) -> UserTemplate | None:
        return self._backend.get(template_id)  # type: ignore[no-any-return]

    def list_for_user(self, user_id: str) -> list[UserTemplate]:
        return list(self._backend.list_for_user(user_id))

    def update(self, template_id: str, changes: dict[str, Any]) -> UserTemplate:
        return self._backend.update(template_id, changes)  # type: ignore[no-any-return]

    def delete(self, template_id: str) -> bool:
        return bool(self._backend.delete(template_id))


@dataclass
class _Prefs:
    user_id: str
    default_cv_template_id: str | None = None
    default_cover_letter_template_id: str | None = None


class DefaultsStore:
    """Per-user default template ids. Supabase ``profile_preferences`` when configured, memory otherwise.

    Only the two default fields (plus ``user_id``) are written here, so this store can
    never overwrite the other preference columns.
    """

    def __init__(self) -> None:
        self._backend: SupabaseRepository | InMemoryRepository = (
            SupabaseRepository("profile_preferences", _Prefs, "user_id")
            if settings.supabase_url and settings.supabase_service_role_key
            else InMemoryRepository()
        )
        self._local: dict[str, _Prefs] = {}

    def get(self, user_id: str) -> _Prefs:
        if isinstance(self._backend, InMemoryRepository):
            return self._local.get(user_id) or _Prefs(user_id)
        return self._backend.get(user_id) or _Prefs(user_id)

    def set_default(self, user_id: str, kind: str, template_id: str | None) -> None:
        field_name = _DEFAULT_FIELD[kind]
        stamp = datetime.now(timezone.utc).isoformat()
        if isinstance(self._backend, InMemoryRepository):
            prefs = self._local.setdefault(user_id, _Prefs(user_id))
            setattr(prefs, field_name, template_id)
            return
        if self._backend.get(user_id) is None:
            self._backend.create({"user_id": user_id, field_name: template_id})
        else:
            self._backend.update(user_id, {field_name: template_id, "updated_at": stamp})


def _template_text(template: UserTemplate) -> str:
    parts = [template.name, template.structure_type or "", template.tone or ""]
    content = template.content
    for key in sorted(content):
        value = content[key]
        parts.append(
            f"{key}: {value}" if not isinstance(value, (list, tuple)) else f"{key}: " + ", ".join(map(str, value))
        )
    return "\n".join(p for p in parts if p)


class TemplateService:
    """Orchestrates built-in registry, user templates, defaults, overrides and RAG indexing."""

    def __init__(
        self,
        *,
        registry: TemplateRegistry,
        templates: UserTemplateStore,
        defaults: DefaultsStore,
        projects: _Projects,
        indexer: _Indexer,
    ) -> None:
        self._registry = registry
        self._templates = templates
        self._defaults = defaults
        self._projects = projects
        self._indexer = indexer
        projects.user_template_exists = self.user_owns_template

    # -- ownership / validation ----------------------------------------------
    def user_owns_template(self, user_id: str, kind: str, template_id: str) -> bool:
        found = self._templates.get(template_id)
        return found is not None and found.user_id == user_id and found.kind == kind

    def is_selectable(self, user_id: str, kind: str, template_id: str) -> bool:
        return self._registry.supports(template_id, kind) or self.user_owns_template(user_id, kind, template_id)

    @staticmethod
    def _validate_fields(kind: str, name: str, language: str | None, content: dict[str, Any]) -> str:
        if kind not in TEMPLATE_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(TEMPLATE_KINDS)}")
        clean = " ".join(str(name).split())
        if not clean or len(clean) > MAX_TEMPLATE_NAME:
            raise ValueError(f"name is required and at most {MAX_TEMPLATE_NAME} characters.")
        if language is not None and language not in TEMPLATE_LANGUAGES:
            raise ValueError(f"language must be one of: {', '.join(TEMPLATE_LANGUAGES)}")
        if len(str(content)) > MAX_TEMPLATE_CONTENT_CHARS:
            raise ValueError("template content is too large.")
        return clean

    # -- user templates ---------------------------------------------------------
    def create_template(
        self,
        user_id: str,
        kind: str,
        name: str,
        *,
        base_template_id: str | None = None,
        structure_type: str | None = None,
        tone: str | None = None,
        language: str | None = None,
        content: dict[str, Any] | None = None,
    ) -> tuple[UserTemplate, bool]:
        """Create and index a template. Returns ``(template, indexed)``."""
        if not user_id.strip():
            raise ValueError("user_id is required.")
        clean = self._validate_fields(kind, name, language, content or {})
        if base_template_id is not None and not self._registry.supports(base_template_id, kind):
            raise ValueError(f"Unknown base template '{base_template_id}'.")
        template = UserTemplate(
            id=str(uuid.uuid4()),
            user_id=user_id,
            kind=kind,
            name=clean,
            base_template_id=base_template_id,
            structure_type=structure_type,
            tone=tone,
            language=language,
            content=dict(content or {}),
        )
        stored = self._templates.create(template)
        return stored, self._index(stored)

    def update_template(self, user_id: str, template_id: str, changes: dict[str, Any]) -> tuple[UserTemplate, bool]:
        """Edit an owned template and re-index it (old chunks are replaced)."""
        current = self._owned(user_id, template_id)
        allowed = {"name", "structure_type", "tone", "language", "content"}
        clean = {k: v for k, v in changes.items() if k in allowed}
        if not clean:
            raise ValueError("No editable fields were provided.")
        self._validate_fields(
            current.kind,
            clean.get("name", current.name),
            clean.get("language", current.language),
            clean.get("content", current.content),
        )
        if "name" in clean:
            clean["name"] = " ".join(str(clean["name"]).split())
        clean["updated_at"] = datetime.now(timezone.utc).isoformat()
        stored = self._templates.update(template_id, clean)
        return stored, self._index(stored)

    def delete_template(self, user_id: str, template_id: str) -> None:
        """Delete an owned template, its index entries, and any default pointing at it."""
        template = self._owned(user_id, template_id)
        self._templates.delete(template_id)
        self._safe_remove(user_id, template_id)
        if self._defaults.get(user_id).__dict__.get(_DEFAULT_FIELD[template.kind]) == template_id:
            self._defaults.set_default(user_id, template.kind, None)
        for project in self._user_projects(user_id):
            if getattr(project, _PROJECT_FIELD[template.kind]) == template_id:
                self._projects.update(project.id, {_PROJECT_FIELD[template.kind]: BUILTIN_DEFAULTS[template.kind]})

    def list_templates(self, user_id: str, kind: str | None = None) -> list[UserTemplate]:
        items = self._templates.list_for_user(user_id)
        return [t for t in items if kind is None or t.kind == kind]

    def _owned(self, user_id: str, template_id: str) -> UserTemplate:
        found = self._templates.get(template_id)
        if found is None or found.user_id != user_id:
            raise UserTemplateNotFound(template_id)
        return found

    def _user_projects(self, user_id: str) -> list[Any]:
        lister = getattr(self._projects, "list_for_user", None)
        return list(lister(user_id)) if lister else []

    def _index(self, template: UserTemplate) -> bool:
        try:
            self._indexer.index_document(template.user_id, "template", template.id, _template_text(template))
        except (AppError, RuntimeError, ValueError, OSError):
            logger.warning("templates.index_failed kind=%s", template.kind)
            return False
        return True

    def _safe_remove(self, user_id: str, template_id: str) -> None:
        try:
            self._indexer.remove_document(user_id, "template", template_id)
        except (AppError, RuntimeError, ValueError, OSError):
            logger.warning("templates.unindex_failed")

    # -- defaults and overrides ---------------------------------------------------
    def set_default(self, user_id: str, kind: str, template_id: str | None) -> None:
        """Set (or clear with ``None``) the user's default. Never modifies existing projects."""
        if kind not in TEMPLATE_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(TEMPLATE_KINDS)}")
        if template_id is not None and not self.is_selectable(user_id, kind, template_id):
            raise ValueError(f"Unknown template '{template_id}'.")
        self._defaults.set_default(user_id, kind, template_id)

    def default_for(self, user_id: str, kind: str) -> str:
        chosen = getattr(self._defaults.get(user_id), _DEFAULT_FIELD[kind])
        if chosen and self.is_selectable(user_id, kind, chosen):
            return str(chosen)
        return BUILTIN_DEFAULTS[kind]

    def seed_for_new_project(self, user_id: str) -> tuple[str, str]:
        """``(cv_template_id, cover_letter_template_id)`` to pass to ``ProjectStore.create``."""
        return self.default_for(user_id, "cv"), self.default_for(user_id, "cover_letter")

    def set_project_override(self, user_id: str, project_id: str, kind: str, template_id: str) -> Any:
        """Override the template for ONE project. Writes only the project, never the defaults."""
        project = self._projects.get(project_id)
        if project is None or project.user_id != user_id:
            raise KeyError(project_id)
        if kind not in TEMPLATE_KINDS or not self.is_selectable(user_id, kind, template_id):
            raise ValueError(f"Unknown template '{template_id}'.")
        return self._projects.update(project_id, {_PROJECT_FIELD[kind]: template_id})

    def resolve(self, user_id: str, kind: str, project_id: str | None = None) -> tuple[str, str]:
        """``(template_id, source)``; source is ``project``, ``default`` or ``builtin``."""
        if project_id:
            project = self._projects.get(project_id)
            if project is not None and project.user_id == user_id:
                chosen = getattr(project, _PROJECT_FIELD[kind])
                if chosen and self.is_selectable(user_id, kind, chosen):
                    return str(chosen), "project"
        chosen = getattr(self._defaults.get(user_id), _DEFAULT_FIELD[kind])
        if chosen and self.is_selectable(user_id, kind, chosen):
            return str(chosen), "default"
        return BUILTIN_DEFAULTS[kind], "builtin"

    # -- context for prompts ------------------------------------------------------------
    def context_for(self, user_id: str, kind: str, template_id: str) -> TemplateContext:
        """Structure/tone/language of the selected template (built-in or the user's own)."""
        own = self._templates.get(template_id)
        if own is not None and own.user_id == user_id and own.kind == kind:
            paragraphs, tone = (
                LETTER_STYLE.get(own.structure_type or "", DEFAULT_LETTER_STYLE) if kind == "cover_letter" else (0, "")
            )
            return TemplateContext(
                own.id,
                kind,
                own.name,
                "user",
                own.structure_type or "",
                own.tone or tone,
                own.language or "en",
                paragraphs,
            )
        builtin = self._registry.get(template_id, kind)
        if builtin is None:
            raise UserTemplateNotFound(template_id)
        layout = str(builtin.metadata.get("layout", ""))
        paragraphs, tone = LETTER_STYLE.get(layout, DEFAULT_LETTER_STYLE) if kind == "cover_letter" else (0, "")
        return TemplateContext(
            builtin.id, kind, builtin.name, "builtin", layout, tone, builtin.supported_locales[0], paragraphs
        )

    def cover_letter_style(self, user_id: str, template_id: str) -> tuple[int, str]:
        """``(paragraph count, tone)`` for ``write_cover_letter(style=...)``."""
        ctx = self.context_for(user_id, "cover_letter", template_id)
        return ctx.paragraphs or DEFAULT_LETTER_STYLE[0], ctx.tone or DEFAULT_LETTER_STYLE[1]


_template_service: TemplateService | None = None


def get_template_service() -> TemplateService:
    """Lazy process-wide service wired to the shared project store and retrieval service."""
    global _template_service
    if _template_service is None:
        from app.application.services.document_retrieval import get_document_retrieval
        from app.application.services.project_store import project_store

        _template_service = TemplateService(
            registry=TemplateRegistry(),
            templates=UserTemplateStore(),
            defaults=DefaultsStore(),
            projects=project_store,
            indexer=get_document_retrieval(),
        )
    return _template_service
