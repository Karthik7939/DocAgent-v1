"""
Utility functions for generating deterministic hashes.

Hashes are used throughout the RAG pipeline to detect changes,
avoid duplicate embeddings, and identify semantic chunks.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


DEFAULT_HASH_ALGORITHM = "sha256"
SUPPORTED_HASH_ALGORITHMS = hashlib.algorithms_available


def generate_hash(
    content: str | bytes,
    algorithm: str = DEFAULT_HASH_ALGORITHM,
) -> str:
    """
    Generate a deterministic hash for the given content.

    Parameters
    ----------
    content : str | bytes
        Content to hash.

    algorithm : str, default="sha256"
        Hashing algorithm.

    Returns
    -------
    str
        Hexadecimal hash digest.

    Raises
    ------
    ValueError
        If the hashing algorithm is unsupported.
    """

    if algorithm not in SUPPORTED_HASH_ALGORITHMS:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    hasher = hashlib.new(algorithm)

    if isinstance(content, str):
        content = content.encode("utf-8")

    hasher.update(content)

    return hasher.hexdigest()


def hash_file(
    file_path: str | Path,
    algorithm: str = DEFAULT_HASH_ALGORITHM,
    chunk_size: int = 8192,
) -> str:
    """
    Generate a hash for a file.

    Parameters
    ----------
    file_path : str | Path
        File to hash.

    algorithm : str
        Hash algorithm.

    chunk_size : int
        Number of bytes read per iteration.

    Returns
    -------
    str
        File hash.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(path)

    hasher = hashlib.new(algorithm)

    with path.open("rb") as file:

        while chunk := file.read(chunk_size):
            hasher.update(chunk)

    return hasher.hexdigest()


def hash_chunks(chunks: Iterable[str]) -> list[str]:
    """
    Generate hashes for multiple chunks.

    Parameters
    ----------
    chunks : Iterable[str]

    Returns
    -------
    list[str]
        List of hashes.
    """

    return [
        generate_hash(chunk)
        for chunk in chunks
    ]


def combine_hashes(
    hashes: Iterable[str],
    algorithm: str = DEFAULT_HASH_ALGORITHM,
) -> str:
    """
    Generate a single hash from multiple hashes.

    Useful for hashing an entire file based on the hashes
    of its semantic chunks.

    Parameters
    ----------
    hashes : Iterable[str]

    algorithm : str

    Returns
    -------
    str
        Combined hash.
    """

    hasher = hashlib.new(algorithm)

    for value in sorted(hashes):
        hasher.update(value.encode("utf-8"))

    return hasher.hexdigest()


def has_content_changed(
    old_hash: str,
    new_hash: str,
) -> bool:
    """
    Compare two hashes.

    Parameters
    ----------
    old_hash : str

    new_hash : str

    Returns
    -------
    bool
        True if the content has changed.
    """

    return old_hash != new_hash