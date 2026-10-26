## Purpose

The chat domain: threads, messages and the per-session job context.
No HTTP concerns, no AI concerns — the rules live in the application layer.

## Responsibilities

- A chat thread (`ChatSession`) with a mode, a language, a model and a
  message history
- A chat message (`ChatMessage`) with its routing audit
- The **job context** of a thread: the job it is about (title, company,
  location, employment type, skills, url, source host, the posting text and
  a `text_hash`). It never holds CV text and it is deleted with the session.

## Data contract

`ChatSession.to_dict()` is the **browser payload**: it carries the id, the
owner, the title, the model, the mode, the language, the timestamps, the
message count and (optionally) the messages. The job context is deliberately
**not** part of it, so the posting text never reaches the client; the client
only ever sees the safe summary in `structured.job`.

`ChatSession.job_context` is a real dataclass field, so the Supabase
repository reads and writes it like any other column
(`chat_sessions.job_context`, migration
`backend/migrations/rd08_004_chat_session_job_context.sql`).
`ChatSession.session_job` is the in-memory cache of the same context.

## Responsibilities of the owner

- `app/application/services/chat_store.py` — persistence, the session cache
  and `set_session_job()` (row first, cache second)
- `app/application/services/chat_service.py` — one chat turn end to end

## Testing

- `tests/unit/test_chat_store_job_context.py` — what is written, what is
  rejected, and what happens without the column
- `tests/api/test_chat_general_characterization.py` — the general path stays
  byte-identical

## Related Modules

- `app.application.services.career_assistant` — the intent routing
- `app.application.services.chat_input` — the input analysis
- `docs/architecture/career-intents.md` — the pipeline
