"""
Dependency-based chunk retrieval.

This module converts dependency graph traversal results into relevant
chunks. Graph traversal itself is delegated to ``DependencyGraphQuery``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rag.parsing.dependency_graph import DependencyGraphQuery
from rag.schemas.chunk import Chunk
from rag.utils import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class DependencyRetrieverStatistics:
    """
    Statistics for dependency-based retrieval.
    """

    files_expanded: int = 0
    chunks_returned: int = 0
    missing_files: int = 0


@dataclass(frozen=True, slots=True)
class DependencySearchHit:
    """
    One dependency retrieval result before hybrid ranking.
    """

    chunk: Chunk
    score: float
    source_file: str
    reason: str


class DependencyRetriever:
    """
    Retrieve chunks related to changed files through the dependency graph.
    """

    def __init__(
        self,
        graph_query: DependencyGraphQuery,
        chunks_by_file: dict[str, list[Chunk]] | None = None,
    ) -> None:
        self._graph_query = graph_query
        self._chunks_by_file = chunks_by_file or {}
        self._stats = DependencyRetrieverStatistics()

    def set_chunks_by_file(
        self,
        chunks_by_file: dict[str, list[Chunk]],
    ) -> None:
        """
        Replace the file-to-chunk registry used for retrieval.
        """
        self._chunks_by_file = chunks_by_file

    def retrieve(
        self,
        changed_files: Iterable[str],
        *,
        depth: int = 2,
    ) -> list[DependencySearchHit]:
        """
        Retrieve chunks for changed files and their dependency neighborhood.
        """
        return self.affected_chunks(changed_files, depth=depth)

    def retrieve_one_hop(
        self,
        file_path: str,
    ) -> list[DependencySearchHit]:
        """
        Retrieve chunks for a file and its one-hop neighbors.
        """
        files = {file_path} | self._graph_query.one_hop(file_path)
        return self._hits_for_files(files, seed=file_path, depth=1)

    def retrieve_two_hop(
        self,
        file_path: str,
    ) -> list[DependencySearchHit]:
        """
        Retrieve chunks for a file and its two-hop neighborhood.
        """
        files = {file_path} | self._graph_query.two_hop(file_path)
        return self._hits_for_files(files, seed=file_path, depth=2)

    def affected_chunks(
        self,
        changed_files: Iterable[str],
        *,
        depth: int = 2,
    ) -> list[DependencySearchHit]:
        """
        Retrieve chunks for all files affected by a set of changes.
        """
        changed = list(changed_files)
        affected_files = self._graph_query.affected_files(changed)
        hits = self._hits_for_files(
            affected_files,
            seed=changed[0] if changed else "",
            depth=depth,
        )
        self._stats.files_expanded = len(affected_files)
        self._stats.chunks_returned = len(hits)
        return hits

    def expand_context(
        self,
        seed_files: Iterable[str],
        *,
        depth: int = 2,
    ) -> list[DependencySearchHit]:
        """
        Expand retrieval context around one or more seed files.
        """
        seeds = list(seed_files)
        affected: set[str] = set()

        for seed in seeds:
            affected.update({seed} | self._graph_query.bfs(seed, depth=depth))

        seed = seeds[0] if seeds else ""
        return self._hits_for_files(affected, seed=seed, depth=depth)

    def statistics(self) -> DependencyRetrieverStatistics:
        """
        Return dependency retrieval statistics.
        """
        return self._stats

    def _hits_for_files(
        self,
        file_paths: Iterable[str],
        *,
        seed: str,
        depth: int,
    ) -> list[DependencySearchHit]:
        hits: list[DependencySearchHit] = []
        seen_chunk_ids: set[str] = set()

        for file_path in sorted(set(file_paths)):
            chunks = self._chunks_for_file(file_path)

            if not chunks:
                self._stats.missing_files += 1
                continue

            for chunk in chunks:
                if chunk.metadata.chunk_id in seen_chunk_ids:
                    continue

                seen_chunk_ids.add(chunk.metadata.chunk_id)
                hits.append(
                    DependencySearchHit(
                        chunk=chunk,
                        score=self._dependency_score(
                            file_path,
                            seed,
                            depth,
                        ),
                        source_file=file_path,
                        reason=self._build_reason(
                            file_path,
                            seed,
                            depth,
                        ),
                    ),
                )

        return hits

    def _chunks_for_file(self, file_path: str) -> list[Chunk]:
        chunks = self._chunks_by_file.get(file_path, [])
        return [
            chunk
            for chunk in chunks
            if chunk.metadata.active
        ]

    @staticmethod
    def _dependency_score(
        file_path: str,
        seed: str,
        depth: int,
    ) -> float:
        if file_path == seed:
            return 1.0
        if depth <= 1:
            return 0.8
        return 0.6

    @staticmethod
    def _build_reason(
        file_path: str,
        seed: str,
        depth: int,
    ) -> str:
        if file_path == seed:
            return "Changed file"

        return (
            f"Dependency neighbor of {seed} within {depth} hop(s)"
        )
