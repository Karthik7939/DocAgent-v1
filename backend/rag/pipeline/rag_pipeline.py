"""
RAG pipeline module.

Master orchestrator combining incremental indexing and retrieval pipeline execution.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from rag.pipeline.incremental_pipeline import IncrementalPipeline
from rag.pipeline.retrieval_pipeline import RetrievalPipeline
from rag.retrieval.keyword_store import KeywordStore
from rag.retrieval.vector_store_factory import get_vector_store
from rag.schemas.context import ContextPackage
from rag.utils import get_logger

logger = get_logger(__name__)


class RAGPipeline:
    """
    Master pipeline coordinating commit-triggered updates and context retrieval.
    """

    def __init__(
        self,
        repository_path: str,
        repository_name: str,
        vector_store=None,
        keyword_store: Optional[KeywordStore] = None,
    ) -> None:
        self.repository_path = repository_path
        self.repository_name = repository_name
        self.vector_store = vector_store or get_vector_store(repository=repository_name)
        self.keyword_store = keyword_store or KeywordStore(repository=repository_name)
        self._stats: dict[str, Any] = {}

    def run(
        self,
        old_commit_sha: Optional[str],
        new_commit_sha: str,
        workflow_id: Optional[str] = None,
    ) -> PipelineResult:
        """
        Orchestrates pipeline execution.
        """
        return self.execute(old_commit_sha, new_commit_sha, workflow_id)

    def execute(
        self,
        old_commit_sha: Optional[str],
        new_commit_sha: str,
        workflow_id: Optional[str] = None,
    ) -> PipelineResult:
        """
        Runs incremental updates followed by retrieving the updated context package.
        """
        logger.info(
            "Executing master RAG pipeline for repo '%s' (%s -> %s)",
            self.repository_name,
            old_commit_sha,
            new_commit_sha,
        )
        start_time = time.perf_counter()

        # Import locally to avoid circular dependency
        from rag.schemas.context import PipelineResult

        try:
            if workflow_id:
                from rag.pipeline.events import PipelineStarted
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineStarted(workflow_id, self.repository_name, new_commit_sha))
                except Exception:
                    pass

            # 1. Run incremental pipeline (commit webhook processing & index update)
            inc_start = time.perf_counter()
            inc_pipeline = IncrementalPipeline(
                repository_path=self.repository_path,
                repository_name=self.repository_name,
                old_commit_sha=old_commit_sha,
                new_commit_sha=new_commit_sha,
                vector_store=self.vector_store,
                keyword_store=self.keyword_store,
            )
            query = inc_pipeline.run(workflow_id=workflow_id)
            if workflow_id:
                from rag.pipeline.manager import get_workflow_manager
                try:
                    manager = get_workflow_manager()
                    state = manager.load_workflow(workflow_id)
                    if state:
                        state.semantic_query = query.model_dump(mode="json")
                        manager.save_workflow(state)
                except Exception as exc:
                    logger.warning("Failed to persist generated SemanticQuery: %s", exc)
            inc_elapsed = (time.perf_counter() - inc_start) * 1000

            # 2. Run retrieval pipeline to fetch context around the change
            ret_start = time.perf_counter()
            ret_pipeline = RetrievalPipeline(
                vector_store=self.vector_store,
                keyword_store=self.keyword_store,
            )
            if workflow_id:
                context_package = ret_pipeline.retrieve(query, workflow_id=workflow_id)
            else:
                context_package = ret_pipeline.retrieve(query)
            ret_elapsed = (time.perf_counter() - ret_start) * 1000

            if workflow_id:
                from rag.pipeline.manager import get_workflow_manager

                manager = get_workflow_manager()
                state = manager.load_workflow(workflow_id)
                if state:
                    state.retrieved_chunks = [
                        {
                            "rank": item.rank,
                            "file_path": item.file_path,
                            "chunk_id": item.chunk_id,
                            "symbol_name": item.chunk.metadata.symbol_name,
                            "language": item.chunk.metadata.language,
                            "score": item.similarity_score,
                            "source": item.retrieval_source.value,
                            "reason": item.retrieval_reason,
                        }
                        for item in context_package.retrieval_results.results
                    ]
                    manager.save_workflow(state)

            total_elapsed = (time.perf_counter() - start_time) * 1000

            # Save statistics
            self._stats = {
                "success": True,
                "incremental_time_ms": inc_elapsed,
                "retrieval_time_ms": ret_elapsed,
                "total_time_ms": total_elapsed,
                "retrieved_chunks": context_package.metadata.total_retrieved_chunks,
                "changed_files_count": len(context_package.changed_files),
            }

            logger.info(
                "RAG pipeline completed successfully in %.2fms. (Indexing: %.2fms, Retrieval: %.2fms)",
                total_elapsed,
                inc_elapsed,
                ret_elapsed,
            )

            if workflow_id:
                from rag.pipeline.events import PipelineCompleted
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineCompleted(workflow_id, total_elapsed))
                except Exception:
                    pass

            return PipelineResult(
                success=True,
                context_package=context_package,
                execution_time_ms=total_elapsed,
            )

        except Exception as e:
            logger.error("RAG pipeline failed during execution: %s", e)
            total_elapsed = (time.perf_counter() - start_time) * 1000
            self._stats = {
                "success": False,
                "error": str(e),
                "total_time_ms": total_elapsed,
            }
            if workflow_id:
                from rag.pipeline.events import PipelineFailed
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineFailed(workflow_id, str(e)))
                except Exception:
                    pass
            return PipelineResult(
                success=False,
                error=str(e),
                execution_time_ms=total_elapsed,
            )

    def status(self) -> dict[str, Any]:
        """
        Returns the pipeline status and statistics.
        """
        try:
            v_stats = self.vector_store.statistics()
            k_stats = self.keyword_store.statistics()
            stores_status = {
                "vector_store_active_chunks": v_stats.active_vectors,
                "keyword_store_active_documents": k_stats.active_documents,
            }
        except Exception:
            stores_status = {}

        return {
            "repository": self.repository_name,
            "last_run_stats": self._stats,
            "indexes_status": stores_status,
        }
