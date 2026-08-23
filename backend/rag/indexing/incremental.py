"""
Incremental indexing update.

Performs fast updates on commits, analyzing chunk hash diffs, checking model
mismatches, supporting transactions, consistency checks, and detail logging.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import time
from typing import Any, Optional

from rag.chunking.chunker import Chunker
from rag.config import settings
from rag.embeddings.embedder import Embedder
from rag.indexing.bootstrap import BootstrapIndexer
from rag.indexing.invalidation import IndexInvalidator
from rag.parsing.dependency_graph import DependencyGraphUpdater, GraphPersistence
from rag.retrieval.keyword_store import KeywordStore
from rag.retrieval.vector_store_factory import get_vector_store
from rag.utils import get_logger
from rag.utils.file_loader import load_text_file

logger = get_logger(__name__)


class IncrementalIndexer:
    """
    Handles incremental updates to index structures (FAISS, BM25, dependency graph).
    """

    def __init__(
        self,
        repository_path: str,
        repository_name: str,
        commit_sha: str,
        vector_store=None,
        keyword_store: Optional[KeywordStore] = None,
        chunker: Optional[Chunker] = None,
        embedder: Optional[Embedder] = None,
    ) -> None:
        self.repository_path = Path(repository_path)
        self.repository_name = repository_name
        self.commit_sha = commit_sha

        self.vector_store = vector_store or get_vector_store(repository=repository_name)
        self.keyword_store = keyword_store or KeywordStore(repository=repository_name)
        self.chunker = chunker or Chunker()
        self.embedder = embedder or Embedder()

    def _ensure_loaded(self) -> None:
        """
        Loads the indexes if they are not already in memory.
        """
        # VectorStore
        try:
            if not self.vector_store._chunks:
                self.vector_store.load()
        except Exception:
            pass

        # KeywordStore
        try:
            if not self.keyword_store._chunks:
                self.keyword_store.load()
        except Exception:
            pass

    def _model_info_path(self) -> Path:
        return self.vector_store._storage_dir / "embedding_model_info.json"

    def _check_model_version_mismatch(self) -> bool:
        """
        Returns True if the current model or version differs from stored metadata.
        """
        info_path = self._model_info_path()
        if not info_path.exists():
            return True

        try:
            data = json.loads(info_path.read_text(encoding="utf-8"))
            stored_name = data.get("model_name")
            stored_ver = data.get("model_version")

            curr_name = self.embedder.model.model_name()
            curr_ver = self.embedder.model.model_version()

            if stored_name != curr_name or stored_ver != curr_ver:
                logger.warning(
                    "Embedding model changed from %s (v%s) to %s (v%s). Rebuild required.",
                    stored_name,
                    stored_ver,
                    curr_name,
                    curr_ver,
                )
                return True
        except Exception as e:
            logger.error("Failed to parse embedding model info: %s", e)
            return True

        return False

    def update(
        self,
        added_files: list[str],
        modified_files: list[str],
        deleted_files: list[str],
        renamed_files: dict[str, str],
        workflow_id: Optional[str] = None,
    ) -> None:
        """
        Incrementally applies commit changes. Falls back to bootstrap on mismatch.
        """
        start_time = time.time()

        try:
            # Check model version mismatch
            if self._check_model_version_mismatch():
                logger.info("Triggering full bootstrap rebuild due to embedding model mismatch...")
                bootstrap_indexer = BootstrapIndexer(
                    str(self.repository_path),
                    self.repository_name,
                    self.commit_sha,
                    vector_store=self.vector_store,
                    keyword_store=self.keyword_store,
                    chunker=self.chunker,
                    embedder=self.embedder,
                )
                bootstrap_indexer.bootstrap(workflow_id=workflow_id)
                return

            self._ensure_loaded()
            invalidator = IndexInvalidator(self.vector_store, self.keyword_store)

            chunk_start = time.time()

            # 1. Chunk added, modified, and renamed files
            file_new_chunks: dict[str, list[Any]] = {}

            def process_file_chunks(file_path: str) -> list[Any]:
                full_path = self.repository_path / file_path
                if not full_path.is_file() or not self.chunker.should_process(full_path):
                    return []
                try:
                    content = load_text_file(full_path)
                    return self.chunker.chunk_file(
                        file_path,
                        content,
                        repository=self.repository_name,
                        commit_sha=self.commit_sha,
                    )
                except Exception as e:
                    logger.error("Failed to chunk file %s: %s", file_path, e)
                    return []

            for f in added_files:
                file_new_chunks[f] = process_file_chunks(f)
            for f in modified_files:
                file_new_chunks[f] = process_file_chunks(f)
            for old_path, new_path in renamed_files.items():
                file_new_chunks[new_path] = process_file_chunks(new_path)

            # 2. Hash Comparison & Change Detection
            chunks_to_embed = []
            new_chunk_ids_by_file: dict[str, set[str]] = {}
            skipped_count = 0
            added_count = 0
            updated_count = 0
            restored_count = 0

            for f, chunks in file_new_chunks.items():
                new_chunk_ids_by_file[f] = {c.metadata.chunk_id for c in chunks}
                for chunk in chunks:
                    chunk_id = chunk.metadata.chunk_id
                    existing = self.vector_store.get_chunk(chunk_id)

                    if existing is not None:
                        # Check if contents are identical
                        if existing.metadata.content_hash == chunk.metadata.content_hash:
                            # Skipped embedding! Restore if soft deleted.
                            if chunk_id in self.vector_store._deleted_chunk_ids:
                                invalidator.restore(chunk_id)
                                restored_count += 1
                            else:
                                skipped_count += 1
                            continue
                        else:
                            # Modified content, invalidate old and enqueue new
                            invalidator.invalidate(chunk_id)
                            chunks_to_embed.append(chunk)
                            updated_count += 1
                    else:
                        # New chunk entirely
                        chunks_to_embed.append(chunk)
                        added_count += 1

            # 3. Soft delete obsolete chunks
            deleted_count = 0
            files_to_clean = deleted_files + modified_files + list(renamed_files.keys())
            for f in files_to_clean:
                old_chunks = self.vector_store.get_chunks_by_file(f)
                new_ids = new_chunk_ids_by_file.get(f, set())
                for old_c in old_chunks:
                    if old_c.metadata.chunk_id not in new_ids:
                        invalidator.invalidate(old_c.metadata.chunk_id)
                        deleted_count += 1

            chunk_time = time.time() - chunk_start

            # 4. Generate Embeddings
            embed_start = time.time()
            embedded_chunks = []
            if chunks_to_embed:
                embedded_chunks = self.embedder.embed_chunks(chunks_to_embed, workflow_id=workflow_id) if workflow_id else self.embedder.embed_chunks(chunks_to_embed)
            embed_time = time.time() - embed_start

        # 5. Update Vector Store
            faiss_start = time.time()
            if embedded_chunks:
                self.vector_store.add_batch(embedded_chunks)
            faiss_time = time.time() - faiss_start

            # 6. Update Keyword Store
            bm25_start = time.time()
            if embedded_chunks:
                for chunk in embedded_chunks:
                    self.keyword_store._append_document(chunk)
                self.keyword_store._rebuild_bm25()
            bm25_time = time.time() - bm25_start

            # 7. Update Dependency Graph
            graph_start = time.time()
            added_dict = {}
            modified_dict = {}

            for file_path in added_files:
                full_path = self.repository_path / file_path
                if full_path.is_file() and self.chunker.should_process(full_path):
                    added_dict[file_path] = load_text_file(full_path)

            for file_path in modified_files:
                full_path = self.repository_path / file_path
                if full_path.is_file() and self.chunker.should_process(full_path):
                    modified_dict[file_path] = load_text_file(full_path)

            for old_path, new_path in renamed_files.items():
                full_path = self.repository_path / new_path
                if full_path.is_file() and self.chunker.should_process(full_path):
                    modified_dict[new_path] = load_text_file(full_path)

            try:
                persistence = GraphPersistence()
                if persistence.graph_path.exists():
                    graph = persistence.load()
                    from rag.parsing.dependency_graph import DependencyGraphUpdater
                    updater = DependencyGraphUpdater()
                    graph = updater.apply_changes(
                        graph,
                        added=added_dict,
                        modified=modified_dict,
                        deleted=deleted_files,
                        renamed=renamed_files,
                    )
                    self._graph_to_persist = graph
                else:
                    self._graph_to_persist = None
            except Exception as e:
                logger.error("Failed to update dependency graph: %s", e)
                self._graph_to_persist = None

            graph_time = time.time() - graph_start

            # 8. Persist Indexes with Transaction safety
            persist_start = time.time()
            self.refresh_indexes()
            persist_time = time.time() - persist_start

            # Check physical rebuild threshold
            if invalidator.needs_rebuild():
                logger.info("Physical rebuild threshold exceeded. Running physical purge cleanup...")
                invalidator.cleanup()
                self.refresh_indexes()

            total_time = time.time() - start_time

            logger.info(
                "Incremental update finished:\n"
                "  Repository: %s\n"
                "  Chunks Added: %d\n"
                "  Chunks Updated: %d\n"
                "  Chunks Restored: %d\n"
                "  Chunks Skipped: %d\n"
                "  Chunks Deleted: %d\n"
                "  Chunking/Diff Time: %.2fs\n"
                "  Embedding Time: %.2fs\n"
                "  FAISS Update Time: %.2fs\n"
                "  BM25 Update Time: %.2fs\n"
                "  Graph Time: %.2fs\n"
                "  Persist Time: %.2fs\n"
                "  Total Time: %.2fs",
                self.repository_name,
                added_count,
                updated_count,
                restored_count,
                skipped_count,
                deleted_count,
                chunk_time,
                embed_time,
                faiss_time,
                bm25_time,
                graph_time,
                persist_time,
                total_time,
            )

        except Exception as e:
            if workflow_id:
                from rag.pipeline.events import PipelineFailed
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineFailed(workflow_id, str(e)))
                except Exception:
                    pass
            raise e

    def insert_chunks(self, chunks: list[Any]) -> None:
        """
        Inserts new chunks programmatically.
        """
        self._ensure_loaded()
        unembedded = [c for c in chunks if not c.has_embedding]
        if unembedded:
            embedded = self.embedder.embed_chunks(unembedded)
            embedded_map = {c.metadata.chunk_id: c for c in embedded}
            chunks = [embedded_map.get(c.metadata.chunk_id, c) for c in chunks]

        self.vector_store.add_batch(chunks)
        for chunk in chunks:
            self.keyword_store._append_document(chunk)
        self.keyword_store._rebuild_bm25()
        self.refresh_indexes()

    def update_chunks(self, chunks: list[Any]) -> None:
        """
        Updates existing chunks programmatically.
        """
        self._ensure_loaded()
        for chunk in chunks:
            self.remove_chunks([chunk.metadata.chunk_id])
        self.insert_chunks(chunks)

    def remove_chunks(self, chunk_ids: list[str]) -> None:
        """
        Removes chunks by ID programmatically.
        """
        self._ensure_loaded()
        invalidator = IndexInvalidator(self.vector_store, self.keyword_store)
        for chunk_id in chunk_ids:
            invalidator.invalidate(chunk_id)
        self.refresh_indexes()

    def sync(self) -> None:
        """
        Saves metadata, checks and repairs active chunk sets discrepancy.
        """
        self._ensure_loaded()
        invalidator = IndexInvalidator(self.vector_store, self.keyword_store)

        v_ids = set(self.vector_store._chunks.keys()) - self.vector_store._deleted_chunk_ids
        k_ids = set(self.keyword_store._chunk_ids) - self.keyword_store._deleted_chunk_ids

        if v_ids != k_ids:
            logger.warning(
                "Index discrepancy found. VectorStore has %d active chunks, KeywordStore has %d.",
                len(v_ids),
                len(k_ids),
            )
            v_only = v_ids - k_ids
            k_only = k_ids - v_ids

            # Repair
            for cid in v_only:
                chunk = self.vector_store.get_chunk(cid)
                if chunk:
                    logger.info("Repairing: Appending %s to BM25 store", cid)
                    self.keyword_store._append_document(chunk)

            for cid in k_only:
                logger.info("Repairing: Soft-deleting %s from BM25 store", cid)
                self.keyword_store.delete(cid, soft=True)

            if v_only or k_only:
                self.keyword_store._rebuild_bm25()
                self.refresh_indexes()
                logger.info("Consistency repair complete.")
        else:
            logger.info("Indexes are fully synchronized.")

    def refresh_indexes(self) -> None:
        """
        Saves indexing stores to disk with transaction support.

        For Pinecone: vectors are already in the cloud; only the sidecar,
        BM25, and dependency graph need saving locally.
        For FAISS: the full transactional file-backup logic runs.
        """
        persistence = GraphPersistence()
        is_pinecone = settings.vector_store_backend.strip().lower() == "pinecone"

        if is_pinecone:
            try:
                self.vector_store.save()   # sidecar with full chunk content
                self.keyword_store.save()

                if hasattr(self, "_graph_to_persist") and self._graph_to_persist:
                    persistence.save(self._graph_to_persist)

                # Write embedding model info
                info = {
                    "model_name": self.embedder.model.model_name(),
                    "model_version": self.embedder.model.model_version(),
                }
                self._model_info_path().write_text(
                    json.dumps(info, indent=2), encoding="utf-8"
                )
            except Exception as e:
                logger.error(
                    "Failed to refresh Pinecone indexes. Error: %s", e
                )
                raise RuntimeError(f"Incremental Pinecone refresh failed: {e}") from e
            return

        # FAISS backend — transactional file backup
        paths_to_backup = [
            self.vector_store.index_path,
            self.vector_store.metadata_path,
            self.keyword_store.index_path,
            self.keyword_store.metadata_path,
            persistence.graph_path,
            self._model_info_path(),
        ]

        backups = []
        try:
            # Create backups
            for path in paths_to_backup:
                if path.exists():
                    bak_path = path.with_suffix(path.suffix + ".bak")
                    shutil.copy2(path, bak_path)
                    backups.append((path, bak_path))

            # Save stores
            self.vector_store.save()
            self.keyword_store.save()

            if hasattr(self, "_graph_to_persist") and self._graph_to_persist:
                persistence.save(self._graph_to_persist)

            # Write model name and version
            info = {
                "model_name": self.embedder.model.model_name(),
                "model_version": self.embedder.model.model_version(),
            }
            self._model_info_path().write_text(
                json.dumps(info, indent=2), encoding="utf-8"
            )

            # Clean backups
            for _, bak_path in backups:
                if bak_path.exists():
                    bak_path.unlink()

        except Exception as e:
            logger.error("Failed to refresh indexes. Restoring transaction. Error: %s", e)
            for orig_path, bak_path in backups:
                if bak_path.exists():
                    if orig_path.exists():
                        orig_path.unlink()
                    shutil.move(bak_path, orig_path)

            try:
                self.vector_store.load()
            except Exception:
                pass
            try:
                self.keyword_store.load()
            except Exception:
                pass
            raise RuntimeError(f"Incremental refresh failed: {e}") from e

    def statistics(self) -> dict[str, Any]:
        """
        Returns stats for the index structures.
        """
        self._ensure_loaded()
        v_stats = self.vector_store.statistics()
        k_stats = self.keyword_store.statistics()
        return {
            "total_chunks": v_stats.total_vectors,
            "active_chunks": v_stats.active_vectors,
            "deleted_chunks": v_stats.deleted_vectors,
            "bm25_documents": k_stats.total_documents,
        }
