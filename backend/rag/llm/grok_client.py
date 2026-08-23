"""
Grok LLM client implementation.

This module implements the BaseLLM interface using the
OpenAI-compatible REST API exposed by Grok.
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


class GrokClient(BaseLLM):
    """
    Grok implementation of BaseLLM.

    Uses an OpenAI-compatible Chat Completions API.
    """

    def __init__(
        self,
        api_key: str,
        model_name: Optional[str] = None,
        base_url: str = "https://api.x.ai/v1",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> None:
        """
        Initialize the Grok client.

        Parameters
        ----------
        api_key : str
            API key.

        model_name : str | None
            Model name.

        base_url : str
            Base API URL.

        temperature : float
            Sampling temperature.

        max_tokens : int | None
            Maximum number of generated tokens.
        """

        super().__init__(
            model_name=model_name or settings.llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

        self.timeout = settings.ollama_timeout

        self.session = requests.Session()

        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    @property
    def chat_url(self) -> str:
        """
        Chat completion endpoint.
        """
        return f"{self.base_url}/chat/completions"

    @property
    def models_url(self) -> str:
        """
        Models endpoint.
        """
        return f"{self.base_url}/models"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate a response using Grok.

        Parameters
        ----------
        prompt : str

        system_prompt : str | None

        Returns
        -------
        str

        Raises
        ------
        RuntimeError
            If generation fails.
        """

        messages = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }

        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        try:

            logger.debug(
                "Generating response using Grok model '%s'.",
                self.model_name,
            )

            response = self.session.post(
                self.chat_url,
                json=payload,
                timeout=self.timeout,
            )

            self._raise_for_status(response)

            data = response.json()

            text = (
                data["choices"][0]["message"]["content"]
                .strip()
            )

            if not text:
                raise RuntimeError(
                    "Grok returned an empty response."
                )

            logger.debug(
                "Generation completed successfully."
            )

            return text

        except Timeout as exc:

            logger.exception(
                "Request to Grok timed out."
            )

            raise RuntimeError(
                "Timed out while communicating with Grok."
            ) from exc

        except (RequestException, KeyError, IndexError) as exc:

            logger.exception(
                "Failed to generate response using Grok."
            )

            raise RuntimeError(
                "Unable to communicate with the Grok API."
            ) from exc

    def health_check(self) -> bool:
        """
        Check whether the Grok API is reachable.

        Returns
        -------
        bool
        """

        try:

            response = self.session.get(
                self.models_url,
                timeout=5,
            )

            return response.status_code == 200

        except RequestException:

            return False

    @staticmethod
    def _raise_for_status(
        response: Response,
    ) -> None:
        """
        Validate an HTTP response.

        Parameters
        ----------
        response : Response

        Raises
        ------
        RuntimeError
        """

        try:

            response.raise_for_status()

        except RequestException as exc:

            raise RuntimeError(
                f"Grok request failed "
                f"({response.status_code})."
            ) from exc