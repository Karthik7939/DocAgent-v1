"""
Pipeline lifecycle events.

Used to decouple execution steps in RAG from status reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PipelineEvent:
    """Base class for RAG pipeline tracking events."""
    workflow_id: str


@dataclass
class PipelineStarted(PipelineEvent):
    """Event indicating the pipeline process has started."""
    repository_name: str
    commit_sha: str
    stage: str = "started"


@dataclass
class ParsingStarted(PipelineEvent):
    """Event indicating source code parsing has started."""
    total_files: int
    stage: str = "parsing"


@dataclass
class ChunkCreated(PipelineEvent):
    """Event fired when a source file is successfully chunked."""
    file_path: str
    file_index: int
    total_files: int
    chunks_count: int
    stage: str = "chunking"


@dataclass
class EmbeddingGenerated(PipelineEvent):
    """Event indicating a batch of embeddings has been computed."""
    chunk_index: int
    total_chunks: int
    stage: str = "embedding"


@dataclass
class IndexingStarted(PipelineEvent):
    """Event indicating search indexing (FAISS/BM25) has started."""
    stage: str = "indexing"


@dataclass
class RetrievalStarted(PipelineEvent):
    """Event indicating semantic query context retrieval has started."""
    stage: str = "retrieval"


@dataclass
class RetrievalFinished(PipelineEvent):
    """Event indicating context query retrieval is completed."""
    stage: str = "retrieval_finished"


@dataclass
class PipelineCompleted(PipelineEvent):
    """Event indicating full pipeline execution success."""
    execution_time_ms: float
    stage: str = "completed"


@dataclass
class PipelineFailed(PipelineEvent):
    """Event indicating pipeline failure."""
    error_message: str
    stage: str = "error"
