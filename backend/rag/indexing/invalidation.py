"""
Index invalidation and garbage collection.

Manages soft deletions, restorations, physical purging, and rebuild checks for
FAISS and BM25 indexing stores.
"""

from __future__ import annotations

from rag.retrieval.keyword_store import KeywordStore
from rag.retrieval.vector_store import VectorStore
from rag.utils import get_logger

logger = get_logger(__name__)


class IndexInvalidator:
    """
    Manages soft deletion and physical index cleanups for FAISS and BM25.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        keyword_store: KeywordStore,
        rebuild_threshold: float = 0.25,
    ) -> None:
        self.vector_store = vector_store
        self.keyword_store = keyword_store
        self.rebuild_threshold = rebuild_threshold

    def invalidate(self, chunk_id: str) -> None:
        """
        Soft deletes a chunk from retrieval indexes.
        """
        self.vector_store.delete(chunk_id, soft=True)
        self.keyword_store.delete(chunk_id, soft=True)
        logger.info("Soft deleted chunk: %s", chunk_id)

    def mark_deleted(self, chunk_id: str) -> None:
        """
        Alias for invalidate.
        """
        self.invalidate(chunk_id)

    def restore(self, chunk_id: str) -> None:
        """
        Restores a soft-deleted chunk to active status.
        """
        # VectorStore restoration
        if chunk_id in self.vector_store._deleted_chunk_ids:
            self.vector_store._deleted_chunk_ids.discard(chunk_id)
            chunk = self.vector_store.get_chunk(chunk_id)
            if chunk:
                active_meta = chunk.metadata.model_copy(update={"active": True})
                self.vector_store._chunks[chunk_id] = chunk.model_copy(
                    update={"metadata": active_meta}
                )

        # KeywordStore restoration
        if chunk_id in self.keyword_store._deleted_chunk_ids:
            self.keyword_store._deleted_chunk_ids.discard(chunk_id)

        logger.info("Restored soft-deleted chunk: %s", chunk_id)

    def cleanup(self) -> None:
        """
        Physically purges soft-deleted chunks from FAISS and BM25 by rebuilding.
        """
        logger.info("Running physical index cleanup...")
        active_chunks = self.vector_store.get_all_active_chunks()

        # Rebuild vector store
        self.vector_store.rebuild(active_chunks)
        self.vector_store._deleted_chunk_ids.clear()

        # Rebuild keyword store
        self.keyword_store.index(active_chunks)
        self.keyword_store._deleted_chunk_ids.clear()

        logger.info(
            "Physical index cleanup completed. Kept %d active chunks.",
            len(active_chunks),
        )

    def needs_rebuild(self) -> bool:
        """
        Determines if physical rebuild is needed based on ratio of deleted chunks.
        """
        stats = self.vector_store.statistics()
        if stats.total_vectors == 0:
            return False
        ratio = stats.deleted_vectors / stats.total_vectors
        return ratio >= self.rebuild_threshold
