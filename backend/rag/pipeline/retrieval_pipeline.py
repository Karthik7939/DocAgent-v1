"""
Retrieval pipeline module.

Fetches ranked code context chunks and wraps them in a ContextPackage.
"""

from __future__ import annotations

from datetime import datetime
import time
from typing import Any, Optional

from rag.embeddings.embedder import Embedder
from rag.retrieval.dependency_retriever import DependencyRetriever
from rag.retrieval.hybrid_retriever import HybridRetriever
from rag.retrieval.keyword_store import KeywordStore
from rag.retrieval.vector_store_factory import get_vector_store
from rag.schemas.context import ContextMetadata, ContextPackage
from rag.schemas.query import SemanticQuery
from rag.schemas.retrieval import RetrievalResults
from rag.utils import get_logger

logger = get_logger(__name__)


class ContextBuilder:
    """
    Constructs the final ContextPackage model from retrieval results and metadata.
    """

    def build(
        self,
        repository: str,
        commit_sha: str,
        query: SemanticQuery,
        retrieval_results: RetrievalResults,
        changed_files: list[str],
        retrieval_time_ms: float = 0.0,
    ) -> ContextPackage:
        """
        Builds the ContextPackage object.
        """
        metadata = ContextMetadata(
            generated_at=datetime.utcnow(),
            retrieval_time_ms=retrieval_time_ms,
            total_changed_files=len(changed_files),
            total_retrieved_chunks=retrieval_results.total_results,
        )
        return ContextPackage(
            repository=repository,
            commit_sha=commit_sha,
            query=query,
            retrieval_results=retrieval_results,
            changed_files=changed_files,
            metadata=metadata,
        )


class RetrievalPipeline:
    """
    Coordinates context extraction and packaging using HybridRetriever and ContextBuilder.
    """

    def __init__(
        self,
        repository: str = "",
        vector_store=None,
        keyword_store: Optional[KeywordStore] = None,
        dependency_retriever: Optional[DependencyRetriever] = None,
        embedder: Optional[Embedder] = None,
    ) -> None:
        # repository is used to scope the vector store to the right namespace
        self._repository = repository
        self.vector_store = vector_store or get_vector_store(repository=repository)
        self.keyword_store = keyword_store or KeywordStore()

        # Load dependency graph & retriever if not provided
        if dependency_retriever is None:
            try:
                from rag.parsing.dependency_graph import DependencyGraphQuery, GraphPersistence
                persistence = GraphPersistence()
                graph = persistence.load()
                graph_query = DependencyGraphQuery(graph)
                self.dependency_retriever = DependencyRetriever(graph_query)
            except Exception as e:
                logger.warning("Failed to initialize dependency retriever: %s", e)
                self.dependency_retriever = None
        else:
            self.dependency_retriever = dependency_retriever

        self.embedder = embedder or Embedder()

        # Load store data in memory
        try:
            self.vector_store.load()
        except Exception:
            pass
        try:
            self.keyword_store.load()
        except Exception:
            pass

        if self.dependency_retriever:
            self.retriever = HybridRetriever(
                vector_store=self.vector_store,
                keyword_store=self.keyword_store,
                dependency_retriever=self.dependency_retriever,
                embedder=self.embedder,
            )
        else:
            self.retriever = None

    def retrieve(self, query: SemanticQuery, workflow_id: Optional[str] = None) -> ContextPackage:
        """
        Retrieves context chunks and compiles them into a ContextPackage.
        """
        start_time = time.time()

        if workflow_id:
            from rag.pipeline.events import RetrievalStarted
            from rag.pipeline.manager import handle_event
            try:
                handle_event(RetrievalStarted(workflow_id))
            except Exception:
                pass

        # Handle lazy initialization of retriever
        if self.retriever is None:
            try:
                from rag.parsing.dependency_graph import DependencyGraphQuery, GraphPersistence
                persistence = GraphPersistence()
                graph = persistence.load()
                graph_query = DependencyGraphQuery(graph)
                self.dependency_retriever = DependencyRetriever(graph_query)
                self.retriever = HybridRetriever(
                    vector_store=self.vector_store,
                    keyword_store=self.keyword_store,
                    dependency_retriever=self.dependency_retriever,
                    embedder=self.embedder,
                )
            except Exception as e:
                logger.error("Failed to lazily initialize hybrid retriever: %s", e)
                builder = ContextBuilder()
                return builder.build(
                    repository=query.repository,
                    commit_sha=query.commit_sha,
                    query=query,
                    retrieval_results=RetrievalResults(),
                    changed_files=query.changed_files,
                    retrieval_time_ms=0.0,
                )

        # Execute retrieval
        results = self.retriever.retrieve_for_change(query)
        elapsed_ms = (time.time() - start_time) * 1000

        if workflow_id:
            from rag.pipeline.events import RetrievalFinished
            from rag.pipeline.manager import handle_event
            try:
                handle_event(RetrievalFinished(workflow_id))
            except Exception:
                pass

        # Build context package
        builder = ContextBuilder()
        return builder.build(
            repository=query.repository,
            commit_sha=query.commit_sha,
            query=query,
            retrieval_results=results,
            changed_files=query.changed_files,
            retrieval_time_ms=elapsed_ms,
        )

    def build_context(
        self,
        repository: str,
        commit_sha: str,
        query: SemanticQuery,
        retrieval_results: RetrievalResults,
        changed_files: list[str],
        retrieval_time_ms: float = 0.0,
    ) -> ContextPackage:
        """
        Explicit context packaging alias.
        """
        builder = ContextBuilder()
        return builder.build(
            repository=repository,
            commit_sha=commit_sha,
            query=query,
            retrieval_results=retrieval_results,
            changed_files=changed_files,
            retrieval_time_ms=retrieval_time_ms,
        )

    def statistics(self) -> dict[str, Any]:
        """
        Returns retrieval statistics.
        """
        if self.retriever:
            stats = self.retriever.statistics()
            return {
                "faiss_results": stats.faiss_results,
                "bm25_results": stats.bm25_results,
                "dependency_results": stats.dependency_results,
                "merged_results": stats.merged_results,
                "retrieval_time_ms": stats.retrieval_time_ms,
            }
        return {}
