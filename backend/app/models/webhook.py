"""
app/models/webhook.py
----------------------
Pydantic models for incoming GitHub webhook payloads.

These models validate the structure of the JSON body sent by GitHub on a
push event.  Only the fields this service actually needs are declared;
additional fields in the payload are silently ignored.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Owner(BaseModel):
    """Represents the owner of a GitHub repository."""

    name: str = Field(..., description="GitHub username or organisation name.")
    email: Optional[str] = Field(None, description="Owner's email address (may be absent).")


class Repository(BaseModel):
    """Represents a GitHub repository as reported in a push webhook."""

    id: int = Field(..., description="GitHub's internal numeric repository ID.")
    name: str = Field(..., description="Repository name without the owner prefix.")
    full_name: str = Field(..., description="Full repository name, e.g. 'owner/repo'.")
    clone_url: str = Field(..., description="HTTPS URL used for cloning.")
    default_branch: str = Field(..., description="Default branch of the repository.")
    owner: Owner = Field(..., description="Owner information.")

    @property
    def owner_repo_slug(self) -> str:
        """Return a filesystem-safe slug derived from the full repository name.

        Replaces '/' with '_' so the value can be used as a directory name.

        Returns:
            str: e.g. 'owner_repo'
        """
        return self.full_name.replace("/", "_")


class Commit(BaseModel):
    """Represents a single commit included in a push event."""

    id: str = Field(..., description="Full SHA of the commit.")
    message: str = Field(..., description="Commit message.")
    timestamp: str = Field(..., description="ISO-8601 commit timestamp.")
    added: list[str] = Field(default_factory=list, description="Files added in this commit.")
    modified: list[str] = Field(default_factory=list, description="Files modified in this commit.")
    removed: list[str] = Field(default_factory=list, description="Files removed in this commit.")

    class Config:
        # Allow population by both field name and alias
        populate_by_name = True


class Pusher(BaseModel):
    """Represents the GitHub user who performed the push."""

    name: str = Field(..., description="GitHub username of the pusher.")
    email: Optional[str] = Field(None, description="Pusher's email address.")


class WebhookPayload(BaseModel):
    """Top-level model for a GitHub push webhook payload.

    Reference:
        https://docs.github.com/en/webhooks/webhook-events-and-payloads#push
    """

    ref: str = Field(..., description="Full Git ref that was pushed, e.g. 'refs/heads/main'.")
    before: str = Field(..., description="SHA of the most recent commit before the push.")
    after: str = Field(..., description="SHA of the most recent commit after the push.")
    repository: Repository = Field(..., description="Repository metadata.")
    pusher: Pusher = Field(..., description="User who triggered the push.")
    commits: list[Commit] = Field(default_factory=list, description="List of commits in this push.")
    head_commit: Optional[Commit] = Field(None, description="The HEAD commit after the push.")

    @property
    def branch(self) -> str:
        """Extract the short branch name from the ref string.

        Returns:
            str: e.g. 'main' from 'refs/heads/main'.
        """
        return self.ref.removeprefix("refs/heads/")
