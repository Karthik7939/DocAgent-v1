"""
services/git_service.py
------------------------
Git operation service — the only place in the codebase that calls GitPython.

Responsibilities:
- Check whether a local repository already exists
- Clone a repository from a remote URL
- Pull the latest changes for an existing repository

All Git work uses GitPython; raw shell commands are forbidden.
"""

import logging
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, Repo

from utils.git_utils import is_git_repository

logger = logging.getLogger(__name__)


class GitService:
    """Encapsulates all Git operations using GitPython.

    Args:
        repository_root: Root directory under which repositories are stored.
    """

    def __init__(self, repository_root: str) -> None:
        self._root = Path(repository_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def repository_exists(self, local_path: str) -> bool:
        """Return True if a valid Git repository exists at *local_path*.

        Args:
            local_path: Absolute or relative path to check.

        Returns:
            bool: True if the path contains a Git repository.
        """
        exists = is_git_repository(local_path)
        logger.debug("Repository exists=%s at path=%s", exists, local_path)
        return exists

    def clone_repository(self, clone_url: str, local_path: str) -> str:
        """Clone a remote repository to *local_path*.

        Args:
            clone_url:  HTTPS (or SSH) URL of the remote repository.
            local_path: Destination directory on the local filesystem.

        Returns:
            str: The *local_path* where the repository was cloned.

        Raises:
            RuntimeError: If the clone operation fails.
        """
        logger.info("Cloning repository: url=%s  dest=%s", clone_url, local_path)
        try:
            Repo.clone_from(clone_url, local_path)
            logger.info("Clone completed: path=%s", local_path)
            return local_path
        except GitCommandError as exc:
            logger.error("Clone failed: %s", exc)
            raise RuntimeError(f"Repository clone failed: {exc}") from exc

    def pull_repository(self, local_path: str) -> str:
        """Pull the latest changes for the repository at *local_path*.

        Performs a ``git pull`` on the default remote (origin) for the
        currently checked-out branch.

        Args:
            local_path: Path to an existing local Git repository.

        Returns:
            str: The *local_path* of the updated repository.

        Raises:
            RuntimeError: If the path is not a valid Git repository or the
                          pull operation fails.
        """
        logger.info("Pulling repository: path=%s", local_path)
        try:
            repo = Repo(local_path)
            origin = repo.remotes.origin
            origin.pull()
            logger.info("Pull completed: path=%s", local_path)
            return local_path
        except InvalidGitRepositoryError as exc:
            logger.error("Not a valid Git repository: %s", local_path)
            raise RuntimeError(f"Not a valid Git repository: {local_path}") from exc
        except GitCommandError as exc:
            logger.error("Pull failed: %s", exc)
            raise RuntimeError(f"Repository pull failed: {exc}") from exc

    def sync_repository(self, clone_url: str, local_path: str) -> str:
        """Clone or pull a repository, depending on whether it already exists.

        This is the primary entry point for callers — it encapsulates the
        'clone if new, pull if existing' decision.

        Args:
            clone_url:  Remote URL for cloning when the repo does not exist.
            local_path: Local path to check / clone to.

        Returns:
            str: The local path of the up-to-date repository.
        """
        if self.repository_exists(local_path):
            logger.info("Repository already exists — performing pull: %s", local_path)
            return self.pull_repository(local_path)
        else:
            logger.info("Repository not found locally — performing clone: %s", local_path)
            return self.clone_repository(clone_url, local_path)
