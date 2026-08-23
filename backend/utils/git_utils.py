"""
utils/git_utils.py
------------------
Thin wrapper helpers around GitPython primitives.

Responsibilities:
- Validate that a path contains a Git repository
- Retrieve the active branch name from a Repo object
- Retrieve the latest commit SHA from a Repo object
- No business logic; only low-level Git introspection helpers
"""

import logging
from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo

logger = logging.getLogger(__name__)


def is_git_repository(path: str) -> bool:
    """Return True if *path* is a valid Git repository root.

    Args:
        path: Filesystem path to check.

    Returns:
        bool: True if a .git directory (or bare repo) exists at *path*.
    """
    try:
        Repo(path, search_parent_directories=False)
        return True
    except (InvalidGitRepositoryError, NoSuchPathError):
        # InvalidGitRepositoryError → path exists but is not a git repo
        # NoSuchPathError          → path does not exist yet (not cloned)
        return False


def get_active_branch(repo: Repo) -> str:
    """Return the name of the currently checked-out branch.

    Args:
        repo: An initialised GitPython Repo object.

    Returns:
        str: Branch name, e.g. 'main'.
    """
    branch: str = repo.active_branch.name
    logger.debug("Active branch: %s", branch)
    return branch


def get_latest_commit_sha(repo: Repo) -> str:
    """Return the full SHA of the HEAD commit.

    Args:
        repo: An initialised GitPython Repo object.

    Returns:
        str: 40-character hex SHA string.
    """
    sha: str = repo.head.commit.hexsha
    logger.debug("Latest commit SHA: %s", sha)
    return sha


def get_remote_url(repo: Repo, remote_name: str = "origin") -> str:
    """Return the URL of a named remote.

    Args:
        repo: An initialised GitPython Repo object.
        remote_name: The name of the remote (defaults to 'origin').

    Returns:
        str: Remote URL string.

    Raises:
        IndexError: If the named remote does not exist.
    """
    url: str = repo.remotes[remote_name].url
    logger.debug("Remote '%s' URL: %s", remote_name, url)
    return url
