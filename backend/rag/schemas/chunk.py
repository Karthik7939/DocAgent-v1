"""
Schemas representing semantic chunks used throughout the RAG pipeline.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ChunkType(str, Enum):
    """Supported chunk types."""

    CODE = "code"
    DOCUMENTATION = "documentation"


class SymbolType(str, Enum):
    """Supported source code symbol types."""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    MODULE = "module"
    VARIABLE = "variable"
    SECTION = "section"
    UNKNOWN = "unknown"


class ChunkMetadata(BaseModel):
    """
    Metadata describing a semantic chunk.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(
        ...,
        description="Unique identifier of the chunk.",
    )

    repository: str = Field(
        ...,
        description="Repository name.",
    )

    file_path: str = Field(
        ...,
        description="Source file containing the chunk.",
    )

    language: str = Field(
        ...,
        description="Programming language.",
    )

    chunk_type: ChunkType = Field(
        ...,
        description="Type of chunk.",
    )

    symbol_name: Optional[str] = Field(
        default=None,
        description="Associated function/class/section name.",
    )

    symbol_type: SymbolType = Field(
        default=SymbolType.UNKNOWN,
        description="Type of source symbol.",
    )

    parent_symbol: Optional[str] = Field(
        default=None,
        description="Parent class/module if applicable.",
    )

    start_line: int = Field(
        ...,
        ge=1,
        description="Starting line number.",
    )

    end_line: int = Field(
        ...,
        ge=1,
        description="Ending line number.",
    )

    commit_sha: Optional[str] = Field(
        default=None,
        description="Commit SHA when indexed.",
    )

    content_hash: str = Field(
        ...,
        description="Hash of the chunk content.",
    )

    token_count: int = Field(
        ...,
        ge=0,
        description="Number of tokens in the chunk.",
    )

    active: bool = Field(
        default=True,
        description="False if the chunk has been invalidated.",
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Chunk creation timestamp.",
    )


class Chunk(BaseModel):
    """
    Represents one semantic chunk.

    The embedding is optional because chunks are created before
    embedding generation.
    """

    model_config = ConfigDict(frozen=True)

    metadata: ChunkMetadata

    content: str = Field(
        ...,
        min_length=1,
        description="Chunk text.",
    )

    embedding: Optional[list[float]] = Field(
        default=None,
        description="Dense embedding vector.",
    )

    summary: Optional[str] = Field(
        default=None,
        description="Optional LLM-generated summary.",
    )

    @property
    def has_embedding(self) -> bool:
        """
        Returns True if an embedding has been generated.
        """
        return self.embedding is not None

    @property
    def embedding_dimension(self) -> int:
        """
        Returns embedding dimension.

        Returns
        -------
        int
            Length of embedding vector.
        """
        if self.embedding is None:
            return 0

        return len(self.embedding)


class ChunkCollection(BaseModel):
    """
    Collection of semantic chunks.

    Used during indexing and retrieval.
    """

    model_config = ConfigDict(frozen=True)

    chunks: list[Chunk] = Field(
        default_factory=list,
        description="Semantic chunks.",
    )

    @property
    def total_chunks(self) -> int:
        """
        Returns total number of chunks.
        """
        return len(self.chunks)

    @property
    def embedded_chunks(self) -> int:
        """
        Number of chunks with embeddings.
        """
        return sum(
            chunk.has_embedding
            for chunk in self.chunks
        )