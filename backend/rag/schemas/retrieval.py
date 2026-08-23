"""
Schemas representing retrieval results produced by the hybrid retrieval
pipeline.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from rag.schemas.chunk import Chunk


class RetrievalSource(str, Enum):
    """
    Source from which a chunk was retrieved.
    """

    FAISS = "faiss"
    BM25 = "bm25"
    DEPENDENCY = "dependency"
    HYBRID = "hybrid"


class RetrievalResult(BaseModel):
    """
    Represents one retrieved chunk.
    """

    model_config = ConfigDict(frozen=True)

    chunk: Chunk = Field(
        ...,
        description="Retrieved semantic chunk.",
    )

    similarity_score: float = Field(
        ...,
        ge=0.0,
        description="Similarity score assigned during retrieval.",
    )

    rank: int = Field(
        ...,
        ge=1,
        description="Final rank after RRF.",
    )

    retrieval_source: RetrievalSource = Field(
        ...,
        description="Retrieval strategy responsible for this result.",
    )

    retrieval_reason: str = Field(
        default="",
        description="Human-readable explanation of why the chunk was retrieved.",
    )

    @property
    def file_path(self) -> str:
        """
        Returns the source file path.
        """
        return self.chunk.metadata.file_path

    @property
    def chunk_id(self) -> str:
        """
        Returns the unique chunk identifier.
        """
        return self.chunk.metadata.chunk_id

    @property
    def repository(self) -> str:
        """
        Returns the repository name.
        """
        return self.chunk.metadata.repository


class RetrievalResults(BaseModel):
    """
    Collection of retrieval results returned by the hybrid retriever.
    """

    model_config = ConfigDict(frozen=True)

    results: list[RetrievalResult] = Field(
        default_factory=list,
        description="Ranked retrieval results.",
    )

    retrieval_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Time taken to perform retrieval.",
    )

    @property
    def total_results(self) -> int:
        """
        Returns the total number of retrieved chunks.
        """
        return len(self.results)

    @property
    def faiss_results(self) -> int:
        """
        Number of FAISS results.
        """
        return sum(
            result.retrieval_source == RetrievalSource.FAISS
            for result in self.results
        )

    @property
    def bm25_results(self) -> int:
        """
        Number of BM25 results.
        """
        return sum(
            result.retrieval_source == RetrievalSource.BM25
            for result in self.results
        )

    @property
    def dependency_results(self) -> int:
        """
        Number of dependency graph results.
        """
        return sum(
            result.retrieval_source == RetrievalSource.DEPENDENCY
            for result in self.results
        )

    @property
    def hybrid_results(self) -> int:
        """
        Number of hybrid (RRF merged) results.
        """
        return sum(
            result.retrieval_source == RetrievalSource.HYBRID
            for result in self.results
        )