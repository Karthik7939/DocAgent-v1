"""
Utilities for detecting the programming language of repository files.

Language detection is primarily based on file extensions. This module is
used by the parser, chunker, and indexing pipeline.
"""

from __future__ import annotations

from pathlib import Path

from rag.config.constants import (
    DOCUMENTATION_EXTENSIONS,
    SUPPORTED_LANGUAGES,
)


class LanguageDetector:
    """
    Detects the language of repository files.
    """

    @staticmethod
    def detect(file_path: str | Path) -> str:
        """
        Detect the language of a file.

        Parameters
        ----------
        file_path : str | Path
            Repository-relative or absolute file path.

        Returns
        -------
        str
            Language name.

        Notes
        -----
        Returns "documentation" for supported documentation files and
        "unknown" if the extension is not recognized.
        """

        path = Path(file_path)

        extension = path.suffix.lower()

        if extension in SUPPORTED_LANGUAGES:
            return SUPPORTED_LANGUAGES[extension]

        if extension in DOCUMENTATION_EXTENSIONS:
            return "documentation"

        return "unknown"

    @staticmethod
    def is_supported(file_path: str | Path) -> bool:
        """
        Check whether the file is supported by the parser.

        Parameters
        ----------
        file_path : str | Path

        Returns
        -------
        bool
        """

        return (
            LanguageDetector.detect(file_path)
            != "unknown"
        )

    @staticmethod
    def is_code_file(file_path: str | Path) -> bool:
        """
        Check whether a file is a source code file.

        Parameters
        ----------
        file_path : str | Path

        Returns
        -------
        bool
        """

        language = LanguageDetector.detect(file_path)

        return (
            language != "unknown"
            and language != "documentation"
        )

    @staticmethod
    def is_documentation(file_path: str | Path) -> bool:
        """
        Check whether a file is a documentation file.

        Parameters
        ----------
        file_path : str | Path

        Returns
        -------
        bool
        """

        return (
            LanguageDetector.detect(file_path)
            == "documentation"
        )

    @staticmethod
    def supported_languages() -> list[str]:
        """
        Return all supported programming languages.

        Returns
        -------
        list[str]
        """

        return sorted(
            set(SUPPORTED_LANGUAGES.values())
        )

    @staticmethod
    def supported_extensions() -> list[str]:
        """
        Return all supported file extensions.

        Returns
        -------
        list[str]
        """

        extensions = set(SUPPORTED_LANGUAGES.keys())
        extensions.update(DOCUMENTATION_EXTENSIONS)

        return sorted(extensions)