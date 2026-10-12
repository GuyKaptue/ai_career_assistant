from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

VALID_STATUSES = {"applied", "interview", "offer", "rejected"}

# Fields a user may change after creation (PATCH /api/v1/applications/{id}).
UPDATABLE_FIELDS = ("company", "position", "status", "job_url", "notes", "follow_up_date")


@dataclass
class JobApplication:
    application_id: str
    user_id: str
    company: str
    position: str
    status: str = "applied"
    job_url: str | None = None
    notes: str = ""
    applied_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    follow_up_date: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Links added for the project / apply workflow. All optional so manually
    # tracked applications keep working unchanged.
    job_key: str | None = None  # app.domain.jobs.keys.job_key — stable job identity
    source: str | None = None  # job board the posting came from
    project_id: str | None = None
    cv_document_id: str | None = None
    cover_letter_document_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "application_id": self.application_id,
            "user_id": self.user_id,
            "company": self.company,
            "position": self.position,
            "status": self.status,
            "job_url": self.job_url,
            "notes": self.notes,
            "applied_date": self.applied_date,
            "follow_up_date": self.follow_up_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "job_key": self.job_key,
            "source": self.source,
            "project_id": self.project_id,
            "cv_document_id": self.cv_document_id,
            "cover_letter_document_id": self.cover_letter_document_id,
        }
