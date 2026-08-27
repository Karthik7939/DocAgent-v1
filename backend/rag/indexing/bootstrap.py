"""
Repository indexing bootstrapping.

Rebuilds all retrieval stores from scratch for a repository.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import time
from typing import Any, Optional

from rag.chunking.chunker import Chunker
from rag.config import settings
from rag.embeddings.embedder import Embedder
from rag.indexing.index_stats import write_index_stats
from rag.parsing.dependency_graph import DependencyGraph, DependencyGraphBuilder, GraphPersistence
from rag.retrieval.keyword_store import KeywordStore
from rag.retrieval.vector_store_factory import get_vector_store
from rag.utils import get_logger

logger = get_logger(__name__)


class BootstrapIndexer:
    """
    Builds the retrieval vector store, keyword index, and dependency graph from scratch.
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
        self._graph: Optional[DependencyGraph] = None
        self._chunks: list[Any] = []

    def bootstrap(self, workflow_id: Optional[str] = None) -> None:
        """
        Orchestrates full rebuild of all indexes.
        """
        start_time = time.time()

        try:
            if workflow_id:
                from rag.pipeline.events import PipelineStarted
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineStarted(workflow_id, self.repository_name, self.commit_sha))
                except Exception:
                    pass

            # 1. Chunker
            chunk_start = time.time()
            chunks = self.build_repository(workflow_id=workflow_id)
            chunk_time = time.time() - chunk_start

            # 2. Embedder
            embed_start = time.time()
            if chunks:
                chunks = self.embedder.embed_chunks(chunks, workflow_id=workflow_id) if workflow_id else self.embedder.embed_chunks(chunks)
            embed_time = time.time() - embed_start

            if workflow_id:
                from rag.pipeline.events import IndexingStarted
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(IndexingStarted(workflow_id))
                except Exception:
                    pass

            # 3. VectorStore
            faiss_start = time.time()
            self.build_vector_index(chunks)
            faiss_time = time.time() - faiss_start

            # 4. KeywordStore
            bm25_start = time.time()
            self.build_keyword_index(chunks)
            bm25_time = time.time() - bm25_start

            # 5. DependencyGraph
            graph_start = time.time()
            self.build_dependency_graph()
            graph_time = time.time() - graph_start

            # 6. Commit/Persist
            persist_start = time.time()
            self.persist()
            persist_time = time.time() - persist_start

            total_time = time.time() - start_time

            if workflow_id:
                from rag.pipeline.events import PipelineCompleted
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineCompleted(workflow_id, total_time * 1000))
                except Exception:
                    pass

            logger.info(
                "Bootstrap finished successfully:\n"
                "  Repository: %s\n"
                "  Total Chunks: %d\n"
                "  Chunking Time: %.2fs\n"
                "  Embedding Time: %.2fs\n"
                "  FAISS Time: %.2fs\n"
                "  BM25 Time: %.2fs\n"
                "  Graph Time: %.2fs\n"
                "  Persist Time: %.2fs\n"
                "  Total Time: %.2fs",
                self.repository_name,
                len(chunks),
                chunk_time,
                embed_time,
                faiss_time,
                bm25_time,
                graph_time,
                persist_time,
                total_time,
            )

            write_index_stats(
                self.repository_name,
                run_type="bootstrap",
                stats={
                    "chunk_count": len(chunks),
                    "chunk_time_seconds": round(chunk_time, 3),
                    "embed_time_seconds": round(embed_time, 3),
                    "faiss_time_seconds": round(faiss_time, 3),
                    "bm25_time_seconds": round(bm25_time, 3),
                    "graph_time_seconds": round(graph_time, 3),
                    "persist_time_seconds": round(persist_time, 3),
                    "total_time_seconds": round(total_time, 3),
                    "chunks_per_second": round(len(chunks) / total_time, 2) if total_time > 0 else 0.0,
                },
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

    def build_repository(self, workflow_id: Optional[str] = None) -> list[Any]:
        """
        Chunks the repository.
        """
        logger.info("Chunking repository files from path: %s", self.repository_path)
        if not self.repository_path.exists() or not self.repository_path.is_dir():
            logger.warning("Repository path does not exist or is not a directory. Bootstrapping empty repository.")
            self._chunks = []
            return []

        chunks, _ = self.chunker.chunk_repository(
            self.repository_path,
            repository_name=self.repository_name,
            commit_sha=self.commit_sha,
            workflow_id=workflow_id,
        )
        self._chunks = chunks
        return chunks

    def build_vector_index(self, chunks: list[Any]) -> None:
        """
        Rebuilds the FAISS vector index.
        """
        logger.info("Building vector index with %d chunks...", len(chunks))
        if chunks:
            self.vector_store.rebuild(chunks)
        else:
            # Create an empty index with the embedder's model dimension
            dim = self.embedder.model.dimension()
            self.vector_store.create(dimension=dim, repository=self.repository_name)

    def build_keyword_index(self, chunks: list[Any]) -> None:
        """
        Rebuilds the BM25 keyword index.
        """
        logger.info("Building keyword index with %d chunks...", len(chunks))
        self.keyword_store.index(chunks)

    def build_dependency_graph(self) -> None:
        """
        Builds the repository file-level dependency graph.
        """
        logger.info("Building dependency graph...")
        repo_dict = {}
        from rag.utils.file_loader import discover_files, load_text_file

        if self.repository_path.exists() and self.repository_path.is_dir():
            for file_path in discover_files(self.repository_path):
                if self.chunker.should_process(file_path):
                    relative_path = file_path.relative_to(self.repository_path).as_posix()
                    repo_dict[relative_path] = load_text_file(file_path)

        builder = DependencyGraphBuilder()
        self._graph = builder.build(
            repo_dict,
            self.repository_name,
            self.commit_sha,
        )

    def persist(self) -> None:
        """
        Commits all index updates with transaction safety.

        For Pinecone: vectors are already durable in the cloud.  Only the
        sidecar (full content), BM25, and dependency graph need local saving.
        For FAISS: the original file-backup transaction logic is used.
        """
        logger.info("Committing bootstrap indexes...")
        persistence = GraphPersistence()
        is_pinecone = settings.vector_store_backend.strip().lower() == "pinecone"

        if is_pinecone:
            # Pinecone backend — vectors are already in the cloud.
            # Save the sidecar (full chunk content) + BM25 + dependency graph.
            try:
                self.vector_store.save()     # writes local JSON sidecar
                self.keyword_store.save()
                if self._graph:
                    persistence.save(self._graph)
                logger.info("Bootstrap persisted (Pinecone sidecar + BM25 + graph).")
            except Exception as e:
                logger.error("Failed to persist Pinecone bootstrap data: %s", e)
                raise RuntimeError(f"Bootstrap persist failed: {e}") from e
            return

        # FAISS backend — use transactional file backup.
        paths_to_backup = [
            self.vector_store.index_path,
            self.vector_store.metadata_path,
            self.keyword_store.index_path,
            self.keyword_store.metadata_path,
            persistence.graph_path,
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
            if self._graph:
                persistence.save(self._graph)

            # Cleanup backup files
            for _, bak_path in backups:
                if bak_path.exists():
                    bak_path.unlink()

        except Exception as e:
            logger.error("Failed to commit indexes, rolling back transaction. Error: %s", e)
            # Restore backups
            for orig_path, bak_path in backups:
                if bak_path.exists():
                    if orig_path.exists():
                        orig_path.unlink()
                    shutil.move(bak_path, orig_path)

            # Reload stores in memory to discard corrupted changes
            try:
                self.vector_store.load()
            except Exception:
                pass
            try:
                self.keyword_store.load()
            except Exception:
                pass
            raise RuntimeError(f"Bootstrap transaction failed: {e}") from e

    def statistics(self) -> dict[str, Any]:
        """
        Returns indexing statistics.
        """
        v_stats = self.vector_store.statistics()
        k_stats = self.keyword_store.statistics()
        g_nodes = len(self._graph.nodes) if self._graph else 0
        g_edges = len(self._graph.edges) if self._graph else 0

        return {
            "total_chunks": v_stats.total_vectors,
            "active_chunks": v_stats.active_vectors,
            "deleted_chunks": v_stats.deleted_vectors,
            "keyword_documents": k_stats.total_documents,
            "graph_nodes": g_nodes,
            "graph_edges": g_edges,
        }
