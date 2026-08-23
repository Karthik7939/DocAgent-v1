"""
services/workflow_service.py
-----------------------------
Service layer façade over WorkflowManager.

Responsibilities:
- Create a new workflow from parsed commit data
- Update an existing workflow
- Save a workflow to disk
- Load a workflow from disk
- Delete a workflow from disk
- Translate WorkflowState ↔ WorkflowStateModel (Pydantic) when needed
"""

import logging
from typing import Optional

from app.core.constants import WorkflowStatus
from app.models.workflow import WorkflowStateModel
from services.parser_service import ParsedCommitData
from workflow.workflow_manager import WorkflowManager
from workflow.workflow_state import WorkflowState

logger = logging.getLogger(__name__)


class WorkflowService:
    """Provides a service-layer API for workflow persistence operations.

    Args:
        workflow_manager: An initialised WorkflowManager instance.
    """

    def __init__(self, workflow_manager: WorkflowManager) -> None:
        self._manager = workflow_manager

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_workflow(self, parsed_data: ParsedCommitData) -> WorkflowState:
        """Initialise a new workflow from parsed commit data.

        The workflow is created in PENDING status and immediately
        transitioned to IN_PROGRESS, then saved.

        Args:
            parsed_data: The output of ParserService.parse().

        Returns:
            WorkflowState: The in-progress workflow state.
        """
        logger.info("Creating workflow for repo=%s  branch=%s", parsed_data.repository, parsed_data.branch)

        state = self._manager.start_workflow(
            repository=parsed_data.repository,
            branch=parsed_data.branch,
            commit_sha=parsed_data.commit_sha,
            changed_files=parsed_data.changed_files,
        )
        self._manager.update_progress(state)
        logger.info("Workflow created and in progress: id=%s", state.workflow_id)
        return state

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def complete_workflow(self, state: WorkflowState) -> WorkflowState:
        """Mark a workflow as successfully completed and persist it.

        Args:
            state: Current workflow state.

        Returns:
            WorkflowState: Updated state with status=COMPLETED.
        """
        return self._manager.complete_workflow(state)

    def fail_workflow(self, state: WorkflowState, reason: str) -> WorkflowState:
        """Mark a workflow as failed, record the reason, and persist it.

        Args:
            state:  Current workflow state.
            reason: Human-readable failure description.

        Returns:
            WorkflowState: Updated state with status=FAILED.
        """
        return self._manager.fail_workflow(state, reason)

    # ------------------------------------------------------------------
    # Save / Load / Delete
    # ------------------------------------------------------------------

    def save_workflow(self, state: WorkflowState) -> None:
        """Explicitly persist a workflow state to disk.

        Args:
            state: Workflow state to save.
        """
        self._manager.save_workflow(state)

    def load_workflow(self, workflow_id: str) -> Optional[WorkflowState]:
        """Load a workflow from disk by its UUID.

        Args:
            workflow_id: UUID of the workflow to load.

        Returns:
            WorkflowState if found, else None.
        """
        return self._manager.load_workflow(workflow_id)

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow JSON file from disk.

        Args:
            workflow_id: UUID of the workflow to delete.

        Returns:
            bool: True if the file was deleted, False if not found.
        """
        return self._manager.delete_workflow(workflow_id)

    # ------------------------------------------------------------------
    # Model conversion
    # ------------------------------------------------------------------

    @staticmethod
    def to_pydantic_model(state: WorkflowState) -> WorkflowStateModel:
        """Convert a WorkflowState dataclass to a WorkflowStateModel Pydantic model.

        Args:
            state: In-memory workflow state dataclass.

        Returns:
            WorkflowStateModel: Pydantic model suitable for serialisation.
        """
        return WorkflowStateModel(
            workflow_id=state.workflow_id,
            repository=state.repository,
            branch=state.branch,
            status=WorkflowStatus(state.status),
            commit_sha=state.commit_sha,
            timestamp=state.timestamp,
            changed_files=state.changed_files,
            error_message=state.error_message,
        )
