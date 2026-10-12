"""Chat session store: user-scoped threads with message history.

Mirrors document_store: in-memory when Supabase is unconfigured
(hermetic tests, offline dev), Supabase REST (chat_sessions /
chat_messages) when configured. Reads filter by JWT `sub`; foreign
sessions return None so routes answer 404 (never 403).
"""

from __future__ import annotations

import logging
import uuid

from app.core.config import settings
from app.core.persistence import InMemoryRepository, SupabaseRepository
from app.domain.chat.models import CHAT_LANGUAGES, CHAT_MODES, ChatMessage, ChatSession, utc_now_iso

logger = logging.getLogger(__name__)

# Bounded history so a thread never grows without limit.
MAX_MESSAGES_PER_SESSION = 200


class ChatStore:
    def __init__(self) -> None:
        if settings.supabase_url and settings.supabase_service_role_key:
            self._sessions_backend: SupabaseRepository | InMemoryRepository = SupabaseRepository(
                "chat_sessions", ChatSession, "id"
            )
            self._messages_backend: SupabaseRepository | InMemoryRepository = SupabaseRepository(
                "chat_messages", ChatMessage, "id"
            )
        else:
            self._sessions_backend = InMemoryRepository()
            self._messages_backend = InMemoryRepository()
        self._sessions: dict[str, ChatSession] = {}

    def create_session(
        self,
        *,
        user_id: str,
        title: str = "New chat",
        model_id: str | None = None,
        mode: str = "general",
        language: str = "en",
    ) -> ChatSession:
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id is required for chat session creation.")
        if mode not in CHAT_MODES:
            raise ValueError(f"Unknown chat mode '{mode}'. Use one of: {', '.join(CHAT_MODES)}.")
        if language not in CHAT_LANGUAGES:
            raise ValueError(f"Unknown chat language '{language}'. Use one of: {', '.join(CHAT_LANGUAGES)}.")
        now = utc_now_iso()
        session = ChatSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title.strip() or "New chat",
            model_id=model_id,
            mode=mode,
            language=language,
            created_at=now,
            updated_at=now,
        )
        if settings.supabase_url and settings.supabase_service_role_key:
            # `to_dict()` adds the derived `message_count` (len(messages)); that is
            # a read-only summary, not a table column. Sending it makes PostgREST
            # reject the INSERT with PGRST204 ("Could not find the 'message_count'
            # column"), so strip it (and any other non-column key) before writing.
            row = {
                key: value for key, value in session.to_dict(include_messages=False).items() if key != "message_count"
            }
            stored = self._sessions_backend.create(row)
            self._sessions[stored.id] = stored
            return stored
        self._sessions[session.id] = session
        logger.debug(
            "chat session created: id=%s user=%s mode=%s language=%s",
            session.id,
            user_id,
            mode,
            language,
        )
        return session

    def get_session(self, session_id: str, user_id: str) -> ChatSession | None:
        """Return the session only when it belongs to `user_id` (else None = 404)."""
        session = self._sessions.get(session_id)
        if session is None and settings.supabase_url and settings.supabase_service_role_key:
            session = self._sessions_backend.get(session_id)
            if session is not None:
                session.messages = self._messages_for(session_id)
                self._sessions[session_id] = session
        if session is None or session.user_id != user_id:
            return None
        return session

    def list_sessions(self, user_id: str) -> list[ChatSession]:
        if settings.supabase_url and settings.supabase_service_role_key:
            rows = self._sessions_backend.list_for_user(user_id)
            for row in rows:
                cached = self._sessions.get(row.id)
                if cached is not None:
                    row.messages = cached.messages
                self._sessions[row.id] = row
            return sorted(rows, key=lambda item: item.updated_at, reverse=True)
        owned = [item for item in self._sessions.values() if item.user_id == user_id]
        return sorted(owned, key=lambda item: item.updated_at, reverse=True)

    def delete_session(self, session_id: str, user_id: str) -> bool:
        session = self.get_session(session_id, user_id)
        if session is None:
            return False
        if settings.supabase_url and settings.supabase_service_role_key:
            deleted = self._sessions_backend.delete(session_id)
            if deleted:
                self._sessions.pop(session_id, None)
            return deleted
        self._sessions.pop(session_id, None)
        return True

    def append_message(
        self,
        session: ChatSession,
        *,
        role: str,
        content: str,
        model_id: str | None = None,
        citations: list[dict] | None = None,
        artifact: dict | None = None,
        routing: dict | None = None,
    ) -> ChatMessage:
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Unknown message role '{role}'.")
        if not content or not content.strip():
            raise ValueError("Message content is required.")
        message = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role=role,
            content=content,
            model_id=model_id,
            citations=list(citations or []),
            artifact=artifact,
            routing=dict(routing or {}),
            created_at=utc_now_iso(),
        )
        if settings.supabase_url and settings.supabase_service_role_key:
            stored = self._messages_backend.create(message.to_dict())
            session.messages.append(stored)
        else:
            session.messages.append(message)
        while len(session.messages) > MAX_MESSAGES_PER_SESSION:
            for index, existing in enumerate(session.messages):
                if existing.role != "system":
                    session.messages.pop(index)
                    break
            else:
                break
        session.updated_at = utc_now_iso()
        return message

    def _messages_for(self, session_id: str) -> list[ChatMessage]:
        if settings.supabase_url and settings.supabase_service_role_key:
            rows = self._messages_backend.list_for_user(session_id)
            return sorted(rows, key=lambda item: item.created_at)
        return []


chat_store = ChatStore()
