"""Tests for the Supabase repository's fallback decision.

Supabase answers a missing **table** and a missing **column** with text that
both contain "in the schema cache". Treating them the same silently discarded
writes into memory whenever a migration had not been applied — the API
returned 201 and the data vanished on the next process. That is what
`_is_missing_table_error` now distinguishes.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.persistence import SupabaseRepository


def response(text: str) -> httpx.Response:
    return httpx.Response(400, text=text)


def postgrest(code: str, message: str) -> str:
    return '{"code":"%s","message":"%s"}' % (code, message.replace("'", "\\'"))


@pytest.fixture
def repo() -> SupabaseRepository:
    return SupabaseRepository("chat_sessions", dict)


@pytest.mark.parametrize(
    "text",
    [
        postgrest("PGRST205", "Could not find the table 'chat_sessions' in the schema cache"),
        "Could not find the table public.chat_sessions in the schema cache",
        'relation "chat_sessions" does not exist',
    ],
)
def test_missing_table_falls_back_to_memory(repo, text):
    """Absent table is the intended graceful degradation (no DB configured)."""
    assert repo._is_missing_table_error(response(text)) is True


@pytest.mark.parametrize(
    "text",
    [
        postgrest(
            "PGRST204",
            "Could not find the 'language' column of 'chat_sessions' in the schema cache",
        ),
        postgrest(
            "PGRST204",
            "Could not find the 'routing' column of 'chat_messages' in the schema cache",
        ),
        "Could not find the 'routing' column of 'chat_messages'",
        postgrest("PGRST202", "Could not find the function public.knowledge_search"),
        postgrest("23505", "duplicate key value violates unique constraint"),
    ],
)
def test_stale_schema_and_other_errors_do_not_fall_back(repo, text):
    """A missing column means the schema is out of date — must raise, not cache.

    Silently caching here is silent data loss: the endpoint would answer 201
    and the row would be gone on the next process.
    """
    assert repo._is_missing_table_error(response(text)) is False


def test_the_two_cases_are_disambiguated(repo):
    """The regression itself: same "in the schema cache" text, opposite outcomes."""
    table = response(postgrest("PGRST205", "Could not find the table 't' in the schema cache"))
    column = response(postgrest("PGRST204", "Could not find the 'x' column of 't' in the schema cache"))
    assert repo._is_missing_table_error(table) is True
    assert repo._is_missing_table_error(column) is False


def test_exception_detail_is_handled(repo):
    """The httpx exception path passes the exception, whose str() is the message."""
    assert repo._is_missing_table_error(RuntimeError(postgrest("PGRST205", "no such table"))) is True
    assert repo._is_missing_table_error(RuntimeError(postgrest("PGRST204", "no such column"))) is False
