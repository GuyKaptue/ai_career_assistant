"""The chat session's job context: what is written, and what happens without the column.

PostgREST answers an unknown column with PGRST204 ("Could not find the 'col'
column of 'x' in the schema cache"). The strict backend below reproduces that:
it only accepts the columns the table really has, so a write of a column that
the migration has not added is rejected instead of being silently dropped.
"""

from __future__ import annotations

import dataclasses
import logging

import pytest

from app.application.services import chat_store as chat_store_module
from app.application.services.chat_store import chat_store
from app.core.config import settings
from app.core.errors import DatabaseError
from app.domain.chat.models import ChatMessage, ChatSession

#: The columns of ``public.chat_sessions`` (migration rd08_004 adds job_context).
SESSION_COLUMNS = frozenset(
    {
        "id",
        "user_id",
        "title",
        "model_id",
        "mode",
        "language",
        "created_at",
        "updated_at",
        "job_context",
    }
)

#: The columns of ``public.chat_messages``.
MESSAGE_COLUMNS = frozenset(
    {
        "id",
        "session_id",
        "role",
        "content",
        "model_id",
        "citations",
        "artifact",
        "routing",
        "created_at",
    }
)


class StrictBackend:
    """A PostgREST-like backend: unknown columns are rejected, not ignored."""

    def __init__(self, model_factory, columns: frozenset[str], key_field: str = "id"):
        self._factory = model_factory
        self._columns = columns
        self._key = key_field
        self.rows: dict[str, dict] = {}
        self.inserted: list[dict] = []
        self.patched: list[dict] = []

    def _check(self, payload: dict, what: str) -> None:
        unknown = sorted(set(payload) - self._columns)
        if unknown:
            raise DatabaseError(
                "The database rejected the write.",
                internal=(f"PGRST204: Could not find the '{unknown[0]}' column of the table in the schema cache"),
            )

    def create(self, payload: dict):
        self._check(payload, "create")
        self.inserted.append(dict(payload))
        key = str(payload.get(self._key))
        self.rows[key] = dict(payload)
        return self._factory(**payload)

    def update(self, record_id: str, payload: dict):
        self._check(payload, "update")
        self.patched.append(dict(payload))
        row = self.rows[str(record_id)]
        row.update(payload)
        return self._factory(**row)

    def get(self, record_id: str):
        row = self.rows.get(str(record_id))
        return self._factory(**row) if row is not None else None

    def list_for_user(self, user_id: str) -> list:
        return [self._factory(**row) for row in self.rows.values() if row.get("user_id") == user_id]

    def delete(self, record_id: str) -> bool:
        return self.rows.pop(str(record_id), None) is not None


def _use_backend(monkeypatch, *, with_job_context: bool) -> StrictBackend:
    """Put the chat store on a strict backend, as Supabase would be."""
    columns = SESSION_COLUMNS if with_job_context else SESSION_COLUMNS - {"job_context"}
    sessions = StrictBackend(ChatSession, columns)
    messages = StrictBackend(ChatMessage, MESSAGE_COLUMNS)
    monkeypatch.setattr(
        chat_store_module,
        "settings",
        dataclasses.replace(
            settings,
            supabase_url=settings.supabase_url or "https://supabase.test",
            supabase_service_role_key=settings.supabase_service_role_key or "service-role-test",
        ),
    )
    monkeypatch.setattr(chat_store, "_sessions_backend", sessions)
    monkeypatch.setattr(chat_store, "_messages_backend", messages)
    monkeypatch.setattr(chat_store, "_sessions", {})
    return sessions


def test_create_session_sends_only_the_session_columns(monkeypatch):
    """The INSERT carries an explicit column list — no session_job, no messages."""
    sessions = _use_backend(monkeypatch, with_job_context=True)
    session = chat_store.create_session(user_id="owner", title="Thread")

    assert len(sessions.inserted) == 1
    row = sessions.inserted[0]
    assert set(row) == {
        "id",
        "user_id",
        "title",
        "model_id",
        "mode",
        "language",
        "created_at",
        "updated_at",
    }
    assert "session_job" not in row
    assert "messages" not in row
    assert "message_count" not in row
    assert "job_context" not in row  # the column is only written by the PATCH
    assert session.id == row["id"]


def test_set_session_job_patches_only_the_job_context_column(monkeypatch):
    """The PATCH carries exactly one column: job_context."""
    sessions = _use_backend(monkeypatch, with_job_context=True)
    session = chat_store.create_session(user_id="owner")
    context = {"title": "Data Engineer", "description": "posting text"}

    chat_store.set_session_job(session, context)

    assert len(sessions.patched) == 1
    assert sessions.patched[0] == {"job_context": context}
    assert "session_job" not in sessions.patched[0]
    assert "messages" not in sessions.patched[0]
    assert sessions.rows[session.id]["job_context"] == context


def test_strict_backend_rejects_an_unknown_column(monkeypatch):
    """Without the migration the PATCH is refused — and the turn is not blocked.

    The strict backend raises like PostgREST (PGRST204); the store catches it
    so the chat turn keeps working. The row stays unchanged.
    """
    sessions = _use_backend(monkeypatch, with_job_context=False)
    session = chat_store.create_session(user_id="owner")

    # Does not raise: a missing column must never break the turn.
    chat_store.set_session_job(session, {"title": "Data Engineer"})

    # The strict backend refused the write, so the row has no job_context.
    assert sessions.patched == []
    assert "job_context" not in sessions.rows[session.id]
    # The in-memory copy is only a cache; the row is the source of truth.
    assert session.job_context == {"title": "Data Engineer"}

    # The backend really does reject the unknown column (like PostgREST).
    with pytest.raises(DatabaseError):
        sessions.update(session.id, {"job_context": {"title": "x"}})


def test_persist_failure_is_logged_without_content(monkeypatch, caplog):
    """A failing PATCH is logged as a fact — never with the context content."""
    _use_backend(monkeypatch, with_job_context=False)
    session = chat_store.create_session(user_id="owner")

    with caplog.at_level(logging.INFO):
        chat_store.set_session_job(session, {"title": "SecretJobTitle", "description": "SecretText"})

    messages = [record.getMessage() for record in caplog.records]
    assert any("job context could not be persisted" in message for message in messages)
    for message in messages:
        assert "SecretJobTitle" not in message
        assert "SecretText" not in message


def test_session_without_the_column_still_loads_and_answers(monkeypatch):
    """Migration not applied: the row has no job_context key at all."""
    sessions = _use_backend(monkeypatch, with_job_context=True)
    session = chat_store.create_session(user_id="owner")
    # A row written before the migration: the column is simply absent.
    row = dict(sessions.rows[session.id])
    row.pop("job_context", None)
    sessions.rows[session.id] = row
    monkeypatch.setattr(chat_store, "_sessions", {})

    loaded = chat_store.get_session(session.id, "owner")
    assert loaded is not None
    assert loaded.job_context is None
    assert loaded.session_job is None
    # The session still works: a pasted job needs no stored context.
    assert loaded.title == "New chat"
