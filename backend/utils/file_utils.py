"""
utils/file_utils.py
-------------------
Safe filesystem operations.

Responsibilities:
- Read JSON files
- Write JSON files
- Delete JSON files
- Create folders safely
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def ensure_directory(path: str) -> None:
    """Create a directory (and any missing parents) if it does not exist.

    Args:
        path: Absolute or relative path of the directory to create.

    Raises:
        OSError: If the directory cannot be created due to permission issues.
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured directory exists: %s", dir_path)


def read_json(file_path: str) -> dict[str, Any]:
    """Read a JSON file and return its contents as a dictionary.

    Args:
        file_path: Path to the JSON file.

    Returns:
        dict: Parsed JSON content.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file content is not valid JSON.
    """
    path = Path(file_path)
    logger.debug("Reading JSON file: %s", path)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(file_path: str, data: dict[str, Any]) -> None:
    """Serialize *data* to JSON and write it to *file_path*.

    The parent directory is created automatically if it does not exist.

    Args:
        file_path: Destination path for the JSON file.
        data: Dictionary to serialize.

    Raises:
        OSError: If the file cannot be written.
    """
    path = Path(file_path)
    ensure_directory(str(path.parent))
    logger.debug("Writing JSON file: %s", path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=4)


def delete_file(file_path: str) -> bool:
    """Delete a file if it exists.

    Args:
        file_path: Path to the file to remove.

    Returns:
        bool: True if the file was deleted, False if it did not exist.

    Raises:
        OSError: If the file exists but cannot be deleted.
    """
    path = Path(file_path)
    if path.exists():
        path.unlink()
        logger.debug("Deleted file: %s", path)
        return True
    logger.debug("File not found, skipping delete: %s", path)
    return False


def file_exists(file_path: str) -> bool:
    """Check whether a file exists at the given path.

    Args:
        file_path: Path to check.

    Returns:
        bool: True if the path exists and is a file.
    """
    return Path(file_path).is_file()


def directory_exists(dir_path: str) -> bool:
    """Check whether a directory exists at the given path.

    Args:
        dir_path: Path to check.

    Returns:
        bool: True if the path exists and is a directory.
    """
    return Path(dir_path).is_dir()
