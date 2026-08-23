"""
app/models/workflow.py
-----------------------
Pydantic models for workflow data exchanged between layers.

These models are used for:
- Returning workflow data from service functions to API handlers
- Serialising workflow state to JSON
- Deserialising workflow state from JSON
"""

from typing import Optional

from pydantic import BaseModel, Field

from app.core.constants import WorkflowStatus


class WorkflowResponse(BaseModel):
    """Model returned in the HTTP response after a webhook is processed.

    This is the public-facing representation — it omits internal fields
    that are not relevant to the caller.
    """

    status: str = Field(..., description="Response status: 'success' or 'error'.")
    workflow_id: str = Field(..., description="Unique identifier for this workflow run.")
    repository: str = Field(..., description="Repository name.")
    branch: str = Field(..., description="Branch that was pushed to.")


class WorkflowStateModel(BaseModel):
    """Full workflow state persisted to a JSON file.

    This model mirrors workflow/workflow_state.py (dataclass) but as a
    Pydantic model so it can be easily serialised / deserialised.
    """

    workflow_id: str = Field(..., description="UUID identifying this workflow run.")
    repository: str = Field(..., description="Repository full name (owner/repo).")
    branch: str = Field(..., description="Branch name.")
    status: WorkflowStatus = Field(..., description="Current lifecycle status.")
    commit_sha: str = Field(..., description="HEAD commit SHA after the push.")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp when the workflow was created.")
    changed_files: list[str] = Field(
        default_factory=list,
        description="All files touched (added + modified + removed) in the push.",
    )
    error_message: Optional[str] = Field(
        None,
        description="Human-readable error detail when status is 'failed'.",
    )

    def to_dict(self) -> dict:
        """Return a plain dictionary suitable for JSON serialisation.

        Returns:
            dict: All fields serialised, with enum values as strings.
        """
        return self.model_dump(mode="json")
