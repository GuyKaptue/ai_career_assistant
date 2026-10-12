"""Apply-to-position flow.

``apply_to_position`` turns a project (position + templates + candidate data)
into: a tailored CV, a cover letter, a tracker entry with status ``applied``
and the links between them. Tailoring is *reordering only*: skills and
highlights that match the position come first, nothing is added or rewritten,
so the flow cannot fabricate qualifications.
"""

from __future__ import annotations

import logging
from typing import Any

from app.application.services.application_tracking import application_tracker, validate_follow_up
from app.application.services.document_generation import generate_cover_letter_document, generate_cv_document
from app.application.services.document_store import DocumentStore
from app.application.services.project_store import project_store
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domain.jobs.keys import job_key
from app.domain.positions.models import Position
from app.domain.projects.models import Project

logger = logging.getLogger(__name__)


def _terms(position: Position) -> set[str]:
    words = {word.casefold() for word in position.keywords}
    words.update(part.casefold() for part in (position.title or "").replace("/", " ").split() if len(part) > 2)
    return words


def _relevance(text: str, terms: set[str], haystack: str) -> int:
    lowered = text.casefold()
    return int(lowered in haystack or any(term in lowered for term in terms))


def tailor_candidate(candidate: dict[str, Any], position: Position) -> dict[str, Any]:
    """Return a copy of ``candidate`` tuned to ``position`` without adding content."""
    terms = _terms(position)
    haystack = position.description.casefold()
    tailored = dict(candidate)

    skills = [str(skill) for skill in candidate.get("skills") or []]
    tailored["skills"] = sorted(
        skills, key=lambda skill: -_relevance(skill, terms, haystack)
    )  # stable: ties keep order

    experience = []
    for entry in candidate.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        highlights = [str(item) for item in entry.get("highlights") or []]
        experience.append(
            {**entry, "highlights": sorted(highlights, key=lambda item: -_relevance(item, terms, haystack))}
        )
    if experience:
        tailored["experience"] = experience

    tailored["target_role"] = position.title or candidate.get("target_role")
    if position.company:
        tailored["company"] = position.company
    return tailored


def _require_candidate_name(candidate: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(candidate, dict) or not str(candidate.get("name") or "").strip():
        raise ValidationError(
            "candidate.name is required to generate documents "
            "(or pass existing cv_document_id / cover_letter_document_id)."
        )
    return candidate


def _owned_document(store: DocumentStore, document_id: str, user_id: str, expected_type: str) -> Any:
    record = store.get(document_id)
    if record is None or record.user_id != user_id:
        raise NotFoundError("Document not found.")
    if record.document_type != expected_type:
        raise ValidationError(f"Document {document_id} is not a {expected_type.replace('_', ' ')}.")
    return record


def apply_to_position(
    project: Project,
    user_id: str,
    options: dict[str, Any],
    *,
    document_store: DocumentStore,
) -> dict[str, Any]:
    """Create documents + tracker entry for ``project``; returns a summary dict."""
    if project.status == "applied" or project.application_id:
        raise ConflictError("This project has already been applied to.")
    if not project.position:
        raise ValidationError("Attach a position to the project before applying.")
    position = Position.from_dict(project.position)
    if not position.company or not position.title:
        raise ValidationError("The position needs a title and a company before applying; edit the position first.")

    try:
        follow_up = validate_follow_up(options.get("follow_up_date")) if options.get("follow_up_date") else None
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    include_letter = bool(options.get("include_cover_letter", True))
    candidate = options.get("candidate")
    tailored = tailor_candidate(candidate, position) if isinstance(candidate, dict) else None

    created: list[str] = []
    cv_id: str | None = options.get("cv_document_id") or None
    letter_id: str | None = options.get("cover_letter_document_id") or None
    try:
        # Validate everything that can fail on user input BEFORE creating rows.
        if cv_id:
            _owned_document(document_store, cv_id, user_id, "cv")
        else:
            tailored = tailor_candidate(_require_candidate_name(candidate), position)
        if letter_id:
            _owned_document(document_store, letter_id, user_id, "cover_letter")
        elif include_letter and tailored is None:
            tailored = tailor_candidate(_require_candidate_name(candidate), position)

        if not cv_id:
            assert tailored is not None  # nosec B101 - narrowed by the validation above
            generated = generate_cv_document(tailored, template_id=project.template_id)
            cv = document_store.create(
                {
                    "user_id": user_id,
                    "title": f"CV – {position.company} – {position.title}",
                    "document_type": "cv",
                    "template_id": generated["template_id"],
                    "content": generated["content"],
                }
            )
            cv_id = cv.id
            created.append(cv.id)
        if include_letter and not letter_id:
            assert tailored is not None  # nosec B101 - narrowed by the validation above
            letter_data = generate_cover_letter_document(tailored, template_id=project.cover_letter_template_id)
            letter = document_store.create(
                {
                    "user_id": user_id,
                    "title": f"Cover letter – {position.company} – {position.title}",
                    "document_type": "cover_letter",
                    "template_id": letter_data["template_id"],
                    "content": letter_data["content"],
                }
            )
            letter_id = letter.id
            created.append(letter.id)

        application = application_tracker.create(
            {
                "user_id": user_id,
                "company": position.company,
                "position": position.title,
                "status": "applied",
                "job_url": position.url,
                "notes": options.get("notes") or "",
                "follow_up_date": follow_up,
                "job_key": job_key(position.company, position.title, position.location),
                "source": position.source,
                "project_id": project.id,
                "cv_document_id": cv_id,
                "cover_letter_document_id": letter_id,
            }
        )
        updated = project_store.update(
            project.id,
            {
                "status": "applied",
                "application_id": application.application_id,
                "cv_document_id": cv_id,
                "cover_letter_document_id": letter_id,
            },
            internal=True,
        )
    except Exception:
        # Do not leave orphaned documents behind when a later step fails.
        for document_id in created:
            try:
                document_store.delete(document_id)
            except Exception:  # noqa: BLE001 - best-effort cleanup must not mask the original error
                logger.warning("apply.cleanup_failed document_id=%s", document_id)
        raise

    return {
        "project": updated.to_dict(),
        "application": application.to_dict(),
        "documents": {"cv_document_id": cv_id, "cover_letter_document_id": letter_id},
        "generated": created,
        "ai_generated": False,
    }
