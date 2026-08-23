"""
BM25 keyword store for sparse lexical retrieval.

This module complements dense vector search by matching exact identifiers,
function names, class names, and other keyword-heavy code tokens.
"""

from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

from rag.config import settings
from rag.config.constants import BM25_DIRECTORY, BM25_FILENAME
from rag.schemas.chunk import Chunk
from rag.utils import get_logger

logger = get_logger(__name__)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _repo_slug(repository: str) -> str:
    """Convert 'owner/repo' → 'owner_repo' safe for use as a directory name."""
    return re.sub(r"[^\w\-]", "_", repository) if repository else "_default"


@dataclass(slots=True)
class KeywordStoreStatistics:
    """
    Statistics for the BM25 keyword store.
    """

    total_documents: int = 0
    active_documents: int = 0
    deleted_documents: int = 0
    repository: str = ""


@dataclass(frozen=True, slots=True)
class KeywordSearchHit:
    """
    One BM25 search result before hybrid ranking.
    """

    chunk: Chunk
    score: float
    document_index: int


class KeywordStore:
    """
    Sparse retrieval store backed by BM25.
    """

    def __init__(
        self,
        storage_dir: Path | None = None,
        *,
        repository: str = "",
    ) -> None:
        # Each repository gets its own subdirectory so BM25 indexes never mix.
        # Path: storage/bm25/<repo_slug>/bm25.pkl
        self._repository = repository
        self._storage_dir = storage_dir or (
            settings.storage_root / BM25_DIRECTORY / _repo_slug(repository)
        )
        self._bm25: BM25Okapi | None = None
        self._chunks: list[Chunk] = []
        self._chunk_ids: list[str] = []
        self._tokenized_corpus: list[list[str]] = []
        self._deleted_chunk_ids: set[str] = set()

    @property
    def index_path(self) -> Path:
        return self._storage_dir / BM25_FILENAME

    @property
    def metadata_path(self) -> Path:
        return self._storage_dir / "bm25_metadata.json"

    def index(self, chunks: list[Chunk]) -> None:
        """
        Build the BM25 index from scratch.
        """
        self._chunks = []
        self._chunk_ids = []
        self._tokenized_corpus = []
        self._deleted_chunk_ids = set()

        seen: set[str] = set()

        for chunk in chunks:
            chunk_id = chunk.metadata.chunk_id

            if chunk_id in seen:
                logger.debug("Skipping duplicate chunk ID in BM25 index.")
                continue

            seen.add(chunk_id)
            self._chunks.append(chunk)
            self._chunk_ids.append(chunk_id)
            self._tokenized_corpus.append(self._tokenize(chunk.content))

        if self._chunks:
            self._repository = self._chunks[0].metadata.repository

        self._bm25 = (
            BM25Okapi(self._tokenized_corpus)
            if self._tokenized_corpus
            else None
        )

        logger.info("Indexed %d documents for BM25.", len(self._chunks))

    def search(
        self,
        query: str,
        top_k: int = 10,
        *,
        keywords: Optional[list[str]] = None,
    ) -> list[KeywordSearchHit]:
        """
        Search the BM25 index for relevant chunks.
        """
        if self._bm25 is None or not self._tokenized_corpus:
            return []

        query_tokens = self._tokenize(query)

        if keywords:
            for keyword in keywords:
                query_tokens.extend(self._tokenize(keyword))

        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda index: scores[index],
            reverse=True,
        )

        hits: list[KeywordSearchHit] = []

        for document_index in ranked_indices:
            score = float(scores[document_index])

            if score <= 0:
                continue

            chunk = self._chunks[document_index]
            chunk_id = chunk.metadata.chunk_id

            if chunk_id in self._deleted_chunk_ids:
                continue

            if not chunk.metadata.active:
                continue

            hits.append(
                KeywordSearchHit(
                    chunk=chunk,
                    score=score,
                    document_index=document_index,
                ),
            )

            if len(hits) >= top_k:
                break

        return hits

    def update(self, chunk: Chunk) -> None:
        """
        Replace one document in the BM25 index.
        """
        self.delete(chunk.metadata.chunk_id, soft=False)
        self._append_document(chunk)
        self._rebuild_bm25()

    def delete(
        self,
        chunk_id: str,
        *,
        soft: bool = True,
    ) -> bool:
        """
        Remove a document from active BM25 retrieval.
        """
        if chunk_id not in self._chunk_ids:
            return False

        if soft:
            self._deleted_chunk_ids.add(chunk_id)
            return True

        index = self._chunk_ids.index(chunk_id)
        self._chunks.pop(index)
        self._chunk_ids.pop(index)
        self._tokenized_corpus.pop(index)
        self._deleted_chunk_ids.discard(chunk_id)
        self._rebuild_bm25()
        return True

    def save(self) -> None:
        """
        Persist the BM25 index and metadata.
        """
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        with self.index_path.open("wb") as handle:
            pickle.dump(
                {
                    "bm25": self._bm25,
                    "tokenized_corpus": self._tokenized_corpus,
                },
                handle,
            )

        payload = {
            "repository": self._repository,
            "deleted_chunk_ids": sorted(self._deleted_chunk_ids),
            "chunks": [
                chunk.model_dump(mode="json") for chunk in self._chunks
            ],
        }
        self.metadata_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def load(self, storage_dir: Path | None = None) -> None:
        """
        Load a persisted BM25 index and metadata.
        """
        if storage_dir is not None:
            self._storage_dir = storage_dir

        if not self.index_path.exists() or not self.metadata_path.exists():
            raise FileNotFoundError(
                f"BM25 store not found in {self._storage_dir}",
            )

        with self.index_path.open("rb") as handle:
            payload = pickle.load(handle)

        self._bm25 = payload.get("bm25")
        self._tokenized_corpus = payload.get("tokenized_corpus", [])

        metadata = json.loads(
            self.metadata_path.read_text(encoding="utf-8"),
        )
        self._repository = metadata.get("repository", "")
        self._deleted_chunk_ids = set(metadata.get("deleted_chunk_ids", []))
        self._chunks = [
            Chunk.model_validate(item)
            for item in metadata.get("chunks", [])
        ]
        self._chunk_ids = [
            chunk.metadata.chunk_id for chunk in self._chunks
        ]

        if self._tokenized_corpus and self._bm25 is None:
            self._bm25 = BM25Okapi(self._tokenized_corpus)

        logger.info(
            "Loaded BM25 index with %d documents.",
            len(self._chunks),
        )

    def get_chunks_by_file(self, file_path: str) -> list[Chunk]:
        """
        Return active chunks for one file path.
        """
        return [
            chunk
            for chunk in self._chunks
            if chunk.metadata.file_path == file_path
            and chunk.metadata.active
            and chunk.metadata.chunk_id not in self._deleted_chunk_ids
        ]

    def get_all_active_chunks(self) -> list[Chunk]:
        """
        Return every active chunk in the keyword index.
        """
        return [
            chunk
            for chunk in self._chunks
            if chunk.metadata.active
            and chunk.metadata.chunk_id not in self._deleted_chunk_ids
        ]

    def statistics(self) -> KeywordStoreStatistics:
        """
        Return BM25 store statistics.
        """
        total = len(self._chunks)
        deleted = len(self._deleted_chunk_ids)
        active = total - deleted

        return KeywordStoreStatistics(
            total_documents=total,
            active_documents=active,
            deleted_documents=deleted,
            repository=self._repository,
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """
        Tokenize text for BM25 retrieval.
        """
        return [
            token.lower()
            for token in _TOKEN_PATTERN.findall(text)
            if token
        ]

    def _append_document(self, chunk: Chunk) -> None:
        self._chunks.append(chunk)
        self._chunk_ids.append(chunk.metadata.chunk_id)
        self._tokenized_corpus.append(self._tokenize(chunk.content))

    def _rebuild_bm25(self) -> None:
        self._bm25 = (
            BM25Okapi(self._tokenized_corpus)
            if self._tokenized_corpus
            else None
        )
