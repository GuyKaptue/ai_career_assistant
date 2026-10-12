from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone

from app.core.config import settings
from app.core.persistence import InMemoryRepository, SupabaseRepository
from app.domain.applications.models import UPDATABLE_FIELDS, VALID_STATUSES, JobApplication
from app.domain.jobs.keys import job_key as compute_job_key
from app.domain.jobs.keys import loose_key, normalize_url
from app.domain.jobs.models import Job


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_follow_up(value: object) -> str | None:
    """Accept ``None`` (clear) or an ISO 8601 date / datetime string."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("follow_up_date must be an ISO 8601 date (YYYY-MM-DD) or null.")
    text = value.strip()
    try:
        date.fromisoformat(text[:10])
        if len(text) > 10:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("follow_up_date must be an ISO 8601 date (YYYY-MM-DD) or null.") from exc
    return text


class ApplicationTracker:
    def __init__(self) -> None:
        self._backend: SupabaseRepository | InMemoryRepository
        if settings.supabase_url and settings.supabase_service_role_key:
            self._backend = SupabaseRepository("job_applications", JobApplication, "application_id")
        else:
            self._backend = InMemoryRepository()
        self._applications: dict[str, JobApplication] = {}

    def create(self, payload: dict) -> JobApplication:
        user_id = payload.get("user_id")
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required for application creation.")

        status = payload.get("status", "applied")
        if status not in VALID_STATUSES:
            raise ValueError(f"Unsupported status '{status}'.")

        application = JobApplication(
            application_id=payload.get("application_id") or str(uuid.uuid4()),
            user_id=user_id,
            company=payload.get("company", ""),
            position=payload.get("position", ""),
            status=status,
            job_url=payload.get("job_url"),
            notes=payload.get("notes", ""),
            follow_up_date=validate_follow_up(payload.get("follow_up_date")),
            job_key=payload.get("job_key"),
            source=payload.get("source"),
            project_id=payload.get("project_id"),
            cv_document_id=payload.get("cv_document_id"),
            cover_letter_document_id=payload.get("cover_letter_document_id"),
        )
        if settings.supabase_url and settings.supabase_service_role_key:
            row = application.to_dict()
            # The five apply-flow link columns (job_key/source/project_id/
            # cv_document_id/cover_letter_document_id) were added to the domain
            # model after the original table migration. Until
            # supabase/migrations/20261013000000_application_job_links.sql is
            # applied, sending them (even as NULL) makes PostgREST reject the
            # INSERT with PGRST204 ("Could not find the '<column>' column").
            # Omit any optional link column that is unset so a plain tracker
            # entry persists against either schema; populated links are still
            # written (and require the migration, which adds the columns).
            for optional in ("job_key", "source", "project_id", "cv_document_id", "cover_letter_document_id"):
                if row.get(optional) is None:
                    row.pop(optional, None)
            stored = self._backend.create(row)
            self._applications[stored.application_id] = stored
            return stored

        self._applications[application.application_id] = application
        return application

    def list_for_user(self, user_id: str) -> list[JobApplication]:
        if settings.supabase_url and settings.supabase_service_role_key:
            rows = self._backend.list_for_user(user_id)
            for row in rows:
                self._applications[row.application_id] = row
            return rows
        return [app for app in self._applications.values() if app.user_id == user_id]

    def get(self, application_id: str) -> JobApplication | None:
        if settings.supabase_url and settings.supabase_service_role_key:
            app = self._backend.get(application_id)
            if app is not None:
                self._applications[application_id] = app
            return app
        return self._applications.get(application_id)

    def update(self, application_id: str, changes: dict) -> JobApplication:
        """Change editable fields (status, notes, follow-up, URL, company, position).

        Only :data:`UPDATABLE_FIELDS` are applied; unknown keys are ignored so a
        client cannot overwrite ownership or link fields. ``notes`` /
        ``follow_up_date`` / ``job_url`` may be cleared by sending ``null``.
        Raises ``KeyError`` for an unknown id and ``ValueError`` for bad values.
        """
        clean: dict = {key: changes[key] for key in UPDATABLE_FIELDS if key in changes}
        if not clean:
            raise ValueError("No editable fields were provided.")
        if "status" in clean and clean["status"] not in VALID_STATUSES:
            raise ValueError(f"Unsupported status '{clean['status']}'.")
        for required in ("company", "position"):
            if required in clean and not (isinstance(clean[required], str) and clean[required].strip()):
                raise ValueError(f"{required} must not be empty.")
        if "follow_up_date" in clean:
            clean["follow_up_date"] = validate_follow_up(clean["follow_up_date"])
        if "notes" in clean and clean["notes"] is None:
            clean["notes"] = ""
        clean["updated_at"] = _now()

        if settings.supabase_url and settings.supabase_service_role_key:
            updated = self._backend.update(application_id, clean)
            self._applications[application_id] = updated
            return updated

        application = self._applications[application_id]
        for key, value in clean.items():
            setattr(application, key, value)
        return application

    def update_status(self, application_id: str, status: str) -> JobApplication:
        return self.update(application_id, {"status": status})

    def link_documents(
        self,
        application_id: str,
        *,
        cv_document_id: str | None = None,
        cover_letter_document_id: str | None = None,
    ) -> JobApplication:
        """Attach generated documents to an application (apply flow)."""
        changes = {
            "cv_document_id": cv_document_id,
            "cover_letter_document_id": cover_letter_document_id,
            "updated_at": _now(),
        }
        if settings.supabase_url and settings.supabase_service_role_key:
            updated = self._backend.update(application_id, changes)
            self._applications[application_id] = updated
            return updated
        application = self._applications[application_id]
        for key, value in changes.items():
            setattr(application, key, value)
        return application

    # ------------------------------------------------------------------ #
    # Job-search integration: "have I already dealt with this job?"
    # ------------------------------------------------------------------ #
    @staticmethod
    def _identity(applications: list[JobApplication]) -> tuple[set[str], set[str], set[str]]:
        """Strict keys, normalised URLs and loose keys of tracked applications.

        The loose ``company|position`` key is only used for entries that
        recorded neither a job key nor a URL (manual entries); otherwise two
        postings of the same title in different cities would hide each other.
        """
        strict: set[str] = set()
        urls: set[str] = set()
        loose: set[str] = set()
        for application in applications:
            url = normalize_url(application.job_url)
            if application.job_key:
                strict.add(application.job_key)
            if url:
                urls.add(url)
            if not application.job_key and not url:
                loose.add(loose_key(application.company, application.position))
        return strict, urls, loose

    def job_match_filter(self, user_id: str) -> tuple[Callable[[Job], bool], str]:
        """Predicate telling whether a :class:`Job` is already tracked, plus a
        cache token that changes whenever the tracked set changes."""
        strict, urls, loose = self._identity(self.list_for_user(user_id))

        def is_tracked(job: Job) -> bool:
            if compute_job_key(job.company, job.title, job.location) in strict:
                return True
            url = normalize_url(job.url)
            if url and url in urls:
                return True
            return loose_key(job.company, job.title) in loose

        token = hashlib.sha256(
            "|".join(sorted(strict) + ["#"] + sorted(urls) + ["#"] + sorted(loose)).encode()
        ).hexdigest()[:16]
        return is_tracked, token

    def status_by_job(self, user_id: str) -> Callable[[dict], str | None]:
        """Lookup returning the tracked status for a serialised job dict (or ``None``)."""
        applications = self.list_for_user(user_id)

        def lookup(job: dict) -> str | None:
            key = job.get("job_key")
            url = normalize_url(job.get("url"))
            for application in applications:
                if key and application.job_key == key:
                    return application.status
                if url and normalize_url(application.job_url) == url:
                    return application.status
                if (
                    not application.job_key
                    and not application.job_url
                    and loose_key(application.company, application.position)
                    == loose_key(job.get("company"), job.get("title"))
                ):
                    return application.status
            return None

        return lookup

    def delete(self, application_id: str) -> bool:
        """Delete one application. Ownership is enforced by the route layer."""
        if settings.supabase_url and settings.supabase_service_role_key:
            deleted = self._backend.delete(application_id)
            if deleted:
                self._applications.pop(application_id, None)
            return deleted

        if application_id in self._applications:
            del self._applications[application_id]
            return True
        return False


application_tracker = ApplicationTracker()
