# Knowledge Domain

## Purpose

Vectorized career knowledge base (RD-03): CV best
practices, cover-letter guidelines, career advice,
HR recommendations, and country-specific application
rules. Entries are domain-tagged so new knowledge
domains are added as data, not prompt code.

## Public API

- `KnowledgeEntry` — one retrievable snippet with
  its embedding, source, and metadata
- `KNOWLEDGE_DOMAINS` — canonical domain tuple
- `EMBEDDING_DIMENSION` — 384 (matches
  sentence-transformers/all-MiniLM-L6-v2)

## Schemas

- `KnowledgeSearchPayload` — query, domain filter,
  top_k (1–10), min_similarity (0–1)
- `KnowledgeIngestPayload` — domain, content, source
- `KnowledgeSearchResultItem` — result with
  `source` and `similarity` attribution

## Security

- `to_public_dict()` never exposes the raw embedding
- Ingestion is authenticated; search is public

## Testing

- `tests/unit/test_knowledge_base.py`
- `tests/api/test_knowledge.py`
- `tests/contract/test_migrations.py` (TestKnowledgeBase)

## Related Modules

- `app.infrastructure.knowledge` — embeddings + store
- `app.application.services.knowledge_base` — retrieval
- `supabase/migrations/20261008000000_knowledge_base.sql`
