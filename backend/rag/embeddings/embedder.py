"""
Embedding orchestrator for the RAG pipeline.

The embedder coordinates embedding model providers and the embedding
cache. It returns vectors only and never interacts with FAISS directly.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

from rag.config import settings
from rag.embeddings.cache import EmbeddingCache
from rag.embeddings.embedding_models import (
    BaseEmbeddingModel,
    EmbeddingModelFactory,
)
from rag.schemas.chunk import Chunk
from rag.utils import get_logger
from rag.utils.tokenizer import truncate_to_token_limit

logger = get_logger(__name__)


@dataclass(slots=True)
class EmbedderStatistics:
    """
    Runtime statistics for embedding generation.
    """

    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    generated_vectors: int = 0
    failed_requests: int = 0
    retried_requests: int = 0
    total_batches: int = 0
    duplicate_chunks_skipped: int = 0
    total_vectors: int = 0


class Embedder:
    """
    Generate, cache, validate, and normalize embedding vectors.
    """

    def __init__(
        self,
        model: BaseEmbeddingModel | None = None,
        cache: EmbeddingCache | None = None,
        *,
        normalize: Optional[bool] = None,
        batch_size: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
        use_cache: Optional[bool] = None,
    ) -> None:
        self._model = model
        self._cache = cache
        self._normalize = (
            settings.embedding_normalize
            if normalize is None
            else normalize
        )
        self._batch_size = batch_size or settings.embedding_batch_size
        self._max_retries = (
            max_retries
            if max_retries is not None
            else settings.embedding_max_retries
        )
        self._retry_delay = retry_delay or settings.embedding_retry_delay
        self._use_cache = (
            settings.enable_embedding_cache
            if use_cache is None
            else use_cache
        )
        self._stats = EmbedderStatistics()
        self._expected_dimension: Optional[int] = None

    @property
    def model(self) -> BaseEmbeddingModel:
        """
        Lazily initialize the configured embedding model.
        """
        if self._model is None:
            self._model = EmbeddingModelFactory.create()
        return self._model

    @property
    def cache(self) -> EmbeddingCache:
        """
        Lazily initialize the embedding cache.
        """
        if self._cache is None:
            self._cache = EmbeddingCache(
                model_name=self.model.model_name(),
                model_version=self.model.model_version(),
            )
        return self._cache

    def embed_chunk(self, chunk: Chunk) -> Chunk:
        """
        Generate or load an embedding for one chunk.
        """
        if not chunk.content.strip():
            raise ValueError(
                f"Cannot embed empty chunk: {chunk.metadata.chunk_id}",
            )

        vector = self._resolve_vector(
            text=chunk.content,
            content_hash=chunk.metadata.content_hash,
        )
        return chunk.model_copy(update={"embedding": vector})

    def embed_chunks(self, chunks: list[Chunk], workflow_id: Optional[str] = None) -> list[Chunk]:
        """
        Generate embeddings for multiple chunks with batching and caching.
        """
        if not chunks:
            return []

        results: list[Optional[Chunk]] = [None] * len(chunks)
        pending: list[tuple[int, Chunk]] = []
        resolved_hashes: dict[str, list[float]] = {}
        deferred_duplicates: dict[int, str] = {}
        hash_first_index: dict[str, int] = {}

        for index, chunk in enumerate(chunks):
            if not chunk.content.strip():
                self._stats.failed_requests += 1
                logger.warning(
                    "Skipping empty chunk %s.",
                    chunk.metadata.chunk_id,
                )
                continue

            content_hash = chunk.metadata.content_hash

            cached = self._load_cached_vector(content_hash)
            if cached is not None:
                resolved_hashes[content_hash] = cached
                results[index] = chunk.model_copy(
                    update={"embedding": cached},
                )
                continue

            if content_hash in hash_first_index:
                self._stats.duplicate_chunks_skipped += 1
                deferred_duplicates[index] = content_hash
                continue

            hash_first_index[content_hash] = index
            pending.append((index, chunk))

        total_chunks = len(chunks)

        for batch_start in range(0, len(pending), self._batch_size):
            if workflow_id:
                from rag.pipeline.manager import check_cancelled
                try:
                    check_cancelled(workflow_id)
                except Exception:
                    raise

            batch = pending[batch_start:batch_start + self._batch_size]
            self._embed_pending_batch(
                batch,
                results,
                resolved_hashes,
                total_chunks=total_chunks,
            )

            if workflow_id:
                from rag.pipeline.events import EmbeddingGenerated
                from rag.pipeline.manager import handle_event
                completed = sum(1 for chunk in results if chunk is not None)
                try:
                    handle_event(EmbeddingGenerated(
                        workflow_id=workflow_id,
                        chunk_index=completed,
                        total_chunks=total_chunks
                    ))
                except Exception:
                    pass

        for index, content_hash in deferred_duplicates.items():
            vector = resolved_hashes.get(content_hash)

            if vector is None:
                self._stats.failed_requests += 1
                logger.error(
                    "Missing embedding for duplicate chunk %s.",
                    chunks[index].metadata.chunk_id,
                )
                continue

            results[index] = chunks[index].model_copy(
                update={"embedding": list(vector)},
            )

        embedded = [chunk for chunk in results if chunk is not None]
        self._stats.total_vectors = len(embedded)
        return embedded

    def embed_text(self, text: str) -> list[float]:
        """
        Generate an embedding for raw text.
        """
        if not text.strip():
            raise ValueError("Cannot embed empty text.")

        return self._generate_vector(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of raw texts.
        """
        cleaned = [text for text in texts if text.strip()]

        if not cleaned:
            return []

        vectors: list[list[float]] = []

        for batch_start in range(0, len(cleaned), self._batch_size):
            batch = cleaned[batch_start:batch_start + self._batch_size]
            vectors.extend(self._generate_batch(batch))

        return vectors

    def validate_embedding_dimension(
        self,
        vector: list[float],
    ) -> bool:
        """
        Validate that a vector matches the configured model dimension.
        """
        expected = self._expected_dimension or self.model.dimension()
        self._expected_dimension = expected
        return len(vector) == expected

    def clear_cache(self) -> None:
        """
        Clear the embedding cache.
        """
        if self._use_cache:
            self.cache.clear()

    def statistics(self) -> EmbedderStatistics:
        """
        Return embedder runtime statistics.
        """
        return self._stats

    def _resolve_vector(
        self,
        *,
        text: str,
        content_hash: str,
    ) -> list[float]:
        cached = self._load_cached_vector(content_hash)
        if cached is not None:
            return cached

        vector = self._generate_vector(text)
        self._store_cached_vector(content_hash, vector)
        return vector

    def _load_cached_vector(
        self,
        content_hash: str,
    ) -> list[float] | None:
        if not self._use_cache:
            return None

        vector = self.cache.load(
            content_hash,
            model_name=self.model.model_name(),
            model_version=self.model.model_version(),
        )

        if vector is None:
            self._stats.cache_misses += 1
            return None

        vector = self._post_process(vector)
        if not self.validate_embedding_dimension(vector):
            raise RuntimeError(
                "Cached embedding dimension does not match model dimension.",
            )

        self._stats.cache_hits += 1
        self._stats.total_requests += 1
        return vector

    def _store_cached_vector(
        self,
        content_hash: str,
        vector: list[float],
    ) -> None:
        if not self._use_cache:
            return

        try:
            self.cache.save(
                content_hash,
                vector,
                model_name=self.model.model_name(),
                model_version=self.model.model_version(),
            )
        except OSError as exc:
            logger.warning(
                "Embedding cache save failed; continuing without cache: %s",
                exc,
            )
            self._use_cache = False

    def _generate_vector(self, text: str) -> list[float]:
        vectors = self._generate_batch([text])
        return vectors[0]

    def _generate_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        self._stats.total_batches += 1
        last_error: Exception | None = None
        current_budget = settings.max_chunk_tokens

        for attempt in range(self._max_retries + 1):
            prepared_texts = self._prepare_texts_for_embedding(
                texts,
                max_tokens=current_budget,
            )

            try:
                vectors = self.model.embed_batch(prepared_texts)
                processed = [self._post_process(vector) for vector in vectors]

                for vector in processed:
                    if not self.validate_embedding_dimension(vector):
                        raise RuntimeError(
                            "Embedding dimension mismatch for model "
                            f"{self.model.model_name()}.",
                        )

                self._stats.generated_vectors += len(processed)
                self._stats.total_requests += len(processed)
                return processed

            except Exception as exc:
                last_error = exc
                self._stats.retried_requests += 1

                if self._is_context_length_error(exc) and current_budget > 64:
                    current_budget = max(64, current_budget // 2)

                if attempt >= self._max_retries:
                    break

                logger.warning(
                    "Embedding batch failed (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
                time.sleep(self._retry_delay)

        self._stats.failed_requests += len(texts)
        raise RuntimeError(
            "Failed to generate embeddings after retries.",
        ) from last_error

    def _embed_pending_batch(
        self,
        batch: list[tuple[int, Chunk]],
        results: list[Optional[Chunk]],
        resolved_hashes: dict[str, list[float]],
        *,
        total_chunks: int,
    ) -> None:
        texts = [chunk.content for _, chunk in batch]

        try:
            vectors = self._generate_batch(texts)
        except RuntimeError:
            for index, chunk in batch:
                try:
                    vector = self._generate_vector(chunk.content)
                except RuntimeError as exc:
                    logger.error(
                        "Failed to embed chunk %s: %s",
                        chunk.metadata.chunk_id,
                        exc,
                    )
                    continue

                self._store_cached_vector(
                    chunk.metadata.content_hash,
                    vector,
                )
                resolved_hashes[chunk.metadata.content_hash] = vector
                results[index] = chunk.model_copy(
                    update={"embedding": vector},
                )
            return

        for (index, chunk), vector in zip(batch, vectors, strict=True):
            self._store_cached_vector(
                chunk.metadata.content_hash,
                vector,
            )
            resolved_hashes[chunk.metadata.content_hash] = vector
            results[index] = chunk.model_copy(update={"embedding": vector})

        completed = sum(1 for chunk in results if chunk is not None)
        logger.info(
            "Embedded batch of %d chunks (%d/%d complete).",
            len(batch),
            completed,
            total_chunks,
        )

    def _post_process(self, vector: list[float]) -> list[float]:
        if not self._normalize:
            return vector
        return self._l2_normalize(vector)

    def _prepare_texts_for_embedding(
        self,
        texts: list[str],
        *,
        max_tokens: int | None = None,
    ) -> list[str]:
        """
        Normalize and truncate texts before sending them to the embedding provider.

        The provider-facing limit reuses the repository-wide chunk token budget,
        which keeps embeddings within a conservative context window without
        changing any downstream APIs.
        """
        token_budget = max_tokens or settings.max_chunk_tokens
        prepared: list[str] = []

        for text in texts:
            normalized = text.strip()
            truncated = truncate_to_token_limit(normalized, token_budget)
            prepared.append(truncated)

        return prepared

    @staticmethod
    def _is_context_length_error(error: Exception) -> bool:
        message = str(error).lower()
        return "context length" in message or "input length exceeds" in message

    @staticmethod
    def _l2_normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))

        if norm == 0:
            return vector

        return [value / norm for value in vector]
