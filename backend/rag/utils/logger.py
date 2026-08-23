"""
Logging utilities for the RAG module.

This module provides a centralized way to obtain loggers throughout the
RAG system while integrating with the application's existing logging
configuration.
"""

from __future__ import annotations

import logging
from typing import Optional


_DEFAULT_LOGGER_NAME = "rag"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Returns a configured logger for the RAG module.

    Parameters
    ----------
    name : str | None, optional
        Name of the logger. If omitted, returns the root RAG logger.

    Returns
    -------
    logging.Logger
        Configured logger instance.

    Examples
    --------
    >>> logger = get_logger(__name__)
    >>> logger.info("Starting bootstrap indexing")
    """

    if name:
        logger_name = f"{_DEFAULT_LOGGER_NAME}.{name}"
    else:
        logger_name = _DEFAULT_LOGGER_NAME

    return logging.getLogger(logger_name)


def set_log_level(level: str) -> None:
    """
    Dynamically updates the logging level of the RAG logger.

    Parameters
    ----------
    level : str
        Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Raises
    ------
    ValueError
        If the supplied log level is invalid.
    """

    logger = logging.getLogger(_DEFAULT_LOGGER_NAME)

    try:
        logger.setLevel(level.upper())
    except ValueError as exc:
        raise ValueError(f"Invalid logging level: {level}") from exc


def is_debug_enabled() -> bool:
    """
    Checks whether DEBUG logging is enabled.

    Returns
    -------
    bool
        True if DEBUG logging is enabled.
    """

    logger = logging.getLogger(_DEFAULT_LOGGER_NAME)
    return logger.isEnabledFor(logging.DEBUG)