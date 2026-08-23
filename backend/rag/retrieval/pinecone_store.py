"""
Pinecone-backed dense vector store for semantic retrieval.

Each repository's chunks are stored in a dedicated Pinecone namespace
(namespace == repository_name), providing hard isolation between projects.
Retrieval for repo-A NEVER returns vectors from repo-B.

Multi-owner / collaborative repos:
    Both owners push to the same GitHub repo path (e.g. "owner/repo-A").
    The webhook fires for "owner/repo-A", the incremental pipeline updates
    the "owner/repo-A" namespace — always reflecting the latest commit.

Full chunk content is stored in a local JSON sidecar because Pinecone
metadata has a 40 KB per-vector limit and code chunks can be larger.
The sidecar lives at:
    rag/storage/pinecone/<repo_slug>/chunks.json

This module exposes the same public interface as ``VectorStore`` so all
callers can switch backends via the factory without knowing the difference.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rag.config import settings
from rag.schemas.chunk import Chunk, ChunkMetadata
from rag.utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_slug(repository: str) -> str:
    """Convert 'owner/repo' → 'owner_repo' for use in filesystem paths."""
    return re.sub(r"[^\w\-]", "_", repository)


def _sidecar_dir(repository: str) -> Path:
    return settings.storage_root / "pinecone" / _repo_slug(repository)


def _sidecar_path(repository: str) -> Path:
    return _sidecar_dir(repository) / "chunks.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class VectorStoreStatistics:
    """Statistics for the Pinecone vector store."""

    total_vectors: int = 0
    active_vectors: int = 0
    deleted_vectors: int = 0
    dimension: int = 0
    repository: str = ""


@dataclass
class VectorSearchHit:
    """One vector search result before hybrid ranking."""

    chunk: Chunk
    score: float
    faiss_id: int  # kept for API compatibility with VectorStore


# ---------------------------------------------------------------------------
# PineconeVectorStore
# ---------------------------------------------------------------------------

class PineconeVectorStore:
    """
    Dense retrieval store backed by Pinecone cloud.

    Namespace strategy
    ------------------
    Every vector is upserted and queried with ``namespace=self._repository``.
    This gives hard per-repo isolation: retrieving from ``owner/repo-A``
    never touches ``owner/repo-B``'s vectors.

    Sidecar
    -------
    Full chunk content and all metadata are persisted in a local JSON file
    (``rag/storage/pinecone/<slug>/chunks.json``) because Pinecone's
    40 KB metadata limit would truncate long source files.
    Pinecone metadata only stores what is needed for server-side filtering.
    """

    def __init__(
        self,
        repository: str = "",
        storage_dir: Optional[Path] = None,
        *,
        dimension: Optional[int] = None,
    ) -> None:
        self._repository = repository
        self._namespace = repository          # Pinecone namespace == repo name
        self._dimension = dimension
        self._storage_dir = storage_dir or _sidecar_dir(repository)

        # In-memory chunk registry (populated from sidecar on load)
        self._chunks: dict[str, Chunk] = {}
        self._deleted_chunk_ids: set[str] = set()

        # Lazy Pinecone index handle — opened on first use
        self._index = None

    # ------------------------------------------------------------------
    # Pinecone connectivity
    # ------------------------------------------------------------------

    def _get_index(self):
        """Return (and lazily open) the Pinecone index handle."""
        if self._index is not None:
            return self._index

        if not settings.pinecone_api_key:
            raise RuntimeError(
                "PINECONE_API_KEY is not set. "
                "Add it to backend/.env — see the comments there for instructions."
            )
        if not settings.pinecone_index_name:
            raise RuntimeError("PINECONE_INDEX_NAME is not set in backend/.env.")

        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise RuntimeError(
                "pinecone-client is not installed. "
                "Run: pip install pinecone-client>=3.0.0"
            ) from exc

        pc = Pinecone(api_key=settings.pinecone_api_key)
        self._index = pc.Index(settings.pinecone_index_name)
        logger.info(
            "Connected to Pinecone index '%s' (namespace: '%s').",
            settings.pinecone_index_name,
            self._namespace,
        )
        return self._index

    # ------------------------------------------------------------------
    # VectorStore-compatible interface
    # ------------------------------------------------------------------

    # These two properties mirror VectorStore so callers that check them
    # (e.g. BootstrapIndexer.persist) keep working unchanged.
    @property
    def index_path(self) -> Path:
        """Not used for Pinecone; returned so callers don't break."""
        return self._storage_dir / "pinecone.stub"

    @property
    def metadata_path(self) -> Path:
        """Not used for Pinecone; returned so callers don't break."""
        return self._storage_dir / "metadata.stub"

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise RuntimeError("PineconeVectorStore dimension is not set.")
        return self._dimension

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(
        self,
        dimension: int,
        *,
        repository: str = "",
    ) -> None:
        """
        Set the dimension and (optionally) clear the namespace.

        For Pinecone, 'create' just records the dimension locally.
        The index itself already exists in the cloud.
        """
        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive.")
        self._dimension = dimension
        if repository:
            self._repository = repository
            self._namespace = repository
        self._chunks = {}
        self._deleted_chunk_ids = set()
        logger.info(
            "PineconeVectorStore ready (dimension=%d, namespace='%s').",
            dimension,
            self._namespace,
        )

    def load(self, storage_dir: Optional[Path] = None) -> None:
        """
        Load chunk metadata from the local sidecar file.

        Pinecone holds the vectors; the sidecar holds the full content.
        """
        if storage_dir is not None:
            self._storage_dir = storage_dir

        sidecar = _sidecar_path(self._repository)
        if not sidecar.exists():
            logger.info(
                "No Pinecone sidecar found for '%s'. Starting empty.",
                self._repository,
            )
            return

        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            self._dimension = payload.get("dimension", self._dimension)
            self._repository = payload.get("repository", self._repository)
            self._namespace = self._repository
            self._deleted_chunk_ids = set(payload.get("deleted_chunk_ids", []))
            self._chunks = {
                chunk_id: Chunk.model_validate(chunk_data)
                for chunk_id, chunk_data in payload.get("chunks", {}).items()
            }
            logger.info(
                "Loaded %d chunks from Pinecone sidecar for '%s'.",
                len(self._chunks),
                self._repository,
            )
        except Exception as exc:
            logger.warning(
                "Failed to load Pinecone sidecar for '%s': %s",
                self._repository,
                exc,
            )

    def save(self) -> None:
        """
        Persist chunk metadata to the local sidecar file.

        Vectors are already stored in Pinecone cloud (durable).
        """
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        sidecar = _sidecar_path(self._repository)

        payload = {
            "dimension": self._dimension,
            "repository": self._repository,
            "deleted_chunk_ids": sorted(self._deleted_chunk_ids),
            "chunks": {
                chunk_id: chunk.model_dump(mode="json")
                for chunk_id, chunk in self._chunks.items()
            },
        }
        sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.debug(
            "Saved Pinecone sidecar for '%s' (%d chunks).",
            self._repository,
            len(self._chunks),
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, chunk: Chunk) -> int:
        """Add one chunk to Pinecone and the sidecar. Returns 0 (compat)."""
        self.add_batch([chunk])
        return 0

    def add_batch(self, chunks: list[Chunk]) -> list[int]:
        """
        Upsert a batch of embedded chunks into Pinecone.

        Each chunk is stored as:
            - vector id  = chunk_id
            - values     = embedding
            - metadata   = lightweight filtering fields
            - namespace  = repository name  (← isolation key)

        Full content lives in the local sidecar.
        """
        if not chunks:
            return []

        # Infer dimension from first chunk
        if self._dimension is None and chunks[0].has_embedding:
            self._dimension = len(chunks[0].embedding)

        index = self._get_index()
        batch_size = settings.pinecone_upsert_batch_size
        assigned: list[int] = []

        to_upsert: list[dict] = []

        for chunk in chunks:
            if not chunk.has_embedding:
                logger.warning(
                    "Skipping chunk %s — no embedding.",
                    chunk.metadata.chunk_id,
                )
                continue

            chunk_id = chunk.metadata.chunk_id
            meta = chunk.metadata

            # Store in local registry (for content retrieval & statistics)
            self._chunks[chunk_id] = chunk
            self._deleted_chunk_ids.discard(chunk_id)

            # Pinecone metadata — lightweight, for server-side filtering
            pinecone_meta = {
                "repository": meta.repository,
                "file_path": meta.file_path,
                "language": meta.language,
                "chunk_type": meta.chunk_type.value,
                "symbol_name": meta.symbol_name or "",
                "symbol_type": meta.symbol_type.value,
                "start_line": meta.start_line,
                "end_line": meta.end_line,
                "commit_sha": meta.commit_sha or "",
                "content_hash": meta.content_hash,
                "token_count": meta.token_count,
                "active": meta.active,
            }

            to_upsert.append({
                "id": chunk_id,
                "values": chunk.embedding,
                "metadata": pinecone_meta,
            })
            assigned.append(0)  # compat — FAISS returns int IDs

        # Send in configurable batches to respect Pinecone limits
        for batch_start in range(0, len(to_upsert), batch_size):
            batch = to_upsert[batch_start: batch_start + batch_size]
            try:
                index.upsert(vectors=batch, namespace=self._namespace)
                logger.debug(
                    "Upserted %d vectors to Pinecone namespace '%s'.",
                    len(batch),
                    self._namespace,
                )
            except Exception as exc:
                logger.error(
                    "Pinecone upsert failed (namespace='%s'): %s",
                    self._namespace,
                    exc,
                )
                raise

        return assigned

    def update(self, chunk: Chunk) -> int:
        """Replace a chunk (delete + re-upsert)."""
        self.delete(chunk.metadata.chunk_id, soft=False)
        return self.add(chunk)

    def delete(
        self,
        chunk_id: str,
        *,
        soft: bool = True,
    ) -> bool:
        """
        Delete a chunk from active retrieval.

        soft=True  → marks inactive in sidecar only (fast, reversible).
        soft=False → also removes the vector from Pinecone.
        """
        if chunk_id not in self._chunks:
            return False

        if soft:
            self._deleted_chunk_ids.add(chunk_id)
            # Mark inactive in sidecar
            existing = self._chunks.get(chunk_id)
            if existing:
                inactive_meta = existing.metadata.model_copy(update={"active": False})
                self._chunks[chunk_id] = existing.model_copy(
                    update={"metadata": inactive_meta}
                )
            return True

        # Hard delete — remove from Pinecone cloud
        try:
            index = self._get_index()
            index.delete(ids=[chunk_id], namespace=self._namespace)
        except Exception as exc:
            logger.warning(
                "Pinecone hard delete failed for chunk '%s': %s",
                chunk_id,
                exc,
            )

        self._chunks.pop(chunk_id, None)
        self._deleted_chunk_ids.discard(chunk_id)
        return True

    def rebuild(self, chunks: list[Chunk]) -> None:
        """
        Delete all vectors in this namespace and re-upsert from scratch.

        Used by bootstrap when a full re-index is needed.
        """
        if not chunks and self._dimension is None:
            raise RuntimeError(
                "Cannot rebuild an empty Pinecone store without a dimension."
            )

        dimension = len(chunks[0].embedding or []) if chunks else self._dimension
        repository = chunks[0].metadata.repository if chunks else self._repository

        logger.info(
            "Rebuilding Pinecone namespace '%s' (%d chunks)...",
            self._namespace,
            len(chunks),
        )

        # Clear namespace in Pinecone
        try:
            index = self._get_index()
            index.delete(delete_all=True, namespace=self._namespace)
            logger.info(
                "Cleared Pinecone namespace '%s'.",
                self._namespace,
            )
        except Exception as exc:
            logger.warning(
                "Failed to clear Pinecone namespace '%s': %s. Proceeding with upsert.",
                self._namespace,
                exc,
            )

        # Reset local state
        self.create(dimension, repository=repository)

        # Re-upsert
        if chunks:
            self.add_batch(chunks)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def search(
        self,
        vector: list[float],
        top_k: int = 10,
        *,
        similarity_threshold: Optional[float] = None,
    ) -> list[VectorSearchHit]:
        """
        Query Pinecone for the most similar active chunks in this repo's namespace.

        Only the repository's own namespace is searched — cross-repo bleed
        is architecturally impossible.
        """
        if not self._chunks and not self._repository:
            return []

        threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.similarity_threshold
        )

        try:
            index = self._get_index()
            response = index.query(
                vector=vector,
                top_k=min(top_k * 3, 10000),   # over-fetch to filter deleted
                namespace=self._namespace,       # ← repo isolation
                include_metadata=True,
            )
        except Exception as exc:
            logger.error(
                "Pinecone query failed (namespace='%s'): %s",
                self._namespace,
                exc,
            )
            return []

        hits: list[VectorSearchHit] = []

        for match in response.get("matches", []):
            chunk_id: str = match["id"]
            score: float = float(match.get("score", 0.0))

            if score < threshold:
                continue

            if chunk_id in self._deleted_chunk_ids:
                continue

            # Try sidecar first (has full content)
            chunk = self._chunks.get(chunk_id)

            if chunk is None:
                # Reconstruct a minimal Chunk from Pinecone metadata so we
                # don't fail completely if sidecar is out of sync
                chunk = self._chunk_from_pinecone_match(match)
                if chunk is None:
                    continue

            if not chunk.metadata.active:
                continue

            hits.append(
                VectorSearchHit(
                    chunk=chunk,
                    score=score,
                    faiss_id=0,  # compat field
                )
            )

            if len(hits) >= top_k:
                break

        return hits

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Return one chunk by identifier (from sidecar)."""
        return self._chunks.get(chunk_id)

    def get_chunks_by_file(self, file_path: str) -> list[Chunk]:
        """Return all active chunks belonging to a file."""
        return [
            chunk
            for chunk in self._chunks.values()
            if chunk.metadata.file_path == file_path
            and chunk.metadata.active
            and chunk.metadata.chunk_id not in self._deleted_chunk_ids
        ]

    def get_all_active_chunks(self) -> list[Chunk]:
        """Return every active chunk in the sidecar."""
        return [
            chunk
            for chunk_id, chunk in self._chunks.items()
            if chunk.metadata.active and chunk_id not in self._deleted_chunk_ids
        ]

    def statistics(self) -> VectorStoreStatistics:
        """Return vector store statistics from the local sidecar."""
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _chunk_from_pinecone_match(self, match: dict) -> Chunk | None:
        """
        Reconstruct a minimal Chunk from a Pinecone query match.
        Used as fallback when the local sidecar is missing an entry.
        """
        try:
            from rag.schemas.chunk import ChunkType, SymbolType

            meta = match.get("metadata", {})
            chunk_meta = ChunkMetadata(
                chunk_id=match["id"],
                repository=meta.get("repository", self._repository),
                file_path=meta.get("file_path", "unknown"),
                language=meta.get("language", "unknown"),
                chunk_type=ChunkType(meta.get("chunk_type", "code")),
                symbol_name=meta.get("symbol_name") or None,
                symbol_type=SymbolType(meta.get("symbol_type", "unknown")),
                start_line=int(meta.get("start_line", 1)),
                end_line=int(meta.get("end_line", 1)),
                commit_sha=meta.get("commit_sha") or None,
                content_hash=meta.get("content_hash", ""),
                token_count=int(meta.get("token_count", 0)),
                active=bool(meta.get("active", True)),
            )
            return Chunk(
                metadata=chunk_meta,
                content="[Content not available — sidecar out of sync]",
            )
        except Exception as exc:
            logger.warning("Failed to reconstruct chunk from Pinecone match: %s", exc)
            return None
