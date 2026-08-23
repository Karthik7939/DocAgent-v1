"""
Schema representing a semantic retrieval query.

The query builder converts detected code changes into this model,
which is then consumed by the hybrid retrieval pipeline.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from rag.config import settings


class SemanticQuery(BaseModel):
    """
    Represents a semantic query generated from repository changes.
    """

    model_config = ConfigDict(frozen=True)

    repository: str = Field(
        ...,
        description="Repository name.",
    )

    commit_sha: str = Field(
        ...,
        description="Current commit SHA.",
    )

    query_text: str = Field(
        ...,
        min_length=1,
        description="Natural language retrieval query.",
    )

    changed_files: list[str] = Field(
        default_factory=list,
        description="Files involved in the current commit.",
    )

    modified_symbols: list[str] = Field(
        default_factory=list,
        description="Functions/classes/methods modified.",
    )

    renamed_symbols: list[dict[str, str]] = Field(
        default_factory=list,
        description="Structural rename mappings with from and to symbol names.",
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords extracted for BM25 retrieval.",
    )

    semantic_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured semantic evidence used to build the retrieval query.",
    )

    semantic_sections: dict[str, list[str] | str] = Field(
        default_factory=dict,
        description="Structured documentation-oriented query sections.",
    )

    cluster_summaries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Clustered semantic evidence for multi-file commits.",
    )

    file_extensions: list[str] = Field(
        default_factory=list,
        description="Extensions of changed files.",
    )

    languages: list[str] = Field(
        default_factory=list,
        description="Programming languages involved.",
    )

    dependency_files: list[str] = Field(
        default_factory=list,
        description="Files discovered through dependency analysis.",
    )

    top_k: int = Field(
        default_factory=lambda: settings.top_k,
        ge=1,
        description="Maximum number of chunks to retrieve.",
    )

    similarity_threshold: float = Field(
        default_factory=lambda: settings.similarity_threshold,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score.",
    )

    metadata_filters: dict[str, str] = Field(
        default_factory=dict,
        description="Optional metadata filters for retrieval.",
    )

    @property
    def has_keywords(self) -> bool:
        """
        Returns True if keyword retrieval should be used.
        """
        return len(self.keywords) > 0

    @property
    def has_dependencies(self) -> bool:
        """
        Returns True if dependency-based retrieval is applicable.
        """
        return len(self.dependency_files) > 0

    @property
    def total_changed_files(self) -> int:
        """
        Returns the number of changed files.
        """
        return len(self.changed_files)

    @property
    def total_modified_symbols(self) -> int:
        """
        Returns the number of modified symbols.
        """
        return len(self.modified_symbols)

    @property
    def uses_metadata_filters(self) -> bool:
        """
        Returns True if metadata filters are specified.
        """
        return len(self.metadata_filters) > 0
