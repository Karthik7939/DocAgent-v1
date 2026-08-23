"""
Semantic chunking for documentation files.

This module splits Markdown, reStructuredText, plain text, and HTML
documentation at logical section boundaries without generating metadata
or embeddings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from rag.chunking.models import ChunkDraft, ChunkType, SymbolType
from rag.config.settings import settings
from rag.parsing.language_detector import LanguageDetector
from rag.utils.tokenizer import estimate_tokens

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_RST_HEADING = re.compile(r"^(=|-|`|:|~|'|\"|\^|\+|\*){3,}\s*$")
_HTML_HEADING = re.compile(
    r"^\s*<h([1-6])[^>]*>(.*?)</h\1>\s*$",
    re.IGNORECASE,
)
_HTML_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class _DocSection:
    """
    Internal representation of a documentation section.
    """

    content: str
    start_line: int
    end_line: int
    heading: Optional[str]


class DocChunker:
    """
    Split documentation files into semantic chunk drafts.
    """

    def __init__(
        self,
        max_chunk_tokens: int | None = None,
    ) -> None:
        self._max_chunk_tokens = (
            max_chunk_tokens or settings.max_chunk_tokens
        )

    def chunk(
        self,
        source: str,
        file_path: str,
    ) -> list[ChunkDraft]:
        """
        Chunk one documentation file.
        """
        if not LanguageDetector.is_documentation(file_path):
            return []

        normalized_source = source.replace("\r\n", "\n").replace(
            "\r",
            "\n",
        )

        if not normalized_source.strip():
            return []

        language = LanguageDetector.detect(file_path)
        sections = self._split_into_sections(
            normalized_source,
            file_path,
        )

        drafts: list[ChunkDraft] = []

        for section in sections:
            drafts.extend(
                self._section_to_drafts(
                    section,
                    language,
                ),
            )

        return drafts

    def _split_into_sections(
        self,
        source: str,
        file_path: str,
    ) -> list[_DocSection]:
        """
        Split a documentation file into logical sections.
        """
        extension = file_path.lower()

        if extension.endswith(".md"):
            return self._split_markdown(source)

        if extension.endswith(".rst"):
            return self._split_rst(source)

        if extension.endswith(".html"):
            return self._split_html(source)

        return self._split_plain_text(source)

    def _split_markdown(self, source: str) -> list[_DocSection]:
        """
        Split Markdown content by headings while preserving code fences.
        """
        lines = source.splitlines()
        sections: list[_DocSection] = []
        current_heading: Optional[str] = None
        current_lines: list[str] = []
        current_start = 1
        in_code_fence = False

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_fence = not in_code_fence

            heading_match = (
                None
                if in_code_fence
                else _MARKDOWN_HEADING.match(line)
            )

            if heading_match and current_lines:
                sections.append(
                    _DocSection(
                        content="\n".join(current_lines).strip(),
                        start_line=current_start,
                        end_line=index - 1,
                        heading=current_heading,
                    ),
                )
                current_lines = []
                current_start = index

            if heading_match:
                current_heading = heading_match.group(2).strip()
                current_lines.append(line)
                continue

            if not current_lines and stripped:
                current_start = index

            current_lines.append(line)

        if current_lines:
            sections.append(
                _DocSection(
                    content="\n".join(current_lines).strip(),
                    start_line=current_start,
                    end_line=len(lines),
                    heading=current_heading,
                ),
            )

        if not sections and source.strip():
            return [
                _DocSection(
                    content=source.strip(),
                    start_line=1,
                    end_line=len(lines) or 1,
                    heading=None,
                ),
            ]

        return [
            section
            for section in sections
            if section.content
        ]

    def _split_rst(self, source: str) -> list[_DocSection]:
        """
        Split reStructuredText by section titles and underline markers.
        """
        lines = source.splitlines()
        sections: list[_DocSection] = []
        current_heading: Optional[str] = None
        current_lines: list[str] = []
        current_start = 1

        for index, line in enumerate(lines, start=1):
            previous = lines[index - 2] if index > 1 else ""
            is_heading = (
                index > 1
                and line.strip()
                and _RST_HEADING.match(line.strip())
                and previous.strip()
            )

            if is_heading and current_lines:
                body_lines = current_lines[:-1]
                sections.append(
                    _DocSection(
                        content="\n".join(body_lines).strip(),
                        start_line=current_start,
                        end_line=index - 2,
                        heading=current_heading,
                    ),
                )
                current_heading = previous.strip()
                current_lines = [previous, line]
                current_start = index - 1
                continue

            if not current_lines and line.strip():
                current_start = index

            current_lines.append(line)

        if current_lines:
            sections.append(
                _DocSection(
                    content="\n".join(current_lines).strip(),
                    start_line=current_start,
                    end_line=len(lines),
                    heading=current_heading,
                ),
            )

        if not sections and source.strip():
            return [
                _DocSection(
                    content=source.strip(),
                    start_line=1,
                    end_line=len(lines) or 1,
                    heading=None,
                ),
            ]

        return [
            section
            for section in sections
            if section.content
        ]

    def _split_html(self, source: str) -> list[_DocSection]:
        """
        Split HTML documentation by heading tags.
        """
        lines = source.splitlines()
        sections: list[_DocSection] = []
        current_heading: Optional[str] = None
        current_lines: list[str] = []
        current_start = 1

        for index, line in enumerate(lines, start=1):
            heading_match = _HTML_HEADING.match(line.strip())

            if heading_match and current_lines:
                sections.append(
                    _DocSection(
                        content="\n".join(current_lines).strip(),
                        start_line=current_start,
                        end_line=index - 1,
                        heading=current_heading,
                    ),
                )
                current_lines = []
                current_start = index

            if heading_match:
                current_heading = _HTML_TAG.sub(
                    "",
                    heading_match.group(2),
                ).strip()
                current_lines.append(line)
                continue

            if not current_lines and line.strip():
                current_start = index

            current_lines.append(line)

        if current_lines:
            sections.append(
                _DocSection(
                    content="\n".join(current_lines).strip(),
                    start_line=current_start,
                    end_line=len(lines),
                    heading=current_heading,
                ),
            )

        if not sections and source.strip():
            return [
                _DocSection(
                    content=source.strip(),
                    start_line=1,
                    end_line=len(lines) or 1,
                    heading=None,
                ),
            ]

        return [
            section
            for section in sections
            if section.content
        ]

    def _split_plain_text(self, source: str) -> list[_DocSection]:
        """
        Split plain text by blank-line paragraph boundaries.
        """
        lines = source.splitlines()
        sections: list[_DocSection] = []
        current_lines: list[str] = []
        current_start = 1

        for index, line in enumerate(lines, start=1):
            if not line.strip() and current_lines:
                sections.append(
                    _DocSection(
                        content="\n".join(current_lines).strip(),
                        start_line=current_start,
                        end_line=index - 1,
                        heading=None,
                    ),
                )
                current_lines = []
                continue

            if not current_lines and line.strip():
                current_start = index

            if line.strip() or current_lines:
                current_lines.append(line)

        if current_lines:
            sections.append(
                _DocSection(
                    content="\n".join(current_lines).strip(),
                    start_line=current_start,
                    end_line=len(lines),
                    heading=None,
                ),
            )

        if not sections and source.strip():
            return [
                _DocSection(
                    content=source.strip(),
                    start_line=1,
                    end_line=len(lines) or 1,
                    heading=None,
                ),
            ]

        return [
            section
            for section in sections
            if section.content
        ]

    def _section_to_drafts(
        self,
        section: _DocSection,
        language: str,
    ) -> list[ChunkDraft]:
        """
        Convert a documentation section into one or more chunk drafts.
        """
        if estimate_tokens(section.content) <= self._max_chunk_tokens:
            return [
                self._build_draft(section, language),
            ]

        return self._split_large_section(section, language)

    def _split_large_section(
        self,
        section: _DocSection,
        language: str,
    ) -> list[ChunkDraft]:
        """
        Split oversized sections at paragraph boundaries.
        """
        paragraphs = re.split(r"\n\s*\n", section.content)
        drafts: list[ChunkDraft] = []
        current_parts: list[str] = []
        current_start = section.start_line
        line_cursor = section.start_line

        for paragraph in paragraphs:
            paragraph = paragraph.strip()

            if not paragraph:
                continue

            candidate = "\n\n".join(
                [*current_parts, paragraph],
            ).strip()

            if (
                current_parts
                and estimate_tokens(candidate) > self._max_chunk_tokens
            ):
                content = "\n\n".join(current_parts).strip()
                paragraph_lines = content.count("\n") + 1
                drafts.append(
                    ChunkDraft(
                        content=content,
                        start_line=current_start,
                        end_line=current_start + paragraph_lines - 1,
                        language=language,
                        chunk_type=ChunkType.DOCUMENTATION,
                        symbol_name=section.heading,
                        symbol_type=SymbolType.SECTION,
                    ),
                )
                current_start = line_cursor
                current_parts = [paragraph]
            else:
                current_parts.append(paragraph)

            line_cursor += paragraph.count("\n") + 2

        if current_parts:
            content = "\n\n".join(current_parts).strip()
            drafts.append(
                ChunkDraft(
                    content=content,
                    start_line=current_start,
                    end_line=section.end_line,
                    language=language,
                    chunk_type=ChunkType.DOCUMENTATION,
                    symbol_name=section.heading,
                    symbol_type=SymbolType.SECTION,
                ),
            )

        return drafts

    @staticmethod
    def _build_draft(
        section: _DocSection,
        language: str,
    ) -> ChunkDraft:
        """
        Build one documentation chunk draft from a section.
        """
        return ChunkDraft(
            content=section.content,
            start_line=section.start_line,
            end_line=section.end_line,
            language=language,
            chunk_type=ChunkType.DOCUMENTATION,
            symbol_name=section.heading,
            symbol_type=SymbolType.SECTION,
        )
