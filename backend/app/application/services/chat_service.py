"""Chat orchestration: prompt building, inference, deterministic fallback.

Per turn: append user message → bounded prompt (persona + mode +
history window + document/RAG context) → HF adapter with fallback →
append assistant message. RAG (RD-03/RD-05) is best-effort; offline
replies are deterministic and labelled, never fabricated.
"""

from __future__ import annotations

import logging

from app.application.services.chat_store import chat_store
from app.application.services.document_retrieval import get_document_retrieval
from app.application.services.knowledge_base import get_knowledge_base
from app.application.services.output_validation import (
    deterministic_unavailable_content,
    generate_validated,
)
from app.application.services.shared_router import get_adapter, log_routing_decision
from app.core.errors import AIProviderError
from app.domain.chat.models import MODE_TASKS, ChatSession
from app.infrastructure.ai.prompt_templates import (
    build_system_prompt,
    build_task_prompt,
    contract_for_task,
)


def contract_kind(task: str) -> str:
    """The output contract kind (json/markdown) enforced for ``task``."""
    return contract_for_task(task).kind


logger = logging.getLogger(__name__)

AI_REVIEW_NOTICE = "AI-generated content — review before sending."
HISTORY_WINDOW = 20
MAX_PROMPT_CHARS = 8000
MAX_CONTEXT_CHARS = 4000


def build_chat_prompt(session: ChatSession, user_text: str, *, document_context: str = "") -> str:
    """Assemble the bounded inference prompt for one turn.

    The prompt is now built from the contract-aware template in
    ``infrastructure/ai/prompt_templates.py``: persona + honesty rules +
    task context + bounded history/RAG context + an explicit output-format
    contract, so the model has a concrete target and the answer can be
    validated afterwards.
    """
    task = MODE_TASKS.get(session.mode, "career_advice")
    mode_instruction = MODE_INSTRUCTIONS.get(session.mode, MODE_INSTRUCTIONS["general"])
    history = "\n".join(
        f"{'User' if message.role == 'user' else 'Assistant'}: {message.content[:2000]}"
        for message in session.messages[-HISTORY_WINDOW:]
    )
    return "\n\n".join(
        (
            build_system_prompt(task, language=session.language),
            build_task_prompt(
                task,
                instruction=f"Workspace mode ({session.mode}): {mode_instruction}. Answer the user's latest message.",
                language=session.language,
                document_context=document_context,
                history=history,
            ),
        )
    )[:MAX_PROMPT_CHARS]


MODE_INSTRUCTIONS: dict[str, str] = {
    "general": "Give practical career advice tailored to the conversation.",
    "cv_builder": (
        "Help the user build or improve their CV section by section. "
        "Ask for missing facts instead of inventing them. Offer concise "
        "bullet rewrites with strong verbs."
    ),
    "cover_letter": "Help draft a tailored cover letter under 300 words unless asked otherwise.",
    "ats_checker": (
        "Analyse resume text vs job description: score 0-100, matched and missing keywords, three concrete fixes."
    ),
    "job_search": "Help refine the search: queries, locations, CV tailoring. Do not invent postings.",
    "interview_prep": "Coach interviews: ask likely questions one at a time, then feedback.",
}


def deterministic_fallback_reply(session: ChatSession, user_text: str) -> str:
    """Offline-safe reply when HF inference is unavailable (labelled, never AI)."""
    guidance = MODE_INSTRUCTIONS.get(session.mode, MODE_INSTRUCTIONS["general"])
    return (
        "[Offline reply — AI inference is unavailable right now]\n\n"
        f"Mode: {session.mode}. {guidance}\n\n"
        f"Your message ({len(user_text)} chars) was saved to this thread. "
        "Retry when the AI backend is reachable, or use the workspace tools below."
    )


def build_routing_audit(
    task: str,
    *,
    selection: str,
    selected_model: str | None,
    contract_kind: str,
    contract_status: str,
    attempts: int = 0,
    fallback_chain: list[str] | None = None,
    routing_score: float | None = None,
    failure_reason: str | None = None,
) -> dict[str, object]:
    """Per-message routing audit, stored on the assistant message.

    Explains *why* this model answered: which task triggered it, whether the
    model was auto-selected or manually pinned, what the output contract was,
    and whether that contract passed, needed repair, or fell back.
    """
    audit: dict[str, object] = {
        "selected_model": selected_model,
        "selection": selection,
        "task": task,
        "fallback_chain": list(fallback_chain or []),
        "routing_score": routing_score,
        "contract": contract_kind,
        "contract_status": contract_status,
        "attempts": attempts,
    }
    if failure_reason:
        audit["failure_reason"] = failure_reason
    return audit


def run_chat_turn(
    session: ChatSession,
    user_text: str,
    *,
    user_id: str | None = None,
    model_id: str | None = None,
    document_context: str = "",
) -> dict:
    """Execute one conversation turn and return the rendered payload."""
    text = (user_text or "").strip()
    if not text:
        raise ValueError("Message content is required.")
    chat_store.append_message(session, role="user", content=text)

    knowledge_context = ""
    personal_context = ""
    try:
        knowledge_context = get_knowledge_base().retrieve_for_generation(query=text)["context"]
    except Exception as exc:
        logger.debug("chat knowledge retrieval skipped: %s", exc)
    if user_id:
        try:
            personal_context = get_document_retrieval().retrieve_for_generation(user_id=user_id, query=text)["context"]
        except Exception as exc:
            logger.debug("chat personal retrieval skipped: %s", exc)
    rag_context = "\n\n".join(part for part in (knowledge_context, personal_context) if part)
    combined_context = "\n\n".join(part for part in (document_context, rag_context) if part)

    task = MODE_TASKS.get(session.mode, "career_advice")
    prompt = build_chat_prompt(session, text, document_context=combined_context)
    adapter = get_adapter()
    citations: list[dict] = []
    if knowledge_context:
        citations.append({"source": "career_knowledge_base", "kind": "rag"})
    try:
        # Contracts are enforced here: if the model's answer breaks the task's
        # output format it is re-prompted with the exact violations, and only
        # a labelled deterministic reply is returned if that still fails.
        result = generate_validated(
            task,
            prompt=prompt,
            language=session.language,
            token_budget=1024,
            preferred_languages=("en", "de", "fr"),
            preferred_model_id=model_id,
            generate=lambda **kwargs: adapter.generate_with_fallback(**kwargs),
            repair_generate=lambda **kwargs: adapter.generate_with_fallback(**kwargs),
        )
    except (ValueError, RuntimeError, AIProviderError) as exc:
        logger.warning("chat inference failed, deterministic fallback: %s", exc)
        reason = str(exc)[:500]
        log_routing_decision(
            task=task,
            model_id="none",
            fallback_reason=reason,
            fallback_chain=[],
            routing_score=None,
            required_context=1024,
            success=False,
        )
        # Keep the audit complete even when every candidate failed: record
        # what was tried, why, and whether the user had pinned a model.
        routing = build_routing_audit(
            task,
            selection="manual_override" if model_id else "auto",
            selected_model=None,
            contract_kind=contract_kind(task),
            contract_status="fallback",
            attempts=0,
            failure_reason=reason,
        )
        reply = deterministic_fallback_reply(session, text)
        message = chat_store.append_message(
            session,
            role="assistant",
            content=f"{reply}\n\n{AI_REVIEW_NOTICE}",
            model_id=None,
            routing=routing,
        )
        return {
            "session_id": session.id,
            "message": message.to_dict(),
            "model_id": None,
            "ai_generated": False,
            "fallback": True,
            "fallback_reason": reason,
            "citations": citations,
            "review_notice": AI_REVIEW_NOTICE,
            "routing": routing,
        }

    log_routing_decision(
        task=task,
        model_id=result.model_id or "none",
        fallback_reason=None,
        fallback_chain=result.fallback_chain,
        routing_score=result.routing_score,
        required_context=1024,
        success=True,
    )
    routing = build_routing_audit(
        task,
        selection="manual_override" if model_id else "auto",
        selected_model=result.model_id,
        contract_kind=result.kind,
        contract_status=("fallback" if result.fallback else ("repaired" if result.repaired else "passed")),
        attempts=result.attempts,
        fallback_chain=result.fallback_chain,
        routing_score=result.routing_score,
        failure_reason=result.fallback_reason if result.fallback else None,
    )

    if result.fallback:
        # The model answered but the answer never satisfied the output
        # contract, even after repair. Say so honestly instead of serving it.
        log_routing_decision(
            task=task,
            model_id=result.model_id or "none",
            fallback_reason=result.fallback_reason,
            fallback_chain=result.fallback_chain,
            routing_score=result.routing_score,
            required_context=1024,
            success=False,
        )
        payload = deterministic_unavailable_content(
            task,
            result.fallback_reason or "invalid output",
            language=session.language,
        )
        message = chat_store.append_message(
            session,
            role="assistant",
            content=f"{payload['content']}\n\n{AI_REVIEW_NOTICE}",
            model_id=result.model_id,
            routing=routing,
        )
        return {
            "session_id": session.id,
            "message": message.to_dict(),
            "model_id": result.model_id,
            "ai_generated": False,
            "fallback": True,
            "fallback_reason": result.fallback_reason,
            "fallback_chain": result.fallback_chain,
            "citations": citations,
            "review_notice": AI_REVIEW_NOTICE,
            "routing": routing,
        }

    content = f"{result.content}\n\n{AI_REVIEW_NOTICE}"
    message = chat_store.append_message(
        session,
        role="assistant",
        content=content,
        model_id=result.model_id,
        citations=citations,
        routing=routing,
    )
    return {
        "session_id": session.id,
        "message": message.to_dict(),
        "model_id": result.model_id,
        "ai_generated": True,
        "fallback": False,
        "fallback_reason": None,
        "fallback_chain": result.fallback_chain,
        "citations": citations,
        "review_notice": AI_REVIEW_NOTICE,
        "routing": routing,
    }
