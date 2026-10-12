"""Embedding generation for the knowledge base (RD-03).

Two paths, both producing ``EMBEDDING_DIMENSION``-dimensional,
L2-normalized vectors:

1. Remote: Hugging Face Inference API with
   ``sentence-transformers/all-MiniLM-L6-v2`` (Apache-2.0).
2. Deterministic fallback: feature hashing (word + bigram
   hashing with signed buckets). No network, fully
   deterministic, and captures lexical overlap so retrieval
   stays relevant when the provider is unavailable.

The service never raises for embedding failures — it always
returns a usable vector (fail-soft by design).
"""

from __future__ import annotations

import hashlib
import math
import os
import re

from app.domain.knowledge.models import EMBEDDING_DIMENSION

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def deterministic_embedding(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    """Feature-hashing embedding: deterministic and offline.

    Words and bigrams are hashed into signed buckets, then the
    vector is L2-normalized. Texts sharing vocabulary produce
    higher cosine similarity, which keeps fallback retrieval
    relevant without any network call.
    """
    vector = [0.0] * dimension
    tokens = _tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0

    for first, second in zip(tokens, tokens[1:]):
        digest = hashlib.sha256(f"{first} {second}".encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        vector[index] += 0.5 * (1.0 if digest[4] % 2 == 0 else -1.0)

    norm = math.sqrt(sum(value * value for value in vector))
    if norm > 0:
        vector = [value / norm for value in vector]
    return vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


class EmbeddingService:
    """Generate embeddings with a deterministic fallback."""

    MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed every text; falls back to hashing per text."""
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> list[float]:
        try:
            return self._embed_remote(text)
        except Exception:
            # Fail-soft: the deterministic embedding keeps
            # retrieval working offline and in tests.
            return deterministic_embedding(text, self.dimension)

    def _embed_remote(self, text: str) -> list[float]:
        token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
        if not token:
            raise RuntimeError("HF_TOKEN is not configured.")

        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is not installed.") from exc

        client = InferenceClient(model=self.MODEL_ID, token=token, timeout=30.0)
        raw = client.feature_extraction(text)
        vector = self._flatten(raw)
        if len(vector) != self.dimension:
            raise ValueError(f"Provider returned {len(vector)} dimensions, expected {self.dimension}.")
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            raise ValueError("Provider returned a zero vector.")
        return [value / norm for value in vector]

    @staticmethod
    def _flatten(raw: object) -> list[float]:
        """Normalize the provider's nested-list response."""
        if isinstance(raw, (int, float)):
            return [float(raw)]
        if isinstance(raw, (list, tuple)):
            flat: list[float] = []
            for item in raw:
                flat.extend(EmbeddingService._flatten(item))
            return flat
        raise ValueError(f"Unexpected embedding payload: {type(raw)!r}")
