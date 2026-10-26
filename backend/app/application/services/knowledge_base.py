"""Knowledge base service (RD-03).

Retrieval-augmented career guidance:

- Seeds a vectorized corpus covering CV best practices,
  cover-letter guidelines, career advice, HR
  recommendations, and country-specific application
  rules.
- Retrieves relevant snippets before AI generation,
  with source attribution and similarity scores.
- Applies safeguards: a relevance threshold, a
  ``top_k`` cap, and a context-character budget so
  retrieved context stays relevant and bounded.
- Falls back deterministically: embeddings degrade to
  feature hashing and storage degrades to in-memory
  cosine search, so retrieval never hard-fails.
- Retrieved guidance is reference-only: it is appended
  to generated documents under an explicit notice and
  never overrides user-provided facts.
"""

from __future__ import annotations

import logging

from app.application.services.context_budget import build_bounded_context
from app.application.services.document_generation import (
    generate_cover_letter_document,
    generate_cv_document,
    generate_resignation_letter_document,
)
from app.core.errors import ValidationError
from app.domain.knowledge.models import (
    KNOWLEDGE_DOMAINS,
    KnowledgeEntry,
)
from app.infrastructure.knowledge.embeddings import EmbeddingService
from app.infrastructure.knowledge.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

# Retrieval safeguards (RD-03 acceptance criteria).
MAX_TOP_K = 10
DEFAULT_TOP_K = 5
DEFAULT_MIN_SIMILARITY = 0.35
MAX_CONTEXT_CHARS = 4000

# Seed corpus. The ids are deterministic UUIDv5 values so the seeding is
# idempotent across restarts and so they fit the ``knowledge_entries.id``
# uuid column (a plain string id is rejected by Postgres).
SEED_CORPUS: tuple[tuple[str, str, str, str], ...] = (
    # (id, domain, content, source)
    (
        "4b8df5d3-3fc7-59cc-b57c-61be6877022d",
        "cv_best_practices",
        "Tailor the CV to each job description: mirror the keywords and requirements listed in the posting.",
        "career-knowledge-base:v1",
    ),
    (
        "7ef398ad-fd11-58b5-834b-f36a498cf4e6",
        "cv_best_practices",
        "Quantify achievements with numbers (percentages, revenue, team size) instead of vague responsibilities.",
        "career-knowledge-base:v1",
    ),
    (
        "957c999f-dc8b-59f6-a09a-40d6cafba3d2",
        "cv_best_practices",
        "Start bullet points with strong action verbs (led, built, shipped, reduced) rather than duty descriptions.",
        "career-knowledge-base:v1",
    ),
    (
        "2b42ce2b-601c-5797-947d-64f5b6a788aa",
        "cv_best_practices",
        "Keep formatting ATS-friendly: standard section headings, no tables or text boxes, common fonts.",
        "career-knowledge-base:v1",
    ),
    (
        "169c479a-8f05-582b-9427-d33a3c49d625",
        "cv_best_practices",
        "Limit the CV to one page for under ten years of experience; two pages maximum for senior roles.",
        "career-knowledge-base:v1",
    ),
    (
        "a9bd72bd-a281-5342-a7e0-3e60d12d30b7",
        "cover_letter_guidelines",
        "Open the cover letter with the exact role title and where you found the opening.",
        "career-knowledge-base:v1",
    ),
    (
        "225a77bb-594b-59df-b4a4-6cc948249456",
        "cover_letter_guidelines",
        "Match two or three job requirements to concrete examples from your experience in the body paragraphs.",
        "career-knowledge-base:v1",
    ),
    (
        "0b4f1283-7ef9-59a3-9edc-758fc57527d7",
        "cover_letter_guidelines",
        "Close with a clear call to action: an interview request and availability for follow-up.",
        "career-knowledge-base:v1",
    ),
    (
        "e2d37687-8f81-5076-a076-d45c9f4da1b5",
        "cover_letter_guidelines",
        "Address the hiring manager by name whenever the posting does not state 'confidential'.",
        "career-knowledge-base:v1",
    ),
    (
        "ade951b0-f13e-56e3-8b9e-4abbb31fdbbf",
        "career_advice",
        "Research the company's recent news, products, and mission before the interview.",
        "career-knowledge-base:v1",
    ),
    (
        "cfc04108-d30d-59a8-a253-38d09174f353",
        "career_advice",
        "Prepare STAR stories (Situation, Task, Action, Result) for behavioral interview questions.",
        "career-knowledge-base:v1",
    ),
    (
        "8034dc5d-2b57-53fe-a112-974486a263fc",
        "career_advice",
        "Network before applying: referrals dramatically increase interview callback rates.",
        "career-knowledge-base:v1",
    ),
    (
        "eb59a7bb-a2db-5166-a578-224b01276be5",
        "career_advice",
        "Follow up within 24 hours with a short thank-you note referencing a specific discussion point.",
        "career-knowledge-base:v1",
    ),
    (
        "4f6cfdea-1753-5dbb-8310-b4e2a89a037c",
        "hr_recommendations",
        "Recruiters spend only a few seconds on the initial CV scan, so put the most relevant facts first.",
        "career-knowledge-base:v1",
    ),
    (
        "70ea3112-be21-50b7-85dd-218bbc9663a8",
        "hr_recommendations",
        "Explain employment gaps briefly and positively: focus on what you learned or did during the gap.",
        "career-knowledge-base:v1",
    ),
    (
        "716e833a-d98e-5f1b-b99b-75abc86e049c",
        "hr_recommendations",
        "Align your summary with the job posting's language so both ATS and human reviewers see the fit.",
        "career-knowledge-base:v1",
    ),
    (
        "e9569849-df19-5a76-acad-4e5a83c1f339",
        "hr_recommendations",
        "Never fabricate experience or credentials; verification failures end most hiring processes.",
        "career-knowledge-base:v1",
    ),
    (
        "9b831f67-94f4-5836-a278-77dd728be9a1",
        "country_rules",
        "Germany: follow DIN 5008 for formal letters; CVs traditionally include a "
        "professional photo (optional since 2024 AGG guidance) and exclude age, "
        "marital status, and religion.",
        "din-5008:2024",
    ),
    (
        "c030c01b-d929-5daa-b94f-f58e239e6ee1",
        "country_rules",
        "Germany: applications (Bewerbung) typically include a cover letter "
        "(Anschreiben), CV (Lebenslauf), and certificates (Zeugnisse).",
        "din-5008:2024",
    ),
    (
        "9e9d985d-7946-5705-aac1-8f20b625bd50",
        "country_rules",
        "France: a professional photo is common on CVs; keep the document to one "
        "page and include date of birth only if comfortable.",
        "career-knowledge-base:v1",
    ),
    (
        "f182dbcd-330c-5488-ab0d-f70b1aa0999b",
        "country_rules",
        "France: letters often close with the formal formula 'Je vous prie "
        "d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.'",
        "career-knowledge-base:v1",
    ),
    (
        "164bd04d-899d-5146-b869-39ae1b5b8ffe",
        "country_rules",
        "United States: no photo, no age, no marital status; one page for "
        "early-career candidates; include a brief summary instead of an objective.",
        "career-knowledge-base:v1",
    ),
    (
        "bd0329a9-8472-536e-8c95-83e008028931",
        "country_rules",
        "United States: salary history is prohibited in many states; never include "
        "it unless explicitly requested where legal.",
        "career-knowledge-base:v1",
    ),
    (
        "2e6283bb-bf16-5e32-84a8-1ff1fa07add7",
        "country_rules",
        "Netherlands: CVs commonly include personal details (date of birth, "
        "nationality) and a professional photo is optional.",
        "career-knowledge-base:v1",
    ),
    (
        "46f6ea64-4bf8-5390-b557-0d546c3d5563",
        "country_rules",
        "Netherlands: cover letters are typically short (three to four paragraphs) " "and direct in tone.",
        "career-knowledge-base:v1",
    ),
)


class KnowledgeBaseService:
    """Vectorized career knowledge base with RAG retrieval."""

    def __init__(
        self,
        store: KnowledgeStore | None = None,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        self.store = store or KnowledgeStore()
        self.embeddings = embeddings or EmbeddingService()
        if self.store.is_empty():
            self._seed()

    # -- ingestion ----------------------------------------------------

    def _seed(self) -> None:
        for entry_id, domain, content, source in SEED_CORPUS:
            self.ingest(
                domain=domain,
                content=content,
                source=source,
                metadata={"seeded": True},
                entry_id=entry_id,
            )

    def ingest(
        self,
        domain: str,
        content: str,
        source: str = "community-contribution",
        metadata: dict | None = None,
        entry_id: str | None = None,
    ) -> KnowledgeEntry:
        """Add one knowledge entry with its embedding."""
        if domain not in KNOWLEDGE_DOMAINS:
            raise ValidationError(f"domain must be one of: {', '.join(KNOWLEDGE_DOMAINS)}")
        if not content.strip():
            raise ValidationError("content must not be empty.")

        entry = KnowledgeEntry(
            id=entry_id or self.store.new_id(),
            domain=domain,
            content=content.strip(),
            source=source.strip() or "community-contribution",
            embedding=self.embeddings.embed_one(content),
            metadata=metadata or {},
        )
        return self.store.add(entry)

    # -- retrieval ------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        domain: str | None = None,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> list[dict]:
        """Retrieve relevant knowledge snippets with attribution.

        Safeguards applied here:
        - ``top_k`` is capped at ``MAX_TOP_K``
        - ``min_similarity`` filters irrelevant snippets
        - every result carries ``source`` and ``similarity``
        """
        if not query.strip():
            raise ValidationError("query must not be empty.")
        if domain is not None and domain not in KNOWLEDGE_DOMAINS:
            raise ValidationError(f"domain must be one of: {', '.join(KNOWLEDGE_DOMAINS)}")

        capped_top_k = max(1, min(int(top_k), MAX_TOP_K))
        query_embedding = self.embeddings.embed_one(query)
        matches = self.store.search(
            query_embedding,
            top_k=capped_top_k,
            domain=domain,
            min_similarity=min_similarity,
        )

        return [
            {
                "id": entry.id,
                "domain": entry.domain,
                "content": entry.content,
                "source": entry.source,
                "similarity": round(similarity, 4),
                "metadata": entry.metadata,
            }
            for entry, similarity in matches
        ]

    def retrieve_for_generation(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        domain: str | None = None,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> dict:
        """Build bounded, source-attributed guidance context.

        Returns ``{context, sources, used_fallback}``. The
        context is capped at ``MAX_CONTEXT_CHARS`` so
        retrieved knowledge can never flood a prompt
        (safeguard against excessive context). If retrieval
        itself fails, the caller gets an empty context with
        ``used_fallback=True`` (deterministic fallback).
        """
        try:
            results = self.search(
                query=query,
                top_k=top_k,
                domain=domain,
                min_similarity=min_similarity,
            )
        except Exception as exc:  # noqa: BLE001 — fail-soft
            logger.warning("knowledge.retrieval.failed: %s", exc)
            return {"context": "", "sources": [], "used_fallback": True}

        sources = [
            {
                "entry_id": item["id"],
                "source": item["source"],
                "domain": item["domain"],
                "similarity": item["similarity"],
            }
            for item in results
        ]

        return {
            "context": build_bounded_context(
                results,
                MAX_CONTEXT_CHARS,
                attribution=lambda item: (
                    f"[Source: {item['source']} | {item['domain']} | " f"{item['similarity']:.2f}]"
                ),
            ),
            "sources": sources,
            "used_fallback": False,
        }


_knowledge_base: KnowledgeBaseService | None = None


def get_knowledge_base() -> KnowledgeBaseService:
    """Lazy singleton: seeding happens on first use, not at
    import, so importing the app never triggers network
    calls (tests patch settings before first use)."""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBaseService()
    return _knowledge_base


def __getattr__(name: str):
    # Backwards-compatible lazy access to the singleton.
    if name == "knowledge_base":
        return get_knowledge_base()
    raise AttributeError(name)


# Re-exported so callers can generate grounded documents
# without importing the generation module directly. The
# generation functions accept ``knowledge_context`` and
# append it under an explicit reference-only notice.
__all__ = [
    "DEFAULT_MIN_SIMILARITY",
    "DEFAULT_TOP_K",
    "MAX_CONTEXT_CHARS",
    "MAX_TOP_K",
    "KnowledgeBaseService",
    "SEED_CORPUS",
    "get_knowledge_base",
    "generate_cv_document",
    "generate_cover_letter_document",
    "generate_resignation_letter_document",
]
