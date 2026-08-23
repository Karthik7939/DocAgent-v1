"""
Persistent embedding cache for the RAG pipeline.

Embeddings are keyed by content hash, embedding model name, and model
version so unchanged content can be reused even when chunk identifiers
change.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from rag.config import settings
from rag.config.constants import (
    EMBEDDING_CACHE_DIRECTORY,
    EMBEDDING_CACHE_FILENAME,
)
from rag.utils import get_logger
from rag.utils.hashing import generate_hash

logger = get_logger(__name__)


class CacheStatistics(BaseModel):
    """
    Statistics for the embedding cache.
    """

    model_config = ConfigDict(frozen=True)

    total_entries: int = Field(default=0, ge=0)
    hits: int = Field(default=0, ge=0)
    misses: int = Field(default=0, ge=0)
    saves: int = Field(default=0, ge=0)
    deletes: int = Field(default=0, ge=0)


class EmbeddingCache:
    """
    JSON-backed embedding cache with in-process locking.
    """

    def __init__(
        self,
        cache_path: Path | None = None,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> None:
        self._cache_path = cache_path or (
            settings.storage_root
            / EMBEDDING_CACHE_DIRECTORY
            / EMBEDDING_CACHE_FILENAME
        )
        self._model_name = model_name or settings.embedding_model
        self._model_version = (
            model_version or settings.embedding_model_version
        )
        self._lock = threading.RLock()
        self._stats = CacheStatistics()
        self._entries: dict[str, dict] = {}
        self._loaded = False

    @property
    def cache_path(self) -> Path:
        return self._cache_path

    def build_key(
        self,
        content_hash: str,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> str:
        """
        Build a stable cache key from content and model metadata.
        """
        return generate_hash(
            (
                f"{content_hash}:"
                f"{model_name or self._model_name}:"
                f"{model_version or self._model_version}"
            ),
        )

    def exists(
        self,
        content_hash: str,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> bool:
        """
        Check whether a cached embedding exists.
        """
        self._ensure_loaded()
        key = self.build_key(
            content_hash,
            model_name,
            model_version,
        )
        return key in self._entries

    def load(
        self,
        content_hash: str,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> list[float] | None:
        """
        Load a cached embedding vector.
        """
        self._ensure_loaded()
        key = self.build_key(
            content_hash,
            model_name,
            model_version,
        )

        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                self._stats = self._stats.model_copy(
                    update={"misses": self._stats.misses + 1},
                )
                return None

            if entry.get("content_hash") != content_hash:
                logger.warning(
                    "Cache hash mismatch for key %s.",
                    key,
                )
                self._stats = self._stats.model_copy(
                    update={"misses": self._stats.misses + 1},
                )
                return None

            self._stats = self._stats.model_copy(
                update={"hits": self._stats.hits + 1},
            )
            return list(entry["embedding"])

    def save(
        self,
        content_hash: str,
        embedding: list[float],
        *,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> None:
        """
        Persist one embedding vector to the cache.
        """
        self._ensure_loaded()
        key = self.build_key(
            content_hash,
            model_name,
            model_version,
        )

        with self._lock:
            self._entries[key] = {
                "content_hash": content_hash,
                "embedding_model": model_name or self._model_name,
                "model_version": model_version or self._model_version,
                "dimension": len(embedding),
                "embedding": embedding,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._stats = self._stats.model_copy(
                update={
                    "saves": self._stats.saves + 1,
                    "total_entries": len(self._entries),
                },
            )
            self._persist()

    def delete(
        self,
        content_hash: str,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> bool:
        """
        Delete one cache entry.
        """
        self._ensure_loaded()
        key = self.build_key(
            content_hash,
            model_name,
            model_version,
        )

        with self._lock:
            if key not in self._entries:
                return False

            del self._entries[key]
            self._stats = self._stats.model_copy(
                update={
                    "deletes": self._stats.deletes + 1,
                    "total_entries": len(self._entries),
                },
            )
            self._persist()
            return True

    def clear(self) -> None:
        """
        Remove all cache entries.
        """
        with self._lock:
            self._entries = {}
            self._stats = CacheStatistics()
            self._persist()

    def statistics(self) -> CacheStatistics:
        """
        Return cache usage statistics.
        """
        self._ensure_loaded()
        return self._stats.model_copy(
            update={"total_entries": len(self._entries)},
        )

    def purge_stale(
        self,
        *,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> int:
        """
        Delete entries that do not match the current model metadata.
        """
        self._ensure_loaded()
        target_model = model_name or self._model_name
        target_version = model_version or self._model_version
        removed = 0

        with self._lock:
            stale_keys = [
                key
                for key, entry in self._entries.items()
                if entry.get("embedding_model") != target_model
                or entry.get("model_version") != target_version
            ]

            for key in stale_keys:
                del self._entries[key]
                removed += 1

            if removed:
                self._stats = self._stats.model_copy(
                    update={
                        "deletes": self._stats.deletes + removed,
                        "total_entries": len(self._entries),
                    },
                )
                self._persist()

        return removed

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            if not self._cache_path.exists():
                self._entries = {}
                self._loaded = True
                return

            try:
                payload = json.loads(
                    self._cache_path.read_text(encoding="utf-8"),
                )
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Embedding cache is corrupt at %s: %s",
                    self._cache_path,
                    exc,
                )
                self._entries = {}
                self._loaded = True
                self._persist()
                return

            if payload.get("model") != self._model_name:
                logger.info(
                    "Embedding cache model mismatch. Starting fresh cache.",
                )
                self._entries = {}
                self._loaded = True
                self._persist()
                return

            if payload.get("model_version") != self._model_version:
                logger.info(
                    "Embedding cache version mismatch. Starting fresh cache.",
                )
                self._entries = {}
                self._loaded = True
                self._persist()
                return

            self._entries = payload.get("entries", {})
            self._loaded = True

    def _persist(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self._model_name,
            "model_version": self._model_version,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": self._entries,
        }
        temp_path = self._cache_path.with_name(
            f"{self._cache_path.stem}.{uuid4().hex}.tmp",
        )
        temp_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

        last_error: OSError | None = None
        for attempt in range(5):
            try:
                os.replace(temp_path, self._cache_path)
                return
            except OSError as exc:
                last_error = exc
                if attempt < 4:
                    time.sleep(0.1 * (attempt + 1))

        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

        if last_error is not None:
            raise last_error
