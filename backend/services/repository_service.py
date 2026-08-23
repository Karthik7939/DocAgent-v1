"""
services/repository_service.py
--------------------------------
Manages local repository directory layout.

Responsibilities:
- Compute the local filesystem path for a given repository
- Create repository root directories
- Delete repository directories
- No Git commands — this service handles only directory management
"""

import logging
import shutil
from pathlib import Path

from utils.file_utils import directory_exists, ensure_directory

logger = logging.getLogger(__name__)


class RepositoryService:
    """Handles local filesystem layout for cloned repositories.

    Args:
        repository_root: Root directory under which all repos are stored.
                         Typically loaded from Settings.repository_root.
    """

    def __init__(self, repository_root: str) -> None:
        self._root = Path(repository_root)

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def get_repository_path(self, owner_repo_slug: str) -> str:
        """Return the expected local path for a repository.

        The slug is the repository full_name with '/' replaced by '_',
        e.g.  'octocat_Hello-World'.

        Args:
            owner_repo_slug: Filesystem-safe identifier for the repository.

        Returns:
            str: Absolute path string, e.g. 'repositories/octocat_Hello-World'.
        """
        return str(self._root / owner_repo_slug)

    # ------------------------------------------------------------------
    # Directory management
    # ------------------------------------------------------------------

    def ensure_repository_root(self) -> None:
        """Create the repository root directory if it does not exist."""
        ensure_directory(str(self._root))
        logger.debug("Repository root ensured: %s", self._root)

    def repository_directory_exists(self, owner_repo_slug: str) -> bool:
        """Check whether a local repository directory already exists.

        Args:
            owner_repo_slug: Filesystem-safe repository identifier.

        Returns:
            bool: True if the directory exists.
        """
        path = self.get_repository_path(owner_repo_slug)
        exists = directory_exists(path)
        logger.debug("Repository directory exists=%s: %s", exists, path)
        return exists

    def delete_repository_directory(self, owner_repo_slug: str) -> bool:
        """Recursively delete a repository directory.

        Args:
            owner_repo_slug: Filesystem-safe repository identifier.

        Returns:
            bool: True if the directory was deleted, False if it did not exist.

        Raises:
            OSError: If the directory exists but cannot be deleted.
        """
        path = Path(self.get_repository_path(owner_repo_slug))
        if path.exists():
            shutil.rmtree(path)
            logger.info("Repository directory deleted: %s", path)
            return True
        logger.debug("Repository directory not found, skipping delete: %s", path)
        return False
