# Knowledge Infrastructure

## Purpose

Embedding generation and storage for the vectorized
knowledge base (RD-03).

## Modules

- `embeddings.py` — `EmbeddingService` with two
  paths, both producing 384-dim L2-normalized
  vectors:
  1. Remote: HF Inference API
     (`sentence-transformers/all-MiniLM-L6-v2`)
  2. Deterministic fallback: feature hashing
     (word + bigram, signed buckets). Offline,
     deterministic, and captures lexical overlap so
     fallback retrieval stays relevant.
  Also provides `cosine_similarity`.
- `knowledge_store.py` — `KnowledgeStore` with two
  backends behind one interface:
  1. Supabase pgvector: writes to `knowledge_entries`
     and searches via the `knowledge_search` RPC
  2. In-memory cosine search (unconfigured mode and
     the fail-soft fallback when the remote path fails)

## Design

- The backend is selected at **call time** (not
  init) so tests can force in-memory mode by
  patching settings, matching the other stores.
- Writes and searches fail soft: a remote failure
  degrades to the in-memory copy, never to an error.

## Testing

- `tests/unit/test_knowledge_base.py` (embedding
  determinism, normalization, relevance)
- The autouse conftest fixture forces the
  deterministic embedding path (no network).

## Related Modules

- `app.domain.knowledge` — models and schemas
- `app.application.services.knowledge_base` — retrieval
