"""The shared user-data core (RD-08 §1).

One typed structure consumed by every career intent (job search, CV tailoring,
cover letter), so no frontend field is lost between intents. Frontend payload
keys are mapped explicitly in :data:`PAYLOAD_FIELD_MAP`; keys that are not
mapped are reported by :func:`core_from_payload` instead of being dropped silently.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Final, Mapping

from app.domain.users.models import UserProfile

MAX_LIST_ITEMS: Final = 20
MAX_ITEM_CHARS: Final = 120
MAX_CV_CHARS: Final = 60_000
REMOTE_POLICIES: Final = frozenset({"onsite", "hybrid", "remote", "any"})
SUPPORTED_LANGUAGES: Final = ("en", "de", "fr")

# frontend payload key -> UserCore attribute (camelCase and snake_case accepted)
PAYLOAD_FIELD_MAP: Final[dict[str, str]] = {
    "targetTitles": "target_titles",
    "target_titles": "target_titles",
    "targetRole": "target_titles",
    "target_role": "target_titles",
    "targetIndustries": "target_industries",
    "target_industries": "target_industries",
    "preferredLocations": "preferred_locations",
    "preferred_locations": "preferred_locations",
    "location": "preferred_locations",
    "remotePolicy": "remote_policy",
    "remote_policy": "remote_policy",
    "employmentTypes": "employment_types",
    "employment_types": "employment_types",
    "salaryMin": "salary_min",
    "salary_min": "salary_min",
    "salaryMax": "salary_max",
    "salary_max": "salary_max",
    "salaryCurrency": "salary_currency",
    "salary_currency": "salary_currency",
    "seniority": "seniority",
    "workAuthorization": "work_authorization",
    "work_authorization": "work_authorization",
    "noticePeriodDays": "notice_period_days",
    "notice_period_days": "notice_period_days",
    "mustHaves": "must_haves",
    "must_haves": "must_haves",
    "dealBreakers": "deal_breakers",
    "deal_breakers": "deal_breakers",
    "cvTemplateId": "cv_template_id",
    "cv_template_id": "cv_template_id",
    "coverLetterTemplateId": "cover_letter_template_id",
    "cover_letter_template_id": "cover_letter_template_id",
    "language": "language",
}


def _clean_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    items = [value] if isinstance(value, str) else list(value)
    seen: dict[str, str] = {}
    for item in items:
        text = " ".join(str(item).split())[:MAX_ITEM_CHARS]
        if text:
            seen.setdefault(text.casefold(), text)
    return tuple(seen.values())[:MAX_LIST_ITEMS]


def _clean_text(value: Any) -> str:
    return " ".join(str(value).split())[:MAX_ITEM_CHARS] if value is not None else ""


def _clean_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


@dataclass(frozen=True)
class UserCore:
    """Everything known about the user that any career intent may need."""

    user_id: str
    cv_text: str = ""
    cv_document_id: str = ""
    language: str = "en"
    target_titles: tuple[str, ...] = ()
    target_industries: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    remote_policy: str = ""
    employment_types: tuple[str, ...] = ()
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = ""
    seniority: str = ""
    work_authorization: str = ""
    notice_period_days: int | None = None
    must_haves: tuple[str, ...] = ()
    deal_breakers: tuple[str, ...] = ()
    cv_template_id: str = ""
    cover_letter_template_id: str = ""
    accepted_context: tuple[str, ...] = field(default=())

    @property
    def has_cv(self) -> bool:
        return bool(self.cv_text.strip())

    def preference_summary(self) -> dict[str, Any]:
        """Non-empty preference fields only. Never contains name, email or CV text."""
        raw: dict[str, Any] = {
            "target_titles": list(self.target_titles),
            "target_industries": list(self.target_industries),
            "preferred_locations": list(self.preferred_locations),
            "remote_policy": self.remote_policy,
            "employment_types": list(self.employment_types),
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "seniority": self.seniority,
            "work_authorization": self.work_authorization,
            "notice_period_days": self.notice_period_days,
            "must_haves": list(self.must_haves),
            "deal_breakers": list(self.deal_breakers),
        }
        return {key: value for key, value in raw.items() if value not in ("", None, [])}

    def input_hash(self) -> str:
        """Stable hash of everything that influences an analysis (cache key)."""
        canonical = json.dumps(
            {"cv": self.cv_text.strip(), "prefs": self.preference_summary(), "lang": self.language},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_user_core(
    *,
    user_id: str,
    cv_text: str = "",
    cv_document_id: str = "",
    profile: UserProfile | None = None,
    preferences: Mapping[str, Any] | None = None,
    language: str = "en",
    accepted_context: tuple[str, ...] = (),
) -> UserCore:
    """Merge profile + stored preferences into a normalized :class:`UserCore`.

    ``preferences`` keys are UserCore attribute names (as stored in
    ``profile_preferences``). Profile ``target_role``/``location`` fill in only
    when the preferences leave those lists empty.
    """
    prefs = dict(preferences or {})
    titles = _clean_list(prefs.get("target_titles")) or _clean_list(profile.target_role if profile else "")
    locations = _clean_list(prefs.get("preferred_locations")) or _clean_list(profile.location if profile else "")
    remote = _clean_text(prefs.get("remote_policy")).lower()
    lang = (language or "en").strip().lower()
    return UserCore(
        user_id=user_id,
        cv_text=(cv_text or "")[:MAX_CV_CHARS],
        cv_document_id=_clean_text(cv_document_id),
        language=lang if lang in SUPPORTED_LANGUAGES else "en",
        target_titles=titles,
        target_industries=_clean_list(prefs.get("target_industries")),
        preferred_locations=locations,
        remote_policy=remote if remote in REMOTE_POLICIES else "",
        employment_types=_clean_list(prefs.get("employment_types")),
        salary_min=_clean_int(prefs.get("salary_min")),
        salary_max=_clean_int(prefs.get("salary_max")),
        salary_currency=_clean_text(prefs.get("salary_currency")).upper()[:3],
        seniority=_clean_text(prefs.get("seniority")),
        work_authorization=_clean_text(prefs.get("work_authorization")),
        notice_period_days=_clean_int(prefs.get("notice_period_days")),
        must_haves=_clean_list(prefs.get("must_haves")),
        deal_breakers=_clean_list(prefs.get("deal_breakers")),
        cv_template_id=_clean_text(prefs.get("cv_template_id")),
        cover_letter_template_id=_clean_text(prefs.get("cover_letter_template_id")),
        accepted_context=_clean_list(accepted_context),
    )


def core_from_payload(
    payload: Mapping[str, Any],
    *,
    user_id: str,
    cv_text: str = "",
    cv_document_id: str = "",
    profile: UserProfile | None = None,
    stored_preferences: Mapping[str, Any] | None = None,
) -> tuple[UserCore, list[str]]:
    """Build a core from a frontend payload; returns ``(core, unmapped_keys)``.

    Payload values override stored preferences. ``unmapped_keys`` lists payload
    keys that no core field accepts, so a missing mapping is visible, not silent.
    """
    merged: dict[str, Any] = dict(stored_preferences or {})
    unmapped: list[str] = []
    language = "en"
    for key, value in payload.items():
        target = PAYLOAD_FIELD_MAP.get(key)
        if target is None:
            unmapped.append(key)
        elif target == "language":
            language = str(value)
        else:
            merged[target] = value
    core = build_user_core(
        user_id=user_id,
        cv_text=cv_text,
        cv_document_id=cv_document_id,
        profile=profile,
        preferences=merged,
        language=language,
    )
    return core, sorted(unmapped)
