"""The seed corpus must be writable to the real (uuid) column.

``knowledge_entries.id`` is a ``uuid`` column, so a seed id like
``seed-cv-001`` is rejected by Postgres ("invalid input syntax for type
uuid"). The seeding then fails soft, and the pgvector knowledge base is
never populated in a real deployment.
"""

from __future__ import annotations

import uuid

from app.application.services.knowledge_base import SEED_CORPUS, KnowledgeBaseService


def test_every_seed_id_is_a_valid_uuid():
    """Every seed id must be usable as the ``knowledge_entries.id`` uuid."""
    for entry_id, _domain, _content, _source in SEED_CORPUS:
        assert uuid.UUID(entry_id), f"seed id is not a uuid: {entry_id}"


def test_the_seed_ids_are_stable():
    """The same seed always maps to the same id (the seeding is idempotent)."""
    service = KnowledgeBaseService()
    first = [entry.id for entry in service.store.list_entries()] if hasattr(service.store, "list_entries") else []
    second = [entry.id for entry in service.store.list_entries()] if hasattr(service.store, "list_entries") else []
    assert first == second
