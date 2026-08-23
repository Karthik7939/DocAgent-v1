"""
Embedding provider abstractions for the RAG pipeline.

This module mirrors the LLM abstraction layer. The rest of the RAG
system depends only on ``BaseEmbeddingModel``, making it easy to swap
embedding providers without changing pipeline logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import requests
from requests.exceptions import RequestException, Timeout

from rag.config import settings
from rag.utils import get_logger

logger = get_logger(__name__)


class BaseEmbeddingModel(ABC):
    """
    Abstract interface for all embedding providers.
    """

    def __init__(
        self,
        model_name: str,
        model_version: str = "1",
    ) -> None:
        self._model_name = model_name
        self._model_version = model_version
        self._dimension: Optional[int] = None

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """
        Generate an embedding vector for one text input.
        """
        raise NotImplementedError

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for multiple texts.
        """
        raise NotImplementedError

    @abstractmethod
    def dimension(self) -> int:
        """
        Return the embedding vector dimension for this model.
        """
        raise NotImplementedError

    def model_name(self) -> str:
        """
        Return the configured model name.
        """
        return self._model_name

    def model_version(self) -> str:
        """
        Return the configured model version string.
        """
        return self._model_version

    @property
    def provider_name(self) -> str:
        """
        Return the provider implementation name.
        """
        return self.__class__.__name__

    def health_check(self) -> bool:
        """
        Check whether the embedding provider is available.
        """
        try:
            vector = self.embed("health check")
            return len(vector) == self.dimension()
        except Exception:
            return False

    def __repr__(self) -> str:
        return (
            f"{self.provider_name}"
            f"(model='{self._model_name}', "
            f"version='{self._model_version}')"
        )


class OllamaEmbedding(BaseEmbeddingModel):
    """
    Ollama embedding provider using the ``/api/embed`` endpoint.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(
            model_name=model_name or settings.embedding_model,
            model_version=model_version or settings.embedding_model_version,
        )
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._timeout = timeout or settings.ollama_timeout

    @property
    def embed_url(self) -> str:
        return f"{self._base_url}/api/embed"

    def health_check(self) -> bool:
        """
        Check whether Ollama is available for embedding requests.
        """
        try:
            response = requests.get(
                f"{self._base_url}/api/tags",
                timeout=5,
            )
            return response.status_code == 200
        except RequestException:
            return False

    def embed(self, text: str) -> list[float]:
        vectors = self.embed_batch([text])
        return vectors[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        payload = {
            "model": self._model_name,
            "input": texts if len(texts) > 1 else texts[0],
        }

        try:
            response = requests.post(
                self.embed_url,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Timeout as exc:
            raise RuntimeError(
                "Timed out while requesting embeddings from Ollama.",
            ) from exc
        except RequestException as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                body = response.text[:500].strip()
                raise RuntimeError(
                    "Unable to request embeddings from Ollama "
                    f"(status={response.status_code}, body={body!r}).",
                ) from exc

            raise RuntimeError(
                f"Unable to request embeddings from Ollama: {exc}",
            ) from exc

        embeddings = data.get("embeddings")

        if embeddings is None and "embedding" in data:
            embeddings = [data["embedding"]]

        if not embeddings:
            raise RuntimeError(
                "Ollama returned an empty embedding response.",
            )

        if len(embeddings) != len(texts):
            raise RuntimeError(
                "Ollama returned an unexpected number of embeddings.",
            )

        self._dimension = len(embeddings[0])
        return [list(vector) for vector in embeddings]

    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed("dimension probe"))
        return self._dimension


class SentenceTransformerEmbedding(BaseEmbeddingModel):
    """
    Sentence Transformers embedding provider.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> None:
        super().__init__(
            model_name=model_name or settings.embedding_model,
            model_version=model_version or settings.embedding_model_version,
        )
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed.",
            ) from exc

        logger.info(
            "Loading sentence-transformers model '%s'.",
            self._model_name,
        )
        self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        vectors = self.embed_batch([text])
        return vectors[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._load_model()
        vectors = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        embeddings = [vector.tolist() for vector in vectors]
        self._dimension = len(embeddings[0])
        return embeddings

    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed("dimension probe"))
        return self._dimension


class OpenAIEmbedding(BaseEmbeddingModel):
    """
    OpenAI embedding provider placeholder for future integration.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        super().__init__(
            model_name=model_name or settings.embedding_model,
            model_version=model_version or settings.embedding_model_version,
        )
        self._api_key = api_key or getattr(settings, "openai_api_key", None)

        if not self._api_key:
            raise ValueError("OpenAI API key is not configured.")

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "OpenAIEmbedding is reserved for future integration.",
        )

    def dimension(self) -> int:
        raise NotImplementedError(
            "OpenAIEmbedding is reserved for future integration.",
        )


class EmbeddingModelFactory:
    """
    Factory for creating embedding provider instances.
    """

    @staticmethod
    def create(
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> BaseEmbeddingModel:
        selected = (provider or settings.embedding_provider).lower()

        match selected:
            case "ollama":
                return OllamaEmbedding(
                    model_name=model_name,
                    model_version=model_version,
                )

            case "sentence-transformers" | "sentence_transformers":
                return SentenceTransformerEmbedding(
                    model_name=model_name,
                    model_version=model_version,
                )

            case "openai":
                return OpenAIEmbedding(
                    model_name=model_name,
                    model_version=model_version,
                )

            case _:
                raise ValueError(
                    f"Unsupported embedding provider: {selected}",
                )
