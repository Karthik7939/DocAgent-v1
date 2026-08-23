"""
Semantic chunking utilities for the RAG system.

This package splits repository source code and documentation into
meaningful chunks with enriched metadata ready for embedding
generation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .chunker import Chunker
    from .code_chunker import CodeChunker
    from .doc_chunker import DocChunker
    from .metadata_builder import MetadataBuilder
    from .models import Chunk

__all__ = [
    "Chunker",
    "CodeChunker",
    "DocChunker",
    "MetadataBuilder",
    "Chunk",
]


def __getattr__(name: str):
    """
    Lazily import chunking components to avoid loading Tree-sitter
    unless a chunking entry point is actually used.
    """
    if name == "Chunker":
        from .chunker import Chunker

        return Chunker

    if name == "CodeChunker":
        from .code_chunker import CodeChunker

        return CodeChunker

    if name == "DocChunker":
        from .doc_chunker import DocChunker

        return DocChunker

    if name == "MetadataBuilder":
        from .metadata_builder import MetadataBuilder

        return MetadataBuilder

    if name == "Chunk":
        from .models import Chunk

        return Chunk

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
