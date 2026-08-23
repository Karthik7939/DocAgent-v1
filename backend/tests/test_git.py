"""
tests/test_git.py
------------------
Unit tests for GitService.

Tests:
- repository_exists returns True for a valid git repo path
- repository_exists returns False for a non-git directory
- clone_repository raises RuntimeError on GitCommandError
- pull_repository raises RuntimeError on InvalidGitRepositoryError
- sync_repository calls clone when repo does not exist
- sync_repository calls pull when repo already exists
"""

from unittest.mock import MagicMock, patch

import pytest
from git import GitCommandError, InvalidGitRepositoryError

from services.git_service import GitService


@pytest.fixture()
def git_service(tmp_path) -> GitService:
    """Return a GitService pointing at a temporary directory."""
    return GitService(repository_root=str(tmp_path))


# ---------------------------------------------------------------------------
# repository_exists
# ---------------------------------------------------------------------------

def test_repository_exists_true(git_service: GitService) -> None:
    """Should return True when is_git_repository returns True."""
    with patch("services.git_service.is_git_repository", return_value=True):
        assert git_service.repository_exists("/some/path") is True


def test_repository_exists_false(git_service: GitService) -> None:
    """Should return False when is_git_repository returns False."""
    with patch("services.git_service.is_git_repository", return_value=False):
        assert git_service.repository_exists("/some/path") is False


# ---------------------------------------------------------------------------
# clone_repository
# ---------------------------------------------------------------------------

def test_clone_repository_success(git_service: GitService, tmp_path) -> None:
    """Successful clone should return the local path."""
    dest = str(tmp_path / "repo")
    with patch("services.git_service.Repo") as mock_repo_cls:
        mock_repo_cls.clone_from.return_value = MagicMock()
        result = git_service.clone_repository("https://github.com/x/y.git", dest)
    assert result == dest


def test_clone_repository_raises_on_failure(git_service: GitService, tmp_path) -> None:
    """GitCommandError from GitPython should be re-raised as RuntimeError."""
    dest = str(tmp_path / "repo")
    with patch("services.git_service.Repo") as mock_repo_cls:
        mock_repo_cls.clone_from.side_effect = GitCommandError("clone", 128)
        with pytest.raises(RuntimeError, match="clone failed"):
            git_service.clone_repository("https://github.com/x/y.git", dest)


# ---------------------------------------------------------------------------
# pull_repository
# ---------------------------------------------------------------------------

def test_pull_repository_success(git_service: GitService, tmp_path) -> None:
    """Successful pull should return the local path."""
    local = str(tmp_path / "repo")
    mock_repo = MagicMock()
    mock_repo.remotes.origin.pull.return_value = None
    with patch("services.git_service.Repo", return_value=mock_repo):
        result = git_service.pull_repository(local)
    assert result == local


def test_pull_repository_raises_on_invalid_repo(git_service: GitService, tmp_path) -> None:
    """InvalidGitRepositoryError should be re-raised as RuntimeError."""
    local = str(tmp_path / "not-a-repo")
    with patch("services.git_service.Repo", side_effect=InvalidGitRepositoryError()):
        with pytest.raises(RuntimeError, match="valid Git repository"):
            git_service.pull_repository(local)


# ---------------------------------------------------------------------------
# sync_repository
# ---------------------------------------------------------------------------

def test_sync_calls_clone_when_not_exists(git_service: GitService, tmp_path) -> None:
    """sync_repository should delegate to clone_repository when repo doesn't exist."""
    local = str(tmp_path / "repo")
    with patch.object(git_service, "repository_exists", return_value=False), \
         patch.object(git_service, "clone_repository", return_value=local) as mock_clone:
        git_service.sync_repository("https://github.com/x/y.git", local)
        mock_clone.assert_called_once_with("https://github.com/x/y.git", local)


def test_sync_calls_pull_when_exists(git_service: GitService, tmp_path) -> None:
    """sync_repository should delegate to pull_repository when repo already exists."""
    local = str(tmp_path / "repo")
    with patch.object(git_service, "repository_exists", return_value=True), \
         patch.object(git_service, "pull_repository", return_value=local) as mock_pull:
        git_service.sync_repository("https://github.com/x/y.git", local)
        mock_pull.assert_called_once_with(local)
