"""
Hybrid retrieval orchestrator.

This module merges dense vector search, BM25 keyword search, and
dependency-based retrieval using Reciprocal Rank Fusion (RRF).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from rag.config import settings
from rag.embeddings.embedder import Embedder
from rag.retrieval.dependency_retriever import DependencyRetriever
from rag.retrieval.keyword_store import KeywordStore
from rag.retrieval.metadata_filter import MetadataFilter
from rag.retrieval.vector_store import VectorStore
from rag.schemas.chunk import Chunk
from rag.schemas.query import SemanticQuery
from rag.schemas.retrieval import (
    RetrievalResult,
    RetrievalResults,
    RetrievalSource,
)
from rag.utils import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class HybridRetrieverStatistics:
    """
    Runtime statistics for hybrid retrieval.
    """

    faiss_results: int = 0
    bm25_results: int = 0
    dependency_results: int = 0
    merged_results: int = 0
    retrieval_time_ms: float = 0.0
    channel_failures: list[str] = field(default_factory=list)


class HybridRetriever:
    """
    Merge vector, keyword, and dependency retrieval into one ranked list.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        keyword_store: KeywordStore,
        dependency_retriever: DependencyRetriever,
        metadata_filter: MetadataFilter | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._keyword_store = keyword_store
        self._dependency_retriever = dependency_retriever
        self._metadata_filter = metadata_filter or MetadataFilter()
        self._embedder = embedder
        self._stats = HybridRetrieverStatistics()

    def retrieve(
        self,
        query: SemanticQuery,
        *,
        query_vector: Optional[list[float]] = None,
    ) -> RetrievalResults:
        """
        Execute hybrid retrieval for a semantic query.
        """
        start = time.perf_counter()
        top_k = query.top_k or settings.top_k
        channel_results = self._collect_channel_results(
            query,
            query_vector=query_vector,
            top_k=top_k,
        )
        merged = self.rank(
            channel_results,
            query=query,
            top_k=top_k,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._stats.retrieval_time_ms = elapsed_ms
        self._stats.merged_results = len(merged)

        return RetrievalResults(
            results=merged,
            retrieval_time_ms=elapsed_ms,
        )

    def retrieve_for_change(
        self,
        query: SemanticQuery,
        *,
        query_vector: Optional[list[float]] = None,
    ) -> RetrievalResults:
        """
        Retrieve context for a code change event.

        This emphasizes changed files, modified symbols, and dependency
        expansion around the commit delta.
        """
        if not query.dependency_files and query.changed_files:
            query = query.model_copy(
                update={"dependency_files": list(query.changed_files)},
            )

        return self.retrieve(query, query_vector=query_vector)

    def rrf(
        self,
        ranked_lists: dict[RetrievalSource, list[RetrievalResult]],
        *,
        rrf_k: Optional[int] = None,
    ) -> list[RetrievalResult]:
        """
        Merge ranked result lists using Reciprocal Rank Fusion.
        """
        constant = rrf_k or settings.rrf_k
        fused_scores: dict[str, float] = {}
        best_result: dict[str, RetrievalResult] = {}

        for source, results in ranked_lists.items():
            for rank, result in enumerate(results, start=1):
                chunk_id = result.chunk_id
                fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (
                    1.0 / (constant + rank)
                )

                current_best = best_result.get(chunk_id)
                if (
                    current_best is None
                    or result.similarity_score > current_best.similarity_score
                ):
                    best_result[chunk_id] = result

        ordered_chunk_ids = sorted(
            fused_scores.keys(),
            key=lambda chunk_id: fused_scores[chunk_id],
            reverse=True,
        )

        merged: list[RetrievalResult] = []

        for rank, chunk_id in enumerate(ordered_chunk_ids, start=1):
            base = best_result[chunk_id]
            merged.append(
                RetrievalResult(
                    chunk=base.chunk,
                    similarity_score=fused_scores[chunk_id],
                    rank=rank,
                    retrieval_source=RetrievalSource.HYBRID,
                    retrieval_reason=(
                        "Reciprocal Rank Fusion across vector, keyword, "
                        "and dependency retrieval."
                    ),
                ),
            )

        return merged

    def merge(
        self,
        ranked_lists: dict[RetrievalSource, list[RetrievalResult]],
        *,
        query: Optional[SemanticQuery] = None,
    ) -> list[RetrievalResult]:
        """
        Filter channel results and merge them with RRF.
        """
        filtered_lists: dict[RetrievalSource, list[RetrievalResult]] = {}

        for source, results in ranked_lists.items():
            filtered_lists[source] = self._metadata_filter.filter(
                results,
                query=query,
            )

        return self.rrf(filtered_lists)

    def rank(
        self,
        ranked_lists: dict[RetrievalSource, list[RetrievalResult]],
        *,
        query: Optional[SemanticQuery] = None,
        top_k: Optional[int] = None,
    ) -> list[RetrievalResult]:
        """
        Merge, rank, and trim hybrid retrieval results.
        """
        merged = self.merge(ranked_lists, query=query)
        limit = top_k or settings.top_k

        for index, result in enumerate(merged[:limit], start=1):
            merged[index - 1] = result.model_copy(update={"rank": index})

        return merged[:limit]

    def statistics(self) -> HybridRetrieverStatistics:
        """
        Return hybrid retrieval statistics.
        """
        return self._stats

    def _collect_channel_results(
        self,
        query: SemanticQuery,
        *,
        query_vector: Optional[list[float]],
        top_k: int,
    ) -> dict[RetrievalSource, list[RetrievalResult]]:
        results: dict[RetrievalSource, list[RetrievalResult]] = {
            RetrievalSource.FAISS: [],
            RetrievalSource.BM25: [],
            RetrievalSource.DEPENDENCY: [],
        }

        self._sync_dependency_chunks()

        vector = query_vector or self._embed_query(query)
        results[RetrievalSource.FAISS] = self._search_vector(
            query,
            vector,
            top_k,
        )
        results[RetrievalSource.BM25] = self._search_keywords(query, top_k)
        results[RetrievalSource.DEPENDENCY] = self._search_dependency(
            query,
            top_k,
        )

        self._stats.faiss_results = len(results[RetrievalSource.FAISS])
        self._stats.bm25_results = len(results[RetrievalSource.BM25])
        self._stats.dependency_results = len(
            results[RetrievalSource.DEPENDENCY],
        )

        return results

    def _search_vector(
        self,
        query: SemanticQuery,
        query_vector: Optional[list[float]],
        top_k: int,
    ) -> list[RetrievalResult]:
        if query_vector is None:
            return []

        try:
            hits = self._vector_store.search(
                query_vector,
                top_k=top_k,
                similarity_threshold=query.similarity_threshold,
            )
        except Exception as exc:
            logger.warning("Vector retrieval failed: %s", exc)
            self._stats.channel_failures.append("faiss")
            return []

        return [
            RetrievalResult(
                chunk=hit.chunk,
                similarity_score=hit.score,
                rank=index,
                retrieval_source=RetrievalSource.FAISS,
                retrieval_reason="Dense vector similarity match.",
            )
            for index, hit in enumerate(hits, start=1)
        ]

    def _search_keywords(
        self,
        query: SemanticQuery,
        top_k: int,
    ) -> list[RetrievalResult]:
        keyword_query = " ".join(
            [
                query.query_text,
                *query.keywords,
                *query.modified_symbols,
            ],
        ).strip()

        if not keyword_query:
            return []

        try:
            hits = self._keyword_store.search(
                keyword_query,
                top_k=top_k,
                keywords=query.keywords,
            )
        except Exception as exc:
            logger.warning("BM25 retrieval failed: %s", exc)
            self._stats.channel_failures.append("bm25")
            return []

        if not hits:
            return []

        max_score = max(hit.score for hit in hits) or 1.0

        return [
            RetrievalResult(
                chunk=hit.chunk,
                similarity_score=hit.score / max_score,
                rank=index,
                retrieval_source=RetrievalSource.BM25,
                retrieval_reason="BM25 keyword match.",
            )
            for index, hit in enumerate(hits, start=1)
        ]

    def _search_dependency(
        self,
        query: SemanticQuery,
        top_k: int,
    ) -> list[RetrievalResult]:
        seed_files = query.dependency_files or query.changed_files

        if not seed_files:
            return []

        try:
            hits = self._dependency_retriever.affected_chunks(seed_files)
        except Exception as exc:
            logger.warning("Dependency retrieval failed: %s", exc)
            self._stats.channel_failures.append("dependency")
            return []

        hits = hits[:top_k]

        return [
            RetrievalResult(
                chunk=hit.chunk,
                similarity_score=hit.score,
                rank=index,
                retrieval_source=RetrievalSource.DEPENDENCY,
                retrieval_reason=hit.reason,
            )
            for index, hit in enumerate(hits, start=1)
        ]

    def _embed_query(
        self,
        query: SemanticQuery,
    ) -> Optional[list[float]]:
        if self._embedder is None:
            return None

        try:
            return self._embedder.embed_text(query.query_text)
        except Exception as exc:
            logger.warning("Failed to embed retrieval query: %s", exc)
            self._stats.channel_failures.append("embedder")
            return None

    def _sync_dependency_chunks(self) -> None:
        """
        Refresh the dependency retriever's file-to-chunk registry.
        """
        chunks_by_file = self._build_chunks_by_file(
            self._vector_store.get_all_active_chunks(),
        )

        if not chunks_by_file:
            chunks_by_file = self._build_chunks_by_file(
                self._keyword_store.get_all_active_chunks(),
            )

        self._dependency_retriever.set_chunks_by_file(chunks_by_file)

    @staticmethod
    def _build_chunks_by_file(
        chunks: list[Chunk],
    ) -> dict[str, list[Chunk]]:
        grouped: dict[str, list[Chunk]] = {}

        for chunk in chunks:
            grouped.setdefault(chunk.metadata.file_path, []).append(chunk)

        return grouped
