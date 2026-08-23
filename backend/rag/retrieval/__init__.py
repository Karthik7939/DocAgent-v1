"""
Hybrid retrieval utilities for the RAG system.

This package combines dense vector search, BM25 keyword search, and
dependency graph retrieval into one ranked result set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dependency_retriever import DependencyRetriever
    from .hybrid_retriever import HybridRetriever
    from .keyword_store import KeywordStore
    from .metadata_filter import MetadataFilter
    from .vector_store import VectorStore

__all__ = [
    "HybridRetriever",
    "VectorStore",
    "KeywordStore",
    "DependencyRetriever",
    "MetadataFilter",
]


def __getattr__(name: str):
    """
    Lazily import retrieval components.
    """
    if name == "HybridRetriever":
        from .hybrid_retriever import HybridRetriever

        return HybridRetriever

    if name == "VectorStore":
        from .vector_store import VectorStore

        return VectorStore

    if name == "KeywordStore":
        from .keyword_store import KeywordStore

        return KeywordStore

    if name == "DependencyRetriever":
        from .dependency_retriever import DependencyRetriever

        return DependencyRetriever

    if name == "MetadataFilter":
        from .metadata_filter import MetadataFilter

        return MetadataFilter

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
