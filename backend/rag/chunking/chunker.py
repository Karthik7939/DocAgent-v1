"""
High-level chunking orchestrator for the RAG pipeline.

This module routes repository files to the appropriate chunker, enriches
chunk drafts with metadata, validates the result, and returns semantic
chunks ready for embedding generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rag.chunking.code_chunker import CodeChunker
from rag.chunking.doc_chunker import DocChunker
from rag.chunking.metadata_builder import MetadataBuilder
from rag.chunking.models import (
    Chunk,
    ChunkStatistics,
    ChunkType,
    ChunkValidationResult,
)
from rag.parsing.language_detector import LanguageDetector
from rag.schemas.chunk import SymbolType
from rag.utils import get_logger
from rag.utils.file_loader import (
    discover_files,
    is_binary_file,
    is_supported_file,
    load_text_file,
)

logger = get_logger(__name__)


class Chunker:
    """
    Orchestrate repository and file-level semantic chunking.
    """

    def __init__(
        self,
        code_chunker: CodeChunker | None = None,
        doc_chunker: DocChunker | None = None,
        metadata_builder: MetadataBuilder | None = None,
    ) -> None:
        self._code_chunker = code_chunker or CodeChunker()
        self._doc_chunker = doc_chunker or DocChunker()
        self._metadata_builder = metadata_builder or MetadataBuilder()

    def chunk_file(
        self,
        file_path: str | Path,
        source: str,
        *,
        repository: str,
        commit_sha: Optional[str] = None,
    ) -> list[Chunk]:
        """
        Chunk a single repository file.
        """
        path = Path(file_path)
        relative_path = path.as_posix()
        drafts = self._route_to_chunker(relative_path, source)

        if not drafts:
            return []

        chunks = self._metadata_builder.build_many(
            drafts,
            repository=repository,
            file_path=relative_path,
            commit_sha=commit_sha,
        )
        validation = self.validate(chunks)

        if not validation.valid:
            logger.warning(
                "Chunk validation failed for %s: %s",
                relative_path,
                validation.errors,
            )

        return chunks

    def chunk_repository(
        self,
        repository_path: str | Path,
        *,
        repository_name: str,
        commit_sha: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> tuple[list[Chunk], ChunkStatistics]:
        """
        Chunk every supported file in a repository.
        """
        root = Path(repository_path)
        chunks: list[Chunk] = []
        statistics = ChunkStatistics()

        all_files = list(discover_files(root))
        total_files = len(all_files)

        if workflow_id:
            from rag.pipeline.events import ParsingStarted
            from rag.pipeline.manager import handle_event, check_cancelled
            try:
                handle_event(ParsingStarted(workflow_id, total_files))
            except Exception:
                pass

        for idx, file_path in enumerate(all_files, start=1):
            if workflow_id:
                try:
                    check_cancelled(workflow_id)
                except Exception:
                    raise

            relative_path = file_path.relative_to(root).as_posix()

            if not self.should_process(file_path):
                statistics = statistics.model_copy(
                    update={
                        "files_skipped": statistics.files_skipped + 1,
                    },
                )
                continue

            source = load_text_file(file_path)
            file_chunks = self.chunk_file(
                relative_path,
                source,
                repository=repository_name,
                commit_sha=commit_sha,
            )
            chunks.extend(file_chunks)
            statistics = statistics.merge(
                self._statistics_for_file(file_chunks),
            )

            if workflow_id:
                from rag.pipeline.events import ChunkCreated
                try:
                    handle_event(ChunkCreated(
                        workflow_id=workflow_id,
                        file_path=relative_path,
                        file_index=idx,
                        total_files=total_files,
                        chunks_count=len(file_chunks)
                    ))
                except Exception:
                    pass

        validation = self.validate(chunks)

        if validation.warnings:
            logger.warning(
                "Repository chunk validation warnings: %s",
                validation.warnings,
            )

        return chunks, statistics

    def chunk_changed_file(
        self,
        file_path: str | Path,
        source: str,
        *,
        repository: str,
        commit_sha: Optional[str] = None,
    ) -> list[Chunk]:
        """
        Chunk one changed file during incremental processing.
        """
        return self.chunk_file(
            file_path,
            source,
            repository=repository,
            commit_sha=commit_sha,
        )

    def should_process(self, file_path: str | Path) -> bool:
        """
        Determine whether a file should be chunked.
        """
        path = Path(file_path)

        if not path.is_file():
            return False

        if not is_supported_file(path):
            return False

        if is_binary_file(path):
            return False

        language = LanguageDetector.detect(path)

        return language not in {"unknown"}

    def validate(
        self,
        chunks: list[Chunk],
    ) -> ChunkValidationResult:
        """
        Validate chunk output before returning it downstream.
        """
        errors: list[str] = []
        warnings: list[str] = []
        empty_chunks = 0

        for chunk in chunks:
            if not chunk.content.strip():
                empty_chunks += 1
                warnings.append(
                    f"Empty chunk detected: {chunk.metadata.chunk_id}",
                )

            if chunk.metadata.end_line < chunk.metadata.start_line:
                errors.append(
                    "Invalid line range for "
                    f"{chunk.metadata.file_path}: "
                    f"{chunk.metadata.start_line}-"
                    f"{chunk.metadata.end_line}",
                )

            if chunk.metadata.token_count <= 0:
                warnings.append(
                    "Zero token count for "
                    f"{chunk.metadata.chunk_id}",
                )

        duplicates = self._metadata_builder.detect_duplicates(
            chunks,
        )

        if duplicates:
            warnings.append(
                f"Duplicate chunk IDs detected: {duplicates}",
            )

        return ChunkValidationResult(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            duplicate_chunk_ids=duplicates,
            empty_chunks=empty_chunks,
        )

    def _route_to_chunker(
        self,
        file_path: str,
        source: str,
    ):
        """
        Route a file to the code or documentation chunker.
        """
        language = LanguageDetector.detect(file_path)

        if language == "documentation":
            return self._doc_chunker.chunk(source, file_path)

        if LanguageDetector.is_code_file(file_path):
            return self._code_chunker.chunk(source, file_path)

        logger.debug("Skipping unsupported file type: %s", file_path)
        return []

    @staticmethod
    def _statistics_for_file(
        chunks: list[Chunk],
    ) -> ChunkStatistics:
        """
        Build statistics for one processed file.
        """
        code_chunks = sum(
            1
            for chunk in chunks
            if chunk.metadata.chunk_type == ChunkType.CODE
        )
        documentation_chunks = sum(
            1
            for chunk in chunks
            if chunk.metadata.chunk_type == ChunkType.DOCUMENTATION
        )
        module_chunks = sum(
            1
            for chunk in chunks
            if chunk.metadata.symbol_type == SymbolType.MODULE
        )
        symbol_chunks = len(chunks) - module_chunks
        total_tokens = sum(
            chunk.metadata.token_count for chunk in chunks
        )

        return ChunkStatistics(
            total_chunks=len(chunks),
            code_chunks=code_chunks,
            documentation_chunks=documentation_chunks,
            module_chunks=module_chunks,
            symbol_chunks=symbol_chunks,
            total_tokens=total_tokens,
            files_processed=1,
        )
