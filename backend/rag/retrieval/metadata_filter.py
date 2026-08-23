"""
Metadata filtering utilities for retrieval candidates.

This module removes inactive, duplicate, or irrelevant chunks from
multi-channel retrieval results before hybrid ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from rag.schemas.chunk import Chunk, ChunkType
from rag.schemas.query import SemanticQuery
from rag.schemas.retrieval import RetrievalResult, RetrievalSource
from rag.utils import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class MetadataFilterStatistics:
    """
    Statistics for metadata filtering.
    """

    input_count: int = 0
    output_count: int = 0
    removed_inactive: int = 0
    removed_duplicates: int = 0
    removed_threshold: int = 0
    removed_metadata: int = 0


class MetadataFilter:
    """
    Filter and deduplicate retrieval candidates using chunk metadata.
    """

    def __init__(self) -> None:
        self._stats = MetadataFilterStatistics()

    def filter(
        self,
        results: Iterable[RetrievalResult],
        query: Optional[SemanticQuery] = None,
        *,
        similarity_threshold: Optional[float] = None,
    ) -> list[RetrievalResult]:
        """
        Apply the full metadata filtering pipeline.
        """
        filtered = list(results)
        self._stats = MetadataFilterStatistics(input_count=len(filtered))

        filtered = self.filter_active(filtered)
        filtered = self.deduplicate(filtered)

        if query is not None:
            filtered = self.filter_repository(filtered, query.repository)
            filtered = self.filter_language(filtered, query.languages)
            filtered = self._apply_metadata_filters(
                filtered,
                query.metadata_filters,
            )

        threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else (query.similarity_threshold if query else None)
        )

        if threshold is not None:
            filtered = self.filter_similarity(filtered, threshold)

        self._stats.output_count = len(filtered)
        return filtered

    def deduplicate(
        self,
        results: Iterable[RetrievalResult],
    ) -> list[RetrievalResult]:
        """
        Keep the highest-scoring result for each chunk ID.
        """
        best_by_chunk: dict[str, RetrievalResult] = {}

        for result in results:
            chunk_id = result.chunk_id
            existing = best_by_chunk.get(chunk_id)

            if existing is None:
                best_by_chunk[chunk_id] = result
                continue

            if result.similarity_score > existing.similarity_score:
                best_by_chunk[chunk_id] = result
            else:
                self._stats.removed_duplicates += 1

        return list(best_by_chunk.values())

    def filter_active(
        self,
        results: Iterable[RetrievalResult],
    ) -> list[RetrievalResult]:
        """
        Remove inactive or empty chunks.
        """
        filtered: list[RetrievalResult] = []

        for result in results:
            if not result.chunk.metadata.active:
                self._stats.removed_inactive += 1
                continue

            if not result.chunk.content.strip():
                self._stats.removed_inactive += 1
                continue

            filtered.append(result)

        return filtered

    def filter_language(
        self,
        results: Iterable[RetrievalResult],
        languages: list[str],
    ) -> list[RetrievalResult]:
        """
        Keep only chunks whose language is in the allowed list.
        """
        if not languages:
            return list(results)

        allowed = {language.lower() for language in languages}
        filtered: list[RetrievalResult] = []

        for result in results:
            if result.chunk.metadata.language.lower() in allowed:
                filtered.append(result)
            else:
                self._stats.removed_metadata += 1

        return filtered

    def filter_repository(
        self,
        results: Iterable[RetrievalResult],
        repository: str,
    ) -> list[RetrievalResult]:
        """
        Keep only chunks belonging to one repository.
        """
        filtered: list[RetrievalResult] = []

        for result in results:
            if result.chunk.metadata.repository == repository:
                filtered.append(result)
            else:
                self._stats.removed_metadata += 1

        return filtered

    def filter_similarity(
        self,
        results: Iterable[RetrievalResult],
        threshold: float,
    ) -> list[RetrievalResult]:
        """
        Remove results below a similarity threshold.

        Dependency and BM25 scores use the same cutoff heuristically.
        """
        filtered: list[RetrievalResult] = []

        for result in results:
            if result.similarity_score >= threshold:
                filtered.append(result)
            else:
                self._stats.removed_threshold += 1

        return filtered

    def filter_chunk_type(
        self,
        results: Iterable[RetrievalResult],
        chunk_type: ChunkType,
    ) -> list[RetrievalResult]:
        """
        Keep only chunks of one type.
        """
        return [
            result
            for result in results
            if result.chunk.metadata.chunk_type == chunk_type
        ]

    def filter_file_paths(
        self,
        results: Iterable[RetrievalResult],
        file_paths: set[str],
    ) -> list[RetrievalResult]:
        """
        Keep only chunks from the specified file paths.
        """
        return [
            result
            for result in results
            if result.chunk.metadata.file_path in file_paths
        ]

    def statistics(self) -> MetadataFilterStatistics:
        """
        Return metadata filtering statistics.
        """
        return self._stats

    @staticmethod
    def _apply_metadata_filters(
        results: Iterable[RetrievalResult],
        metadata_filters: dict[str, str],
    ) -> list[RetrievalResult]:
        if not metadata_filters:
            return list(results)

        filtered: list[RetrievalResult] = []

        for result in results:
            metadata = result.chunk.metadata
            matches = True

            for key, expected in metadata_filters.items():
                actual = getattr(metadata, key, None)

                if actual is None or str(actual) != expected:
                    matches = False
                    break

            if matches:
                filtered.append(result)

        return filtered
