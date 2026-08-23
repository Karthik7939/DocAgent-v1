"""
RAG pipeline workflow and logging manager.

Updates Pydantic/dataclass states on disk, logs workflow progress,
and checks cancellation tokens.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from rag.pipeline.events import (
    ChunkCreated,
    EmbeddingGenerated,
    IndexingStarted,
    ParsingStarted,
    PipelineCompleted,
    PipelineEvent,
    PipelineFailed,
    PipelineStarted,
    RetrievalFinished,
    RetrievalStarted,
)
from workflow.workflow_manager import WorkflowManager
from workflow.workflow_state import WorkflowState


class PipelineCancelled(Exception):
    """Raised when a RAG pipeline execution is cancelled by the user."""
    pass


def get_workflow_manager() -> WorkflowManager:
    """Returns an instance of WorkflowManager pointing to the configured workflow dir."""
    return WorkflowManager(settings.workflow_path)


def append_log(workflow_id: str, message: str) -> None:
    """Appends a log line to logs/{workflow_id}.log."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{workflow_id}.log"
    timestamp = datetime.utcnow().isoformat()
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def read_logs(workflow_id: str, limit: int = 50) -> list[str]:
    """Reads the last N lines of the log file for the specified workflow."""
    log_file = Path("logs") / f"{workflow_id}.log"
    if not log_file.exists():
        return []
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return [line.strip() for line in lines[-limit:]]


def check_cancelled(workflow_id: str) -> None:
    """Loads workflow state from disk and raises PipelineCancelled if is_cancelled is True."""
    manager = get_workflow_manager()
    state = manager.load_workflow(workflow_id)
    if state and state.is_cancelled:
        append_log(workflow_id, "Pipeline run cancelled by user request.")
        raise PipelineCancelled("Pipeline execution cancelled.")


def handle_event(event: PipelineEvent) -> None:
    """Handles an incoming PipelineEvent, updating the workflow state on disk."""
    manager = get_workflow_manager()
    state = manager.load_workflow(event.workflow_id)
    if not state:
        return

    # Process status and logging by event class
    if isinstance(event, PipelineStarted):
        state.rag_stage = event.stage
        state.rag_progress = 2
        append_log(
            event.workflow_id,
            f"Pipeline started for repository '{event.repository_name}' at commit {event.commit_sha}."
        )

    elif isinstance(event, ParsingStarted):
        state.rag_stage = event.stage
        state.rag_progress = 5
        state.rag_total_files = event.total_files
        append_log(
            event.workflow_id,
            f"Parsing files started. Total files detected: {event.total_files}."
        )

    elif isinstance(event, ChunkCreated):
        state.rag_stage = event.stage
        state.rag_current_file = event.file_path
        state.rag_current_file_index = event.file_index
        state.rag_total_files = event.total_files
        if event.total_files > 0:
            # Map chunking from 5% to 65% progress
            state.rag_progress = int((event.file_index / event.total_files) * 60) + 5
        append_log(
            event.workflow_id,
            f"Chunked [{event.file_index}/{event.total_files}]: {event.file_path} -> generated {event.chunks_count} chunks."
        )

    elif isinstance(event, EmbeddingGenerated):
        state.rag_stage = event.stage
        if event.total_chunks > 0:
            # Map embedding from 65% to 85% progress
            state.rag_progress = int((event.chunk_index / event.total_chunks) * 20) + 65
        append_log(
            event.workflow_id,
            f"Generated embeddings batch for chunk index [{event.chunk_index}/{event.total_chunks}]."
        )

    elif isinstance(event, IndexingStarted):
        state.rag_stage = event.stage
        state.rag_progress = 85
        append_log(event.workflow_id, "Serializing new chunks to FAISS and BM25 index stores.")

    elif isinstance(event, RetrievalStarted):
        state.rag_stage = event.stage
        state.rag_progress = 90
        append_log(event.workflow_id, "Running semantic search and dependency expansion queries.")

    elif isinstance(event, RetrievalFinished):
        state.rag_stage = event.stage
        state.rag_progress = 95
        append_log(event.workflow_id, "Retrieval completed. Bundling ContextPackage.")

    elif isinstance(event, PipelineCompleted):
        state.rag_stage = event.stage
        state.rag_progress = 100
        append_log(
            event.workflow_id,
            f"Pipeline executed successfully in {event.execution_time_ms:.2f}ms."
        )

    elif isinstance(event, PipelineFailed):
        state.rag_stage = event.stage
        state.rag_progress = 100
        append_log(
            event.workflow_id,
            f"Pipeline execution FAILED. Error: {event.error_message}"
        )

    # Save modified state back to disk
    manager.save_workflow(state)
