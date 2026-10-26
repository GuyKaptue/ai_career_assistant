"""Regression tests: latest message kept on long threads, markup-safe PDF."""

from app.application.services.chat_service import MAX_PROMPT_CHARS, build_chat_prompt
from app.application.services.document_generation import render_document_to_pdf
from app.domain.chat.models import ChatMessage, ChatSession

LATEST = "please find jobs that match my profile"


def _session(n: int, size: int) -> ChatSession:
    s = ChatSession(id="s", user_id="u", mode="general", language="en")
    for i in range(n):
        s.messages.append(
            ChatMessage(id=str(i), session_id="s", role="user" if i % 2 == 0 else "assistant", content="x" * size)
        )
    s.messages.append(ChatMessage(id="l", session_id="s", role="user", content=LATEST))
    return s


def test_latest_message_and_contract_survive_long_thread_and_large_cv():
    prompt = build_chat_prompt(_session(19, 1500), LATEST, document_context="cv line. " * 600)
    assert LATEST in prompt
    assert prompt.rstrip().endswith("Nothing but the answer.")
    assert len(prompt) <= MAX_PROMPT_CHARS


def test_pdf_renders_markup_like_text():
    for content in ("a <b>unclosed", "x <img src='/etc/passwd'/>", "R&D <para> text"):
        assert render_document_to_pdf({"title": "T <b>", "content": content}).startswith(b"%PDF")
