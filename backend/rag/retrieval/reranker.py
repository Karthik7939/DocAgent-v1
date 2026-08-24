"""
Cross-encoder reranking for hybrid retrieval results.

RRF fusion (see hybrid_retriever.py) merges channels by rank position only —
each channel's raw score (cosine similarity, BM25, dependency-hop) is
discarded after fusion, since the three are on incomparable scales. That
means the fused list has no real judge of relevance, only "how early did
this show up across channels."

Verified live against an indexed repository: a broad legitimate query
("project purpose architecture main core system...") and a nonsense query
("quantum blockchain xyzabc123") both produced full result sets once the
pre-fusion similarity floor was lowered enough to stop starving the
legitimate query — no single per-channel threshold value distinguished
signal from noise for either. CrossEncoderReranker scores each
(query, chunk) pair directly, giving an actual relevance judgment to sort
by before truncating to the final top_k.
"""

from __future__ import annotations

import math
from typing import Optional

from rag.config import settings
from rag.schemas.retrieval import RetrievalResult
from rag.utils import get_logger

logger = get_logger(__name__)


class CrossEncoderReranker:
    """
    Reranks a candidate pool of RetrievalResults by actual query relevance.

    Lazily loads a small local cross-encoder model on first use. Failures
    to load or score are non-fatal: rerank() falls back to the incoming
    (RRF) order, truncated to top_k, rather than raising — matching how the
    rest of the RAG pipeline treats optional-enhancement failures (e.g.
    RAGService topic retrieval, SemanticQueryRefiner).
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self._model_name = model_name or settings.rerank_model
        self._model = None
        self._load_failed = False

    def _load_model(self):
        if self._model is not None or self._load_failed:
            return self._model

        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            logger.warning(
                "Reranking disabled: sentence-transformers is not installed (%s).",
                exc,
            )
            self._load_failed = True
            return None

        try:
            logger.info("Loading cross-encoder reranker model '%s'.", self._model_name)
            self._model = CrossEncoder(self._model_name)
        except Exception as exc:
            logger.warning(
                "Reranking disabled: failed to load cross-encoder model '%s': %s",
                self._model_name, exc,
            )
            self._load_failed = True
            return None

        return self._model

    def rerank(
        self,
        query_text: str,
        candidates: list[RetrievalResult],
        top_k: int,
    ) -> Optional[list[RetrievalResult]]:
        """
        Score every candidate against the query and return the top_k,
        reranked by actual relevance instead of RRF rank position.

        Args:
            query_text: The retrieval query's text.
            candidates: RRF-fused candidate pool, already in rank order.
            top_k:      Final number of results to return.

        Returns:
            Optional[list[RetrievalResult]]: `None` means reranking did not
            actually run (model unavailable, or scoring failed) — callers
            should fall back to the pre-rerank order in that case. A list
            (possibly empty) means reranking DID run: an empty list is a
            genuine "no candidate was relevant enough" result and must
            NOT be treated as a failure to fall back from.
        """
        if not candidates:
            return []

        model = self._load_model()
        if model is None:
            return None

        pairs = [(query_text, c.chunk.content) for c in candidates]

        try:
            raw_scores = model.predict(pairs)
        except Exception as exc:
            logger.warning("Reranking failed, falling back to RRF order: %s", exc)
            return None

        # Cross-encoder logits are unbounded and can be negative, but
        # RetrievalResult.similarity_score requires >= 0.0 (and a bounded
        # score is more meaningful downstream anyway). Sigmoid squashes to
        # (0, 1) while preserving rank order — it's a monotonic transform,
        # so it can't change which candidates rank above which.
        #
        # NOTE — no absolute score cutoff is applied here, deliberately.
        # An earlier version of this method filtered out any candidate
        # scoring below a fixed threshold (rerank_min_score). That was
        # verified live to be wrong: this model (ms-marco-MiniLM-L-6-v2,
        # trained on short, natural search queries) produces uniformly very
        # negative, low-confidence scores for this system's long,
        # multi-topic keyword-bag queries — genuinely relevant chunks
        # scored sigmoid ~0.00001-0.00007, indistinguishable in absolute
        # terms from irrelevant ones. Only the *relative* ordering within
        # a batch carries signal for these query styles; an absolute floor
        # would silently discard correct results. Ranking still improves
        # on plain RRF (which uses rank position only, with zero relevance
        # signal at all), but doesn't reject a fully irrelevant query the
        # way an absolute cutoff would if the model's scores were
        # well-calibrated for this query style. See rag_fix_plan.md P1.3 —
        # tightening the actual query text is the more durable fix for
        # that remaining gap.
        scored = [
            (candidate, 1.0 / (1.0 + math.exp(-float(score))))
            for candidate, score in zip(candidates, raw_scores)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        reranked: list[RetrievalResult] = []
        for index, (candidate, score) in enumerate(scored[:top_k], start=1):
            reranked.append(
                candidate.model_copy(
                    update={
                        "rank": index,
                        "similarity_score": score,
                        "retrieval_reason": (
                            f"{candidate.retrieval_reason} "
                            f"Reranked by cross-encoder (score={score:.3f})."
                        ),
                    },
                ),
            )
        return reranked
