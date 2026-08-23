"""
Utility functions shared across the RAG system.
"""

from .file_loader import (
    discover_files,
    filter_files_by_extension,
    is_binary_file,
    is_supported_file,
    load_repository,
    load_text_file,
)

from .hashing import (
    combine_hashes,
    generate_hash,
    hash_chunks,
    hash_file,
    has_content_changed,
)

from .logger import (
    get_logger,
    is_debug_enabled,
    set_log_level,
)

from .tokenizer import (
    estimate_available_tokens,
    estimate_tokens,
    fits_context_window,
    normalize_whitespace,
    truncate_to_token_limit,
)

__all__ = [
    # File Loader
    "discover_files",
    "filter_files_by_extension",
    "is_binary_file",
    "is_supported_file",
    "load_repository",
    "load_text_file",

    # Hashing
    "generate_hash",
    "hash_file",
    "hash_chunks",
    "combine_hashes",
    "has_content_changed",

    # Logger
    "get_logger",
    "set_log_level",
    "is_debug_enabled",

    # Tokenizer
    "estimate_tokens",
    "estimate_available_tokens",
    "fits_context_window",
    "normalize_whitespace",
    "truncate_to_token_limit",
]