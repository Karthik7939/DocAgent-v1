"""
Tokenization utilities for the RAG system.

This module provides lightweight token estimation utilities used for
chunking, prompt construction, and context window management.

The implementation intentionally uses approximate token counting to
remain model-agnostic. If exact tokenization is required, this module
can later be extended to use model-specific tokenizers.
"""

from __future__ import annotations

import re


# Average approximation:
# 1 token ≈ 4 characters (works reasonably well for English source code
# and documentation).
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a text.

    Parameters
    ----------
    text : str

    Returns
    -------
    int
        Estimated token count.
    """

    if not text:
        return 0

    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_available_tokens(
    context_window: int,
    prompt: str,
) -> int:
    """
    Estimate the remaining token budget after a prompt.

    Parameters
    ----------
    context_window : int

    prompt : str

    Returns
    -------
    int
        Remaining available tokens.
    """

    used = estimate_tokens(prompt)

    return max(0, context_window - used)


def fits_context_window(
    text: str,
    context_window: int,
) -> bool:
    """
    Check whether a text fits inside a model context window.

    Parameters
    ----------
    text : str

    context_window : int

    Returns
    -------
    bool
    """

    return estimate_tokens(text) <= context_window


def normalize_whitespace(text: str) -> str:
    """
    Normalize consecutive whitespace characters.

    Parameters
    ----------
    text : str

    Returns
    -------
    str
    """

    return re.sub(r"\s+", " ", text).strip()


def truncate_to_token_limit(
    text: str,
    max_tokens: int,
) -> str:
    """
    Truncate text so that its estimated token count
    does not exceed the specified limit.

    Parameters
    ----------
    text : str

    max_tokens : int

    Returns
    -------
    str
    """

    if estimate_tokens(text) <= max_tokens:
        return text

    max_chars = max_tokens * CHARS_PER_TOKEN

    return text[:max_chars]