"""
Schema representing the context package produced by the RAG pipeline.

This is the final output of the RAG system and serves as the interface
between the RAG module and the agent pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from rag.schemas.query import SemanticQuery
from rag.schemas.retrieval import RetrievalResults


class ContextMetadata(BaseModel):
    """
    Metadata describing the generated context package.
    """

    model_config = ConfigDict(frozen=True)

    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the context package was created.",
    )

    retrieval_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Total retrieval execution time.",
    )

    total_changed_files: int = Field(
        default=0,
        ge=0,
        description="Number of changed files.",
    )

    total_retrieved_chunks: int = Field(
        default=0,
        ge=0,
        description="Number of retrieved chunks.",
    )


class ContextPackage(BaseModel):
    """
    Final context package passed to the agent pipeline.
    """

    model_config = ConfigDict(frozen=True)

    repository: str = Field(
        ...,
        description="Repository name.",
    )

    commit_sha: str = Field(
        ...,
        description="Commit SHA associated with this context.",
    )

    query: SemanticQuery = Field(
        ...,
        description="Semantic query used for retrieval.",
    )

    retrieval_results: RetrievalResults = Field(
        ...,
        description="Ranked retrieval results.",
    )

    changed_files: list[str] = Field(
        default_factory=list,
        description="Files modified in the current commit.",
    )

    metadata: ContextMetadata = Field(
        default_factory=ContextMetadata,
        description="Context package metadata.",
    )

    @property
    def total_chunks(self) -> int:
        """
        Returns the number of retrieved chunks.
        """
        return self.retrieval_results.total_results

    @property
    def has_context(self) -> bool:
        """
        Returns True if at least one chunk was retrieved.
        """
        return self.total_chunks > 0

    @property
    def retrieval_sources(self) -> dict[str, int]:
        """
        Returns the number of chunks retrieved from each retrieval strategy.
        """
        return {
            "faiss": self.retrieval_results.faiss_results,
            "bm25": self.retrieval_results.bm25_results,
            "dependency": self.retrieval_results.dependency_results,
            "hybrid": self.retrieval_results.hybrid_results,
        }


class PipelineResult(BaseModel):
    """
    Result returned by the master RAG pipeline run.
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(
        ...,
        description="True if execution completed without fatal errors.",
    )

    error: Optional[str] = Field(
        default=None,
        description="Failure error description if success is False.",
    )

    context_package: Optional[ContextPackage] = Field(
        default=None,
        description="Context package containing retrieval chunks, if query retrieve was run.",
    )

    execution_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Total execution time of the RAG run.",
    )