"""Chat domain models: sessions (threads) and messages.

A session is a conversation thread owned by one user (JWT `sub`).
Messages alternate user/assistant; assistant messages carry the model
that produced them plus optional source citations and artifact payloads
(CV / cover letter / analysis previews rendered side-by-side).

Persistence mirrors the documents pattern: an in-memory store when
Supabase is unconfigured (tests, offline dev), Supabase REST when
configured (see the chat_sessions/chat_messages migration).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ChatMessage:
    """One message inside a chat session."""

    id: str
    session_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    model_id: str | None = None
    citations: list[dict] = field(default_factory=list)
    artifact: dict | None = None
    routing: dict = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "model_id": self.model_id,
            "citations": self.citations,
            "artifact": self.artifact,
            "routing": self.routing,
            "created_at": self.created_at,
        }


@dataclass
class ChatSession:
    """A conversation thread: title, model, mode, message history."""

    id: str
    user_id: str
    title: str = "New chat"
    model_id: str | None = None
    mode: str = "general"
    language: str = "en"
    created_at: str = ""
    updated_at: str = ""
    messages: list[ChatMessage] = field(default_factory=list)

    def to_dict(self, *, include_messages: bool = True) -> dict:
        payload: dict[str, object] = {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "model_id": self.model_id,
            "mode": self.mode,
            "language": self.language,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
        }
        if include_messages:
            payload["messages"] = [message.to_dict() for message in self.messages]
        return payload


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


#: The app's supported chat languages (mirrors the frontend i18n locales).
CHAT_LANGUAGES: tuple[str, ...] = ("en", "de", "fr")

CHAT_MODES: tuple[str, ...] = (
    "general",
    "cv_builder",
    "cover_letter",
    "ats_checker",
    "job_search",
    "interview_prep",
)

#: Prompt-task mapping per mode: the HF router task used for inference.
MODE_TASKS: dict[str, str] = {
    "general": "career_advice",
    "cv_builder": "cv_generation",
    "cover_letter": "cover_letter_generation",
    "ats_checker": "ats_analysis",
    "job_search": "job_matching",
    "interview_prep": "career_advice",
}
