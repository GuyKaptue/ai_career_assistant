"""Chat platform API routes.

- ``POST   /api/v1/chat/sessions`` — create a thread.
- ``GET    /api/v1/chat/sessions`` — list the user's threads (sidebar).
- ``GET    /api/v1/chat/sessions/{id}`` — one thread with its message history.
- ``DELETE /api/v1/chat/sessions/{id}`` — delete a thread (GDPR erasure).
- ``POST   /api/v1/chat/completions`` — one conversation turn (RAG-grounded,
  deterministic fallback). Creates a session when ``session_id`` is omitted.

The routable-model list for the chat model picker is served separately at
``GET /api/v1/models`` (see ``main.py``), matching the top-level
``/api/v1/templates`` convention.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.schemas import (
    COMMON_ERROR_RESPONSES,
    GENERATION_ERROR_RESPONSES,
    ChatCompletionPayload,
    ChatSessionCreatePayload,
)
from app.application.services.chat_service import run_chat_turn
from app.application.services.chat_store import chat_store
from app.core.errors import NotFoundError, ValidationError
from app.core.security.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/chat", tags=["chat"], responses=COMMON_ERROR_RESPONSES)


@router.post("/sessions", status_code=201)
def create_session(body: ChatSessionCreatePayload, current_user: dict = Depends(get_current_user)) -> dict:
    payload = body.model_dump(exclude_unset=True)
    try:
        session = chat_store.create_session(
            user_id=current_user["sub"],
            title=(payload.get("title") or "New chat"),
            model_id=payload.get("model_id"),
            mode=(payload.get("mode") or "general"),
            language=(payload.get("language") or "en"),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return session.to_dict(include_messages=False)


@router.get("/sessions")
def list_sessions(current_user: dict = Depends(get_current_user)) -> dict:
    sessions = chat_store.list_sessions(current_user["sub"])
    return {"count": len(sessions), "items": [session.to_dict(include_messages=False) for session in sessions]}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    session = chat_store.get_session(session_id, current_user["sub"])
    if session is None:
        raise NotFoundError("Chat session not found.")
    return session.to_dict(include_messages=True)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Delete one owned chat session (GDPR right to erasure)."""
    deleted = chat_store.delete_session(session_id, current_user["sub"])
    if not deleted:
        raise NotFoundError("Chat session not found.")
    return {"deleted": True, "session_id": session_id}


@router.post("/completions", responses=GENERATION_ERROR_RESPONSES)
def create_completion(body: ChatCompletionPayload, current_user: dict = Depends(get_current_user)) -> dict:
    """Run one chat turn. Creates a session when ``session_id`` is omitted.

    The reply is RAG-grounded (career knowledge base + the user's own indexed
    documents) and always carries the human-review notice. When AI inference is
    unavailable the endpoint still returns a deterministic, labelled fallback
    reply (HTTP 200) so the UI never dead-ends.
    """
    payload = body.model_dump(exclude_unset=True)
    message = (payload.get("message") or "").strip()
    if not message:
        raise ValidationError("message is required.")

    session_id = payload.get("session_id")
    if session_id:
        session = chat_store.get_session(session_id, current_user["sub"])
        if session is None:
            raise NotFoundError("Chat session not found.")
    else:
        title = (payload.get("title") or message[:40] or "New chat").strip() or "New chat"
        try:
            session = chat_store.create_session(
                user_id=current_user["sub"],
                title=title,
                model_id=payload.get("model_id"),
                mode=(payload.get("mode") or "general"),
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    model_id = payload.get("model_id") or session.model_id
    document_context = payload.get("document_context") or ""

    result = run_chat_turn(
        session,
        message,
        user_id=current_user["sub"],
        model_id=model_id,
        document_context=document_context,
    )
    result["session"] = session.to_dict(include_messages=False)
    return result
