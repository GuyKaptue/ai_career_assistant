"""Semantic job matching with embeddings (RD-04).

Combines embedding cosine similarity with the existing
ATS keyword scoring (BE-03) into a single, explainable
ranking:

    combined = W_SEMANTIC * S_semantic + W_ATS * S_ats_keyword

Explainability: the job description is split into
concepts (sentences), each embedded and scored against
the candidate, so the top matching skills and concepts
are exposed with their similarity.

Fallback: the existing ATS scoring is always computed
and remains available; if embedding fails, the result
degrades to pure ATS scoring (semantic fields null).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.application.services.ats_checker import (
    _compute_keyword_score,
    check_resume_against_job,
)
from app.infrastructure.knowledge.embeddings import (
    EmbeddingService,
    cosine_similarity,
)

logger = logging.getLogger(__name__)

# Combination weights (RD-04). Semantic and ATS keyword
# contribute equally to the combined ranking score.
WEIGHT_SEMANTIC = 0.5
WEIGHT_ATS_KEYWORD = 0.5

# Explainability: how many top concepts are exposed.
MAX_CONCEPTS = 5

# Minimum similarity for a concept to be reported as a match.
CONCEPT_SIMILARITY_THRESHOLD = 0.10

_SENTENCE_SPLIT = re.compile(r"[.!?]+")


def _split_concepts(text: str) -> list[str]:
    """Split text into concepts (sentences/phrases)."""
    sentences = _SENTENCE_SPLIT.split(text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


@dataclass
class SemanticMatch:
    """Semantic matching result with concept-level evidence."""

    semantic_score: float  # [0, 100]
    matched_concepts: tuple[str, ...]
    concept_details: list[dict] = field(default_factory=list)


class SemanticMatchingService:
    """Embedding-based candidate/job matching."""

    def __init__(self, embeddings: EmbeddingService | None = None) -> None:
        self.embeddings = embeddings or EmbeddingService()

    def semantic_match(
        self,
        candidate_text: str,
        job_description: str,
    ) -> SemanticMatch:
        """Compute the semantic similarity and matching concepts.

        The semantic score is the cosine similarity between
        the candidate and job-description embeddings, scaled
        to [0, 100]. Matching concepts are job-description
        sentences whose embedding is closest to the candidate.
        """
        if not candidate_text.strip() or not job_description.strip():
            return SemanticMatch(
                semantic_score=0.0,
                matched_concepts=(),
                concept_details=[],
            )

        candidate_embedding = self.embeddings.embed_one(candidate_text)
        job_embedding = self.embeddings.embed_one(job_description)
        similarity = cosine_similarity(candidate_embedding, job_embedding)
        semantic_score = max(0.0, min(100.0, similarity * 100.0))

        # Concept-level explainability: score each job-description
        # concept against the candidate embedding.
        concept_details: list[dict] = []
        for concept in _split_concepts(job_description):
            concept_embedding = self.embeddings.embed_one(concept)
            concept_similarity = cosine_similarity(candidate_embedding, concept_embedding)
            if concept_similarity >= CONCEPT_SIMILARITY_THRESHOLD:
                concept_details.append(
                    {
                        "concept": concept,
                        "similarity": round(concept_similarity, 4),
                    }
                )

        concept_details.sort(key=lambda item: item["similarity"], reverse=True)
        concept_details = concept_details[:MAX_CONCEPTS]
        matched_concepts = tuple(item["concept"] for item in concept_details)

        return SemanticMatch(
            semantic_score=round(semantic_score, 4),
            matched_concepts=matched_concepts,
            concept_details=concept_details,
        )

    def rank_jobs(
        self,
        candidate_text: str,
        jobs: list[dict],
        top_k: int = 10,
    ) -> list[dict]:
        """Rank jobs by combined semantic + ATS keyword score.

        Each job is annotated with ``semantic_score``,
        ``ats_keyword_score``, ``combined_score`` and
        ``matched_concepts`` so the ranking is transparent.
        """
        if not candidate_text.strip():
            return list(jobs)

        ranked: list[dict] = []
        for job in jobs:
            job_text = " ".join(
                str(job.get(field) or "") for field in ("title", "company", "location", "description")
            ).strip()
            semantic = self.semantic_match(candidate_text, job_text)
            keyword_score, _matched, _missing = _compute_keyword_score(candidate_text, job_text)
            combined = WEIGHT_SEMANTIC * semantic.semantic_score + WEIGHT_ATS_KEYWORD * keyword_score
            ranked.append(
                {
                    **job,
                    "semantic_score": int(round(semantic.semantic_score)),
                    "ats_keyword_score": int(round(keyword_score)),
                    "combined_score": int(round(combined)),
                    "matched_concepts": list(semantic.matched_concepts),
                }
            )

        ranked.sort(key=lambda item: item["combined_score"], reverse=True)
        return ranked[: max(0, min(top_k, len(ranked)))]


def check_resume_semantic(
    resume_text: str,
    job_description: str,
    ats_result: dict | None = None,
    matching: SemanticMatchingService | None = None,
) -> dict:
    """Combine semantic matching with the existing ATS score.

    Returns the semantic score, the ATS keyword score, the
    combined ranking score, and the matching concepts. The
    existing ATS scoring is the fallback: if semantic
    matching fails, the combined score equals the ATS score
    and ``semantic_fallback`` is set.
    """
    if ats_result is None:
        ats_result = check_resume_against_job(resume_text, job_description)

    # ATS keyword score is the keyword_overlap ratio scaled
    # to [0, 100] (identical to the ATS keyword sub-score).
    keyword_score = float(ats_result.get("keyword_overlap", 0.0)) * 100.0

    try:
        service = matching or SemanticMatchingService()
        semantic = service.semantic_match(resume_text, job_description)
    except Exception as exc:  # noqa: BLE001 — ATS fallback
        logger.warning("semantic.matching.failed: %s", exc)
        return {
            "semantic_score": None,
            "ats_keyword_score": int(round(keyword_score)),
            "combined_score": ats_result.get("score"),
            "matched_concepts": [],
            "concept_details": [],
            "semantic_fallback": True,
            "semantic_explanation": (
                "Semantic matching unavailable; combined score " "uses the ATS keyword score only."
            ),
        }

    combined = WEIGHT_SEMANTIC * semantic.semantic_score + WEIGHT_ATS_KEYWORD * keyword_score

    return {
        "semantic_score": int(round(semantic.semantic_score)),
        "ats_keyword_score": int(round(keyword_score)),
        "combined_score": int(round(combined)),
        "matched_concepts": list(semantic.matched_concepts),
        "concept_details": semantic.concept_details,
        "semantic_fallback": False,
        "semantic_explanation": (
            f"Combined {combined:.0f}/100 = "
            f"{WEIGHT_SEMANTIC:.0%}×semantic({semantic.semantic_score:.0f}) + "
            f"{WEIGHT_ATS_KEYWORD:.0%}×ats_keyword({keyword_score:.0f}). "
            f"Top concepts: {', '.join(semantic.matched_concepts[:3]) or 'none'}."
        ),
    }


semantic_matching = SemanticMatchingService()
