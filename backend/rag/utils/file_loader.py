"""
Utility functions for loading repository files.

This module provides reusable utilities for recursively discovering,
filtering, and reading source code and documentation files while
ignoring binary files, hidden directories, and unsupported file types.
"""

from __future__ import annotations

from pathlib import Path

from rag.config.constants import (
    DOCUMENTATION_EXTENSIONS,
    IGNORED_DIRECTORIES,
    IGNORED_EXTENSIONS,
    SUPPORTED_LANGUAGES,
)

TEXT_EXTENSIONS = (
    set(SUPPORTED_LANGUAGES.keys())
    | DOCUMENTATION_EXTENSIONS
)


def is_supported_file(file_path: str | Path) -> bool:
    """
    Checks whether a file should be processed.

    Parameters
    ----------
    file_path : str | Path

    Returns
    -------
    bool
        True if the file is supported.
    """

    path = Path(file_path)

    if not path.is_file():
        return False

    if path.suffix.lower() in IGNORED_EXTENSIONS:
        return False

    return path.suffix.lower() in TEXT_EXTENSIONS


def is_binary_file(file_path: str | Path) -> bool:
    """
    Checks whether a file is binary.

    Parameters
    ----------
    file_path : str | Path

    Returns
    -------
    bool
        True if the file appears to be binary.
    """

    path = Path(file_path)

    try:
        with path.open("rb") as file:
            chunk = file.read(1024)

        return b"\0" in chunk

    except OSError:
        return True


def discover_files(
    repository_path: str | Path,
) -> list[Path]:
    """
    Recursively discovers all supported repository files.

    Parameters
    ----------
    repository_path : str | Path

    Returns
    -------
    list[Path]
        Repository files.
    """

    root = Path(repository_path)

    if not root.exists():
        raise FileNotFoundError(root)

    files: list[Path] = []

    for path in root.rglob("*"):

        if not path.is_file():
            continue

        if any(
            parent.name in IGNORED_DIRECTORIES
            for parent in path.parents
        ):
            continue

        if not is_supported_file(path):
            continue

        if is_binary_file(path):
            continue

        files.append(path)

    return sorted(files)


def load_text_file(
    file_path: str | Path,
    encoding: str = "utf-8",
) -> str:
    """
    Loads a UTF-8 text file.

    Parameters
    ----------
    file_path : str | Path

    encoding : str

    Returns
    -------
    str
        File contents.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(path)

    return path.read_text(
        encoding=encoding,
        errors="replace",
    )


def load_repository(
    repository_path: str | Path,
) -> dict[Path, str]:
    """
    Loads all supported repository files.

    Parameters
    ----------
    repository_path : str | Path

    Returns
    -------
    dict[Path, str]
        Mapping of file paths to file contents.
    """

    repository: dict[Path, str] = {}

    for file_path in discover_files(repository_path):

        content = load_text_file(file_path)

        if not content.strip():
            continue

        repository[file_path] = content

    return repository


def filter_files_by_extension(
    files: list[Path],
    extensions: set[str],
) -> list[Path]:
    """
    Filters files by extension.

    Parameters
    ----------
    files : list[Path]

    extensions : set[str]

    Returns
    -------
    list[Path]
    """

    return [
        file
        for file in files
        if file.suffix.lower() in extensions
    ]