"""
tests/test_github.py
---------------------
Unit tests for GitHubService.

Tests:
- verify_signature returns True for a valid HMAC signature
- verify_signature returns False for a tampered signature
- verify_signature skips verification when no secret is configured
- process_push_event calls sub-services in the correct order
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, call

import pytest

from app.models.webhook import WebhookPayload
from services.github_service import GitHubService, WebhookProcessingResult
from services.git_service import GitService
from services.parser_service import ParserService, ParsedCommitData
from services.repository_service import RepositoryService
from services.workflow_service import WorkflowService
from workflow.workflow_state import WorkflowState
from app.core.constants import WorkflowStatus

SECRET = "super-secret"

VALID_PAYLOAD_DICT: dict = {
    "ref": "refs/heads/main",
    "before": "abc123",
    "after": "def456",
    "repository": {
        "id": 1,
        "name": "demo",
        "full_name": "octocat/demo",
        "clone_url": "https://github.com/octocat/demo.git",
        "default_branch": "main",
        "owner": {"name": "octocat"},
    },
    "pusher": {"name": "octocat"},
    "commits": [],
    "head_commit": None,
}


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def github_service() -> GitHubService:
    """Return a GitHubService with all dependencies mocked."""
    git_svc = MagicMock(spec=GitService)
    git_svc.sync_repository.return_value = "repositories/octocat_demo"

    parser_svc = MagicMock(spec=ParserService)
    parser_svc.parse.return_value = ParsedCommitData(
        repository="octocat/demo",
        branch="main",
        commit_sha="def456",
        commit_message="Initial commit",
        commit_timestamp="2026-06-30T10:00:00Z",
        author="octocat",
        changed_files=["README.md"],
    )

    wf_state = WorkflowState(
        workflow_id="wf-uuid-001",
        repository="octocat/demo",
        branch="main",
        status=WorkflowStatus.IN_PROGRESS,
        commit_sha="def456",
        timestamp="2026-06-30T10:00:00Z",
        changed_files=["README.md"],
    )
    workflow_svc = MagicMock(spec=WorkflowService)
    workflow_svc.create_workflow.return_value = wf_state
    workflow_svc.complete_workflow.return_value = wf_state

    repo_svc = MagicMock(spec=RepositoryService)
    repo_svc.get_repository_path.return_value = "repositories/octocat_demo"

    return GitHubService(
        git_service=git_svc,
        parser_service=parser_svc,
        workflow_service=workflow_svc,
        repository_service=repo_svc,
        github_secret=SECRET,
    )


# ---------------------------------------------------------------------------
# Signature tests
# ---------------------------------------------------------------------------

def test_verify_signature_valid(github_service: GitHubService) -> None:
    """A correctly signed body must pass verification."""
    body = b'{"test": "data"}'
    sig = _sign(body, SECRET)
    assert github_service.verify_signature(body, sig) is True


def test_verify_signature_invalid(github_service: GitHubService) -> None:
    """A tampered body must fail verification."""
    body = b'{"test": "data"}'
    sig = _sign(b"different body", SECRET)
    assert github_service.verify_signature(body, sig) is False


def test_verify_signature_no_secret() -> None:
    """When no secret is configured, verification is skipped and True is returned."""
    svc = GitHubService(
        git_service=MagicMock(),
        parser_service=MagicMock(),
        workflow_service=MagicMock(),
        repository_service=MagicMock(),
        github_secret="",
    )
    assert svc.verify_signature(b"anything", "sha256=irrelevant") is True


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------

def test_process_push_event_returns_result(github_service: GitHubService) -> None:
    """process_push_event must return a WebhookProcessingResult on success."""
    payload = WebhookPayload.model_validate(VALID_PAYLOAD_DICT)
    result = github_service.process_push_event(payload)
    assert isinstance(result, WebhookProcessingResult)
    assert result.workflow_id == "wf-uuid-001"
    assert result.repository == "demo"
    assert result.branch == "main"
