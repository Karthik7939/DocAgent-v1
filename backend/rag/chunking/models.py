"""
Data structures used by the chunking module.

This module defines chunking-specific models and re-exports the shared
chunk schemas used across the RAG pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from rag.schemas.chunk import Chunk, ChunkType, SymbolType

__all__ = [
    "Chunk",
    "ChunkDraft",
    "ChunkStatistics",
    "ChunkType",
    "ChunkValidationResult",
    "SymbolType",
]


@dataclass(slots=True, frozen=True)
class ChunkDraft:
    """
    Intermediate chunk produced by a chunker before metadata enrichment.

    Chunkers extract content and structural information only. The
    metadata builder adds identifiers, hashes, and repository metadata.
    """

    content: str
    start_line: int
    end_line: int
    language: str
    chunk_type: ChunkType
    symbol_name: Optional[str] = None
    symbol_type: SymbolType = SymbolType.UNKNOWN
    parent_symbol: Optional[str] = None


class ChunkStatistics(BaseModel):
    """
    Aggregated statistics for a chunking run.
    """

    model_config = ConfigDict(frozen=True)

    total_chunks: int = Field(default=0, ge=0)
    code_chunks: int = Field(default=0, ge=0)
    documentation_chunks: int = Field(default=0, ge=0)
    module_chunks: int = Field(default=0, ge=0)
    symbol_chunks: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    files_processed: int = Field(default=0, ge=0)
    files_skipped: int = Field(default=0, ge=0)

    def merge(self, other: ChunkStatistics) -> ChunkStatistics:
        """
        Combine two statistics objects.
        """
        return ChunkStatistics(
            total_chunks=self.total_chunks + other.total_chunks,
            code_chunks=self.code_chunks + other.code_chunks,
            documentation_chunks=(
                self.documentation_chunks + other.documentation_chunks
            ),
            module_chunks=self.module_chunks + other.module_chunks,
            symbol_chunks=self.symbol_chunks + other.symbol_chunks,
            total_tokens=self.total_tokens + other.total_tokens,
            files_processed=self.files_processed + other.files_processed,
            files_skipped=self.files_skipped + other.files_skipped,
        )


class ChunkValidationResult(BaseModel):
    """
    Result of validating chunks before they leave the chunking pipeline.
    """

    model_config = ConfigDict(frozen=True)

    valid: bool = Field(
        ...,
        description="True when all chunks passed validation.",
    )

    errors: list[str] = Field(
        default_factory=list,
        description="Validation errors that invalidate the result.",
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal validation warnings.",
    )

    duplicate_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Duplicate chunk identifiers detected.",
    )

    empty_chunks: int = Field(
        default=0,
        ge=0,
        description="Number of empty chunks removed or flagged.",
    )
