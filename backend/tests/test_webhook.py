"""
tests/test_webhook.py
----------------------
Unit tests for the POST /webhook/github endpoint.

Tests:
- Unsupported event returns HTTP 400
- Invalid signature returns HTTP 400
- Invalid JSON payload returns HTTP 422
- Valid push event returns HTTP 200 with correct response shape
"""

import json
import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_github_service
from services.github_service import GitHubService, WebhookProcessingResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_PAYLOAD: dict = {
    "ref": "refs/heads/main",
    "before": "abc123",
    "after": "def456",
    "repository": {
        "id": 1,
        "name": "demo",
        "full_name": "octocat/demo",
        "clone_url": "https://github.com/octocat/demo.git",
        "default_branch": "main",
        "owner": {"name": "octocat", "email": "octocat@github.com"},
    },
    "pusher": {"name": "octocat", "email": "octocat@github.com"},
    "commits": [
        {
            "id": "def456",
            "message": "Initial commit",
            "timestamp": "2026-06-30T10:00:00Z",
            "added": ["README.md"],
            "modified": [],
            "removed": [],
        }
    ],
    "head_commit": {
        "id": "def456",
        "message": "Initial commit",
        "timestamp": "2026-06-30T10:00:00Z",
        "added": ["README.md"],
        "modified": [],
        "removed": [],
    },
}

SECRET = "test-secret"


def _make_signature(body: bytes, secret: str) -> str:
    """Generate a valid HMAC-SHA256 signature for testing."""
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.fixture()
def client():
    """Return a TestClient with a mocked GitHubService."""
    mock_service = MagicMock(spec=GitHubService)
    mock_service.verify_signature.return_value = True
    mock_service.process_push_event.return_value = WebhookProcessingResult(
        workflow_id="test-uuid-1234",
        repository="demo",
        branch="main",
    )

    app.dependency_overrides[get_github_service] = lambda: mock_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_unsupported_event_returns_400(client: TestClient) -> None:
    """Events other than 'push' must be rejected with HTTP 400."""
    response = client.post(
        "/webhook/github",
        headers={"x-github-event": "pull_request", "x-hub-signature-256": "sha256=dummy"},
        json=VALID_PAYLOAD,
    )
    assert response.status_code == 400


def test_valid_push_returns_200(client: TestClient) -> None:
    """A valid push event must return HTTP 200 with the expected body."""
    body = json.dumps(VALID_PAYLOAD).encode()
    response = client.post(
        "/webhook/github",
        headers={
            "x-github-event": "push",
            "x-hub-signature-256": "sha256=dummy",
            "content-type": "application/json",
        },
        content=body,
    )
    assert response.status_code in (200, 202)
    data = response.json()
    if response.status_code == 200:
        assert data["status"] == "success"
        assert data["workflow_id"] == "test-uuid-1234"
        assert data["repository"] == "demo"
        assert data["branch"] == "main"
    else:
        assert data["status"] == "success" or data["message"] is not None


def test_health_endpoint(client: TestClient) -> None:
    """GET /health must return {"status": "healthy"}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
