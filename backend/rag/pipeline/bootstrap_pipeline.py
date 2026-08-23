"""
Bootstrap pipeline module.

Orchestrates full building of all RAG indices from scratch.
"""

from __future__ import annotations

from typing import Any, Optional

from rag.indexing.bootstrap import BootstrapIndexer
from rag.retrieval.keyword_store import KeywordStore
from rag.retrieval.vector_store_factory import get_vector_store
from rag.utils import get_logger

logger = get_logger(__name__)


class BootstrapPipeline:
    """
    Coordinates initializing all indexes for a repository from scratch.
    """

    def __init__(
        self,
        repository_path: str,
        repository_name: str,
        commit_sha: str,
        vector_store=None,
        keyword_store: Optional[KeywordStore] = None,
    ) -> None:
        self.repository_path = repository_path
        self.repository_name = repository_name
        self.commit_sha = commit_sha

        self.indexer = BootstrapIndexer(
            repository_path=repository_path,
            repository_name=repository_name,
            commit_sha=commit_sha,
            vector_store=vector_store or get_vector_store(repository=repository_name),
            keyword_store=keyword_store,
        )

    def run(self, workflow_id: Optional[str] = None) -> None:
        """
        Orchestrates pipeline execution.
        """
        self.initialize_repository(workflow_id=workflow_id)

    def initialize_repository(self, workflow_id: Optional[str] = None) -> None:
        """
        Performs the bootstrapping.
        """
        logger.info("Initializing repository: %s", self.repository_name)
        self.indexer.bootstrap(workflow_id=workflow_id)

    def statistics(self) -> dict[str, Any]:
        """
        Returns indexing statistics.
        """
        return self.indexer.statistics()
