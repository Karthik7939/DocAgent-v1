"""
FAISS-backed dense vector store for semantic retrieval.

This module manages vector indexing and similarity search. It has no
knowledge of Git, dependency graphs, BM25, or LLMs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

from rag.config import settings
from rag.config.constants import (
    FAISS_DIRECTORY,
    FAISS_INDEX_FILENAME,
    METADATA_FILENAME,
)
from rag.schemas.chunk import Chunk
from rag.utils import get_logger

logger = get_logger(__name__)


def _repo_slug(repository: str) -> str:
    """Convert 'owner/repo' → 'owner_repo' safe for use as a directory name."""
    return re.sub(r"[^\w\-]", "_", repository) if repository else "_default"


@dataclass(slots=True)
class VectorStoreStatistics:
    """
    Statistics for the FAISS vector store.
    """

    total_vectors: int = 0
    active_vectors: int = 0
    deleted_vectors: int = 0
    dimension: int = 0
    repository: str = ""


@dataclass
class VectorSearchHit:
    """
    One vector search result before hybrid ranking.
    """

    chunk: Chunk
    score: float
    faiss_id: int


class VectorStore:
    """
    Dense retrieval store backed by FAISS.
    """

    def __init__(
        self,
        storage_dir: Path | None = None,
        *,
        dimension: Optional[int] = None,
        repository: str = "",
    ) -> None:
        # Each repository gets its own subdirectory so FAISS indexes never mix.
        # Path: storage/faiss/<repo_slug>/
        self._repository = repository
        self._storage_dir = storage_dir or (
            settings.storage_root / FAISS_DIRECTORY / _repo_slug(repository)
        )
        self._dimension = dimension
        self._repository = repository
        self._index: faiss.IndexFlatIP | None = None
        self._chunks: dict[str, Chunk] = {}
        self._faiss_id_to_chunk_id: dict[int, str] = {}
        self._chunk_id_to_faiss_id: dict[str, int] = {}
        self._next_faiss_id: int = 0
        self._deleted_chunk_ids: set[str] = set()

    @property
    def index_path(self) -> Path:
        return self._storage_dir / FAISS_INDEX_FILENAME

    @property
    def metadata_path(self) -> Path:
        return self._storage_dir / METADATA_FILENAME

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise RuntimeError("Vector store dimension is not initialized.")
        return self._dimension

    def create(
        self,
        dimension: int,
        *,
        repository: str = "",
    ) -> None:
        """
        Create a new empty FAISS index.
        """
        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive.")

        self._dimension = dimension
        self._repository = repository
        self._index = faiss.IndexFlatIP(dimension)
        self._chunks = {}
        self._faiss_id_to_chunk_id = {}
        self._chunk_id_to_faiss_id = {}
        self._next_faiss_id = 0
        self._deleted_chunk_ids = set()
        logger.info("Created FAISS index (dimension=%d).", dimension)

    def load(
        self,
        storage_dir: Path | None = None,
    ) -> None:
        """
        Load a persisted FAISS index and metadata.
        """
        if storage_dir is not None:
            self._storage_dir = storage_dir

        if not self.index_path.exists() or not self.metadata_path.exists():
            raise FileNotFoundError(
                f"Vector store not found in {self._storage_dir}",
            )

        try:
            self._index = faiss.read_index(str(self.index_path))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load FAISS index from {self.index_path}.",
            ) from exc

        payload = json.loads(
            self.metadata_path.read_text(encoding="utf-8"),
        )
        self._dimension = int(payload["dimension"])
        self._repository = payload.get("repository", "")
        self._next_faiss_id = int(payload.get("next_faiss_id", 0))
        self._deleted_chunk_ids = set(payload.get("deleted_chunk_ids", []))

        if self._index.d != self._dimension:
            raise RuntimeError(
                "FAISS index dimension does not match metadata dimension.",
            )

        self._chunks = {}
        self._faiss_id_to_chunk_id = {}
        self._chunk_id_to_faiss_id = {}

        for faiss_id_str, chunk_payload in payload.get("chunks", {}).items():
            faiss_id = int(faiss_id_str)
            chunk = Chunk.model_validate(chunk_payload)
            chunk_id = chunk.metadata.chunk_id
            self._chunks[chunk_id] = chunk
            self._faiss_id_to_chunk_id[faiss_id] = chunk_id
            self._chunk_id_to_faiss_id[chunk_id] = faiss_id

        logger.info(
            "Loaded FAISS index with %d vectors.",
            self.statistics().total_vectors,
        )

    def save(self) -> None:
        """
        Persist the FAISS index and metadata to disk.
        """
        if self._index is None:
            raise RuntimeError("Cannot save an uninitialized vector store.")

        self._storage_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.index_path))

        payload = {
            "dimension": self._dimension,
            "repository": self._repository,
            "next_faiss_id": self._next_faiss_id,
            "deleted_chunk_ids": sorted(self._deleted_chunk_ids),
            "chunks": {
                str(faiss_id): self._chunks[chunk_id].model_dump(mode="json")
                for faiss_id, chunk_id in self._faiss_id_to_chunk_id.items()
            },
        }
        self.metadata_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def search(
        self,
        vector: list[float],
        top_k: int = 10,
        *,
        similarity_threshold: Optional[float] = None,
    ) -> list[VectorSearchHit]:
        """
        Search for the most similar active chunks.
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        if len(vector) != self.dimension:
            raise ValueError(
                f"Query dimension {len(vector)} does not match "
                f"index dimension {self.dimension}.",
            )

        threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.similarity_threshold
        )
        query = np.array([vector], dtype=np.float32)
        fetch_k = min(max(top_k * 3, top_k), self._index.ntotal)
        scores, indices = self._index.search(query, fetch_k)

        hits: list[VectorSearchHit] = []

        for score, faiss_id in zip(scores[0], indices[0], strict=False):
            if faiss_id < 0:
                continue

            chunk_id = self._faiss_id_to_chunk_id.get(int(faiss_id))
            if chunk_id is None:
                continue

            if chunk_id in self._deleted_chunk_ids:
                continue

            chunk = self._chunks.get(chunk_id)
            if chunk is None or not chunk.metadata.active:
                continue

            similarity = float(score)
            if similarity < threshold:
                continue

            hits.append(
                VectorSearchHit(
                    chunk=chunk,
                    score=similarity,
                    faiss_id=int(faiss_id),
                ),
            )

            if len(hits) >= top_k:
                break

        return hits

    def add(self, chunk: Chunk) -> int:
        """
        Add one chunk embedding to the index.
        """
        return self.add_batch([chunk])[0]

    def add_batch(self, chunks: list[Chunk]) -> list[int]:
        """
        Add multiple chunk embeddings to the index.
        """
        if not chunks:
            return []

        self._ensure_index(chunks[0])

        assigned_ids: list[int] = []
        vectors: list[list[float]] = []

        for chunk in chunks:
            if not chunk.has_embedding:
                raise ValueError(
                    f"Chunk {chunk.metadata.chunk_id} has no embedding.",
                )

            if len(chunk.embedding) != self.dimension:
                raise ValueError(
                    f"Embedding dimension mismatch for "
                    f"{chunk.metadata.chunk_id}.",
                )

            chunk_id = chunk.metadata.chunk_id

            if chunk_id in self._chunk_id_to_faiss_id:
                logger.debug(
                    "Skipping duplicate chunk ID on add: %s",
                    chunk_id,
                )
                assigned_ids.append(self._chunk_id_to_faiss_id[chunk_id])
                continue

            faiss_id = self._next_faiss_id
            self._next_faiss_id += 1
            self._chunks[chunk_id] = chunk
            self._faiss_id_to_chunk_id[faiss_id] = chunk_id
            self._chunk_id_to_faiss_id[chunk_id] = faiss_id
            self._deleted_chunk_ids.discard(chunk_id)
            vectors.append(chunk.embedding)
            assigned_ids.append(faiss_id)

        if vectors:
            matrix = np.array(vectors, dtype=np.float32)
            self._index.add(matrix)

        return assigned_ids

    def update(self, chunk: Chunk) -> int:
        """
        Replace a chunk by soft-deleting the old entry and adding anew.
        """
        self.delete(chunk.metadata.chunk_id, soft=True)
        return self.add(chunk)

    def delete(
        self,
        chunk_id: str,
        *,
        soft: bool = True,
    ) -> bool:
        """
        Delete a chunk from active retrieval results.
        """
        if chunk_id not in self._chunk_id_to_faiss_id:
            return False

        if soft:
            self._deleted_chunk_ids.add(chunk_id)
            if chunk_id in self._chunks:
                inactive = self._chunks[chunk_id].metadata.model_copy(
                    update={"active": False},
                )
                self._chunks[chunk_id] = self._chunks[chunk_id].model_copy(
                    update={"metadata": inactive},
                )
            return True

        faiss_id = self._chunk_id_to_faiss_id.pop(chunk_id)
        self._faiss_id_to_chunk_id.pop(faiss_id, None)
        self._chunks.pop(chunk_id, None)
        self._deleted_chunk_ids.discard(chunk_id)
        return True

    def rebuild(self, chunks: list[Chunk]) -> None:
        """
        Rebuild the entire FAISS index from scratch.
        """
        if not chunks:
            if self._dimension is None:
                raise RuntimeError(
                    "Cannot rebuild an empty store without a dimension.",
                )
            self.create(self._dimension, repository=self._repository)
            return

        dimension = len(chunks[0].embedding or [])
        repository = chunks[0].metadata.repository
        self.create(dimension, repository=repository)
        self.add_batch(chunks)

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """
        Return one chunk by identifier.
        """
        return self._chunks.get(chunk_id)

    def get_chunks_by_file(self, file_path: str) -> list[Chunk]:
        """
        Return all active chunks belonging to a file.
        """
        return [
            chunk
            for chunk in self._chunks.values()
            if chunk.metadata.file_path == file_path
            and chunk.metadata.active
            and chunk.metadata.chunk_id not in self._deleted_chunk_ids
        ]

    def get_all_active_chunks(self) -> list[Chunk]:
        """
        Return every active chunk in the store.
        """
        return [
            chunk
            for chunk_id, chunk in self._chunks.items()
            if chunk.metadata.active and chunk_id not in self._deleted_chunk_ids
        ]

    def statistics(self) -> VectorStoreStatistics:
        """
        Return vector store statistics.
        """
        total = len(self._chunks)
        deleted = len(self._deleted_chunk_ids)
        active = total - deleted

        return VectorStoreStatistics(
            total_vectors=total,
            active_vectors=active,
            deleted_vectors=deleted,
            dimension=self._dimension or 0,
            repository=self._repository,
        )

    def _ensure_index(self, chunk: Chunk) -> None:
        if self._index is not None:
            return

        if not chunk.has_embedding:
            raise ValueError("Cannot initialize vector store without embedding.")

        self.create(
            len(chunk.embedding),
            repository=chunk.metadata.repository,
        )
