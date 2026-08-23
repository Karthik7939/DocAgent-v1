"""
Metadata enrichment for semantic chunks.

Chunkers produce content-only drafts. This module converts drafts into
fully described ``Chunk`` objects ready for embedding generation.
"""

from __future__ import annotations

from typing import Iterable, Optional

from rag.chunking.models import Chunk, ChunkDraft, ChunkType
from rag.config.constants import HASH_ALGORITHM
from rag.schemas.chunk import ChunkMetadata
from rag.utils.hashing import generate_hash
from rag.utils.tokenizer import estimate_tokens


class MetadataBuilder:
    """
    Build chunk metadata and stable identifiers.
    """

    def build(
        self,
        draft: ChunkDraft,
        *,
        repository: str,
        file_path: str,
        commit_sha: Optional[str] = None,
        active: bool = True,
    ) -> Chunk:
        """
        Convert one chunk draft into a fully described chunk.
        """
        content = draft.content.strip()

        if not content:
            raise ValueError(
                f"Cannot build metadata for empty chunk in {file_path}.",
            )

        start_line = max(1, draft.start_line)
        end_line = max(start_line, draft.end_line)
        content_hash = generate_hash(content, algorithm=HASH_ALGORITHM)
        token_count = estimate_tokens(content)
        chunk_id = self.build_chunk_id(
            repository=repository,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            content_hash=content_hash,
            symbol_name=draft.symbol_name,
        )

        metadata = ChunkMetadata(
            chunk_id=chunk_id,
            repository=repository,
            file_path=file_path,
            language=draft.language,
            chunk_type=draft.chunk_type,
            symbol_name=draft.symbol_name,
            symbol_type=draft.symbol_type,
            parent_symbol=draft.parent_symbol,
            start_line=start_line,
            end_line=end_line,
            commit_sha=commit_sha,
            content_hash=content_hash,
            token_count=token_count,
            active=active,
        )

        return Chunk(
            metadata=metadata,
            content=content,
        )

    def build_many(
        self,
        drafts: Iterable[ChunkDraft],
        *,
        repository: str,
        file_path: str,
        commit_sha: Optional[str] = None,
        active: bool = True,
    ) -> list[Chunk]:
        """
        Convert multiple drafts into chunks.
        """
        return [
            self.build(
                draft,
                repository=repository,
                file_path=file_path,
                commit_sha=commit_sha,
                active=active,
            )
            for draft in drafts
        ]

    @staticmethod
    def build_chunk_id(
        *,
        repository: str,
        file_path: str,
        start_line: int,
        end_line: int,
        content_hash: str,
        symbol_name: Optional[str] = None,
    ) -> str:
        """
        Generate a stable chunk identifier.

        The identifier remains stable for unchanged content and location,
        which supports incremental re-indexing and change detection.
        """
        symbol_key = symbol_name or "__module__"

        return generate_hash(
            (
                f"{repository}:{file_path}:{symbol_key}:"
                f"{start_line}:{end_line}:{content_hash}"
            ),
            algorithm=HASH_ALGORITHM,
        )

    @staticmethod
    def detect_duplicates(chunks: Iterable[Chunk]) -> list[str]:
        """
        Return duplicate chunk identifiers, if any.
        """
        seen: set[str] = set()
        duplicates: list[str] = []

        for chunk in chunks:
            chunk_id = chunk.metadata.chunk_id

            if chunk_id in seen:
                duplicates.append(chunk_id)
                continue

            seen.add(chunk_id)

        return duplicates
