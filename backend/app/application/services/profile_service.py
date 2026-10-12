from __future__ import annotations

import logging

from app.core.config import settings
from app.core.persistence import InMemoryRepository, SupabaseRepository
from app.domain.users.models import UserProfile

logger = logging.getLogger(__name__)


class ProfileStore:
    """Storage backend that prefers Supabase when configured and otherwise uses memory."""

    def __init__(self) -> None:
        self._backend: SupabaseRepository | InMemoryRepository
        if settings.supabase_url and settings.supabase_service_role_key:
            self._backend = SupabaseRepository("profiles", UserProfile, "user_id")
        else:
            self._backend = InMemoryRepository()
        self._profiles: dict[str, UserProfile] = {}

    def create(self, payload: dict) -> UserProfile:
        user_id = payload.get("user_id")
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required for profile creation.")

        profile = UserProfile(
            user_id=user_id,
            email=payload.get("email", ""),
            full_name=payload.get("full_name", ""),
            target_role=payload.get("target_role", ""),
            location=payload.get("location", ""),
            summary=payload.get("summary", ""),
        )
        backend = "supabase" if settings.supabase_url and settings.supabase_service_role_key else "memory"
        logger.info("profile_store.create user_id=%s backend=%s", user_id, backend)
        try:
            if settings.supabase_url and settings.supabase_service_role_key:
                record = self._backend.create(profile.to_dict())
                self._profiles[user_id] = record
                logger.info("profile_store.create committed user_id=%s backend=supabase", user_id)
                return record
        except Exception:
            logger.exception("profile_store.create FAILED user_id=%s backend=%s", user_id, backend)
            raise

        self._profiles[user_id] = profile
        logger.info("profile_store.create committed user_id=%s backend=memory", user_id)
        return profile

    def get(self, user_id: str) -> UserProfile | None:
        if settings.supabase_url and settings.supabase_service_role_key:
            record = self._backend.get(user_id)
            logger.info("profile_store.get user_id=%s backend=supabase found=%s", user_id, record is not None)
            if record is not None:
                self._profiles[user_id] = record
            return record
        return self._profiles.get(user_id)

    def update(self, user_id: str, payload: dict) -> UserProfile:
        if settings.supabase_url and settings.supabase_service_role_key:
            profile = self._profiles.get(user_id)
            if profile is None:
                profile = self.get(user_id)
            if profile is None:
                raise KeyError(user_id)
            safe_payload = {key: value for key, value in payload.items() if hasattr(profile, key)}
            updated = self._backend.update(user_id, safe_payload)
            self._profiles[user_id] = updated
            return updated

        profile = self._profiles[user_id]
        for field_name, value in payload.items():
            if hasattr(profile, field_name):
                setattr(profile, field_name, value)
        profile.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        return profile

    def delete(self, user_id: str) -> bool:
        """Delete one profile. Returns True when a profile existed."""
        if settings.supabase_url and settings.supabase_service_role_key:
            deleted = self._backend.delete(user_id)
            if deleted:
                self._profiles.pop(user_id, None)
            return deleted

        if user_id in self._profiles:
            del self._profiles[user_id]
            return True
        return False


profile_store = ProfileStore()
