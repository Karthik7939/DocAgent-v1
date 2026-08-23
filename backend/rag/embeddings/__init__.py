"""
Embedding generation utilities for the RAG system.

This package converts semantic chunks into dense vectors using a
provider-agnostic embedding model abstraction with persistent caching.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cache import EmbeddingCache
    from .embedder import Embedder, EmbedderStatistics
    from .embedding_models import BaseEmbeddingModel, EmbeddingModelFactory

__all__ = [
    "Embedder",
    "EmbedderStatistics",
    "BaseEmbeddingModel",
    "EmbeddingModelFactory",
    "EmbeddingCache",
]


def __getattr__(name: str):
    """
    Lazily import embedding components.
    """
    if name == "Embedder":
        from .embedder import Embedder

        return Embedder

    if name == "EmbedderStatistics":
        from .embedder import EmbedderStatistics

        return EmbedderStatistics

    if name == "BaseEmbeddingModel":
        from .embedding_models import BaseEmbeddingModel

        return BaseEmbeddingModel

    if name == "EmbeddingModelFactory":
        from .embedding_models import EmbeddingModelFactory

        return EmbeddingModelFactory

    if name == "EmbeddingCache":
        from .cache import EmbeddingCache

        return EmbeddingCache

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
