"""
workflow/workflow_manager.py
-----------------------------
High-level workflow lifecycle manager.

Responsibilities:
- Start a new workflow (creates WorkflowState with PENDING status)
- Mark a workflow as in-progress, completed, or failed
- Persist workflow state to disk via file_utils
- Load a workflow from disk
- Delegate all filesystem operations to utils/file_utils.py
"""

import logging
from pathlib import Path
from typing import Optional

from app.core.constants import WorkflowStatus, WORKFLOW_FILE_EXTENSION
from utils.file_utils import read_json, write_json, delete_file, file_exists
from utils.helpers import generate_uuid, generate_timestamp
from workflow.workflow_state import WorkflowState

logger = logging.getLogger(__name__)


class WorkflowManager:
    """Manages the full lifecycle of workflow execution state.

    Args:
        workflow_dir: Path to the directory where workflow JSON files are stored.
    """

    def __init__(self, workflow_dir: str) -> None:
        self._workflow_dir = Path(workflow_dir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _workflow_file_path(self, workflow_id: str) -> str:
        """Build the absolute path for a workflow JSON file.

        Args:
            workflow_id: The UUID of the workflow.

        Returns:
            str: Full path to the JSON file.
        """
        return str(self._workflow_dir / f"{workflow_id}{WORKFLOW_FILE_EXTENSION}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_workflow(
        self,
        repository: str,
        branch: str,
        commit_sha: str,
        changed_files: Optional[list[str]] = None,
    ) -> WorkflowState:
        """Create a new workflow in PENDING status.

        Args:
            repository:    Full repository name, e.g. 'owner/repo'.
            branch:        Branch that was pushed to.
            commit_sha:    HEAD commit SHA.
            changed_files: Files touched by the push.

        Returns:
            WorkflowState: The newly created (unsaved) workflow state.
        """
        state = WorkflowState(
            workflow_id=generate_uuid(),
            repository=repository,
            branch=branch,
            status=WorkflowStatus.PENDING,
            commit_sha=commit_sha,
            timestamp=generate_timestamp(),
            changed_files=changed_files or [],
        )
        logger.info("Workflow created: id=%s  repo=%s  branch=%s", state.workflow_id, repository, branch)
        return state

    def complete_workflow(self, state: WorkflowState) -> WorkflowState:
        """Transition workflow to COMPLETED and save to disk.

        Args:
            state: The current workflow state object.

        Returns:
            WorkflowState: Updated state after marking as completed.
        """
        state.mark_completed()
        self.save_workflow(state)
        logger.info("Workflow completed: id=%s", state.workflow_id)
        return state

    def fail_workflow(self, state: WorkflowState, reason: str) -> WorkflowState:
        """Transition workflow to FAILED, record the reason, and save to disk.

        Args:
            state:  The current workflow state object.
            reason: Human-readable failure description.

        Returns:
            WorkflowState: Updated state after marking as failed.
        """
        state.mark_failed(reason)
        self.save_workflow(state)
        logger.error("Workflow failed: id=%s  reason=%s", state.workflow_id, reason)
        return state

    def update_progress(self, state: WorkflowState) -> WorkflowState:
        """Transition workflow to IN_PROGRESS and save to disk.

        Args:
            state: The current workflow state object.

        Returns:
            WorkflowState: Updated state after marking as in-progress.
        """
        state.mark_in_progress()
        self.save_workflow(state)
        logger.info("Workflow in progress: id=%s", state.workflow_id)
        return state

    def save_workflow(self, state: WorkflowState) -> None:
        """Persist a workflow state object to a JSON file.

        Args:
            state: The workflow state to serialise and write.
        """
        file_path = self._workflow_file_path(state.workflow_id)
        write_json(file_path, state.to_dict())
        logger.info("Workflow saved: path=%s", file_path)

    def load_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        """Read a workflow JSON file and reconstruct a WorkflowState.

        Args:
            workflow_id: UUID of the workflow to load.

        Returns:
            WorkflowState: The deserialised state, or None if not found.
        """
        file_path = self._workflow_file_path(workflow_id)
        if not file_exists(file_path):
            logger.warning("Workflow file not found: %s", file_path)
            return None

        data = read_json(file_path)
        state = WorkflowState(
            workflow_id=data["workflow_id"],
            repository=data["repository"],
            branch=data["branch"],
            status=WorkflowStatus(data["status"]),
            commit_sha=data["commit_sha"],
            timestamp=data["timestamp"],
            changed_files=data.get("changed_files", []),
            error_message=data.get("error_message"),
            is_cancelled=data.get("is_cancelled", False),
            rag_stage=data.get("rag_stage", "queued"),
            rag_progress=data.get("rag_progress", 0),
            rag_current_file=data.get("rag_current_file", ""),
            rag_current_file_index=data.get("rag_current_file_index", 0),
            rag_total_files=data.get("rag_total_files", 0),
            semantic_query=data.get("semantic_query", {}),
            ast_details=data.get("ast_details", []),
            retrieved_chunks=data.get("retrieved_chunks", []),
        )
        logger.info("Workflow loaded: id=%s", workflow_id)
        return state

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow JSON file from disk.

        Args:
            workflow_id: UUID of the workflow to delete.

        Returns:
            bool: True if deleted, False if the file did not exist.
        """
        file_path = self._workflow_file_path(workflow_id)
        deleted = delete_file(file_path)
        if deleted:
            logger.info("Workflow deleted: id=%s", workflow_id)
        return deleted
