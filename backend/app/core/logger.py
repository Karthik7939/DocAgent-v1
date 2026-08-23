"""
app/core/logger.py
------------------
Logging configuration.

Responsibilities:
- Configure the root logger once at application startup
- Attach a console (StreamHandler) and a rotating file handler
- Apply a consistent log format across both handlers
- Expose a `setup_logging()` function called from app/main.py
"""

import logging
import logging.handlers
import os
from pathlib import Path


_LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
_DATE_FORMAT: str = "%Y-%m-%dT%H:%M:%S"

# Rotating file settings
_MAX_BYTES: int = 10 * 1024 * 1024   # 10 MB per file
_BACKUP_COUNT: int = 5                # keep up to 5 rotated files


def setup_logging(log_level: str = "INFO", log_file: str = "logs/backend.log") -> None:
    """Configure the root Python logger.

    Creates the log file's parent directory if it does not exist, then
    attaches:
    - A ``StreamHandler`` that writes to stdout.
    - A ``RotatingFileHandler`` that writes to *log_file*.

    This function is idempotent — calling it more than once will not
    duplicate handlers because it clears existing handlers first.

    Args:
        log_level: Logging level string, e.g. ``'INFO'`` or ``'DEBUG'``.
        log_file:  Path to the log file (relative or absolute).
    """
    numeric_level: int = getattr(logging, log_level.upper(), logging.INFO)

    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)

    # --- Rotating file handler ---
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)

    # --- Root logger ---
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any pre-existing handlers to avoid duplicates on re-initialisation
    root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    root_logger.info("Logging initialised — level=%s  file=%s", log_level, log_file)


def get_logger(name: str) -> logging.Logger:
    """Return a module-specific logger.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        logging.Logger: Logger instance namespaced under *name*.
    """
    return logging.getLogger(name)
