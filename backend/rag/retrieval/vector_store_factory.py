"""
Vector store factory.

Returns the correct vector store backend based on
``RAG_VECTOR_STORE_BACKEND`` in the environment:

    "pinecone" → PineconeVectorStore  (cloud, per-repo namespaces)
    "faiss"    → VectorStore          (local FAISS files, default)

Usage::

    from rag.retrieval.vector_store_factory import get_vector_store

    vector_store = get_vector_store(repository="owner/repo")
"""

from __future__ import annotations

from rag.config import settings
from rag.utils import get_logger

logger = get_logger(__name__)


def get_vector_store(repository: str = ""):
    """
    Return the configured vector store backend for the given repository.

    Parameters
    ----------
    repository:
        Repository name (e.g. ``"owner/repo"``).  For Pinecone this becomes
        the namespace that isolates this repo's vectors from all others.

    Returns
    -------
    PineconeVectorStore | VectorStore
        The selected backend instance.  Both expose the same public API.
    """
    backend = (settings.vector_store_backend or "faiss").strip().lower()

    if backend == "pinecone":
        from rag.retrieval.pinecone_store import PineconeVectorStore

        logger.debug(
            "Using Pinecone vector store (namespace='%s').",
            repository,
        )
        return PineconeVectorStore(repository=repository)

    # Default: local FAISS
    from rag.retrieval.vector_store import VectorStore

    logger.debug(
        "Using FAISS vector store (repository='%s').",
        repository,
    )
    return VectorStore(repository=repository)
