"""
Ollama LLM client implementation.

This module implements the BaseLLM interface using Ollama's REST API.

Reference:
    POST /api/generate
"""

from __future__ import annotations

from typing import Optional

import requests
from requests import Response
from requests.exceptions import RequestException, Timeout

from rag.config import settings
from rag.llm.base import BaseLLM
from rag.utils import get_logger

logger = get_logger(__name__)


class OllamaClient(BaseLLM):
    """
    Ollama implementation of BaseLLM.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        num_ctx: Optional[int] = None,
    ) -> None:
        """
        Initialize the Ollama client.
        """
        configured_model = model_name or settings.llm_model
        if not configured_model:
            raise ValueError("OLLAMA_MODEL is not configured.")

        configured_base_url = settings.ollama_base_url
        if not configured_base_url:
            raise ValueError("OLLAMA_BASE_URL is not configured.")

        super().__init__(
            model_name=configured_model,
            temperature=(
                settings.ollama_temperature
                if temperature is None
                else temperature
            ),
            max_tokens=max_tokens,
        )

        self.base_url = configured_base_url.rstrip("/")
        self.timeout = settings.ollama_timeout
        self.top_p = settings.ollama_top_p if top_p is None else top_p
        self.num_ctx = settings.ollama_num_ctx if num_ctx is None else num_ctx

    @property
    def generate_url(self) -> str:
        """
        Returns the Ollama generate endpoint.
        """
        return f"{self.base_url}/api/generate"

    @property
    def tags_url(self) -> str:
        """
        Returns the Ollama tags endpoint.
        """
        return f"{self.base_url}/api/tags"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate a response using Ollama.

        Parameters
        ----------
        prompt : str
            User prompt.

        system_prompt : str | None
            Optional system prompt.

        Returns
        -------
        str
            Generated response.

        Raises
        ------
        RuntimeError
            If generation fails.
        """

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if self.max_tokens is not None:
            payload["options"]["num_predict"] = self.max_tokens

        if self.num_ctx is not None:
            payload["options"]["num_ctx"] = self.num_ctx

        try:

            logger.debug(
                "Generating response using model '%s'.",
                self.model_name,
            )

            response = requests.post(
                self.generate_url,
                json=payload,
                timeout=self.timeout,
            )

            self._raise_for_status(response)

            data = response.json()

            generated_text = data.get("response", "").strip()

            if not generated_text:
                raise RuntimeError(
                    "Ollama returned an empty response."
                )

            logger.debug("Generation completed successfully.")

            return generated_text

        except Timeout as exc:

            logger.exception("Ollama request timed out.")

            raise RuntimeError(
                "Timed out while communicating with Ollama."
            ) from exc

        except RequestException as exc:

            logger.exception("Failed to communicate with Ollama.")

            raise RuntimeError(
                "Unable to connect to the Ollama server."
            ) from exc

    def health_check(self) -> bool:
        """
        Check whether Ollama is available.

        Returns
        -------
        bool
        """

        try:

            response = requests.get(
                self.tags_url,
                timeout=5,
            )

            return response.status_code == 200

        except RequestException:

            return False

    @staticmethod
    def _raise_for_status(response: Response) -> None:
        """
        Validate HTTP response.

        Parameters
        ----------
        response : Response

        Raises
        ------
        RuntimeError
            If the request failed.
        """

        try:
            response.raise_for_status()

        except RequestException as exc:

            raise RuntimeError(
                f"Ollama request failed "
                f"({response.status_code})."
            ) from exc
