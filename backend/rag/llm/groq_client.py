"""
rag/llm/groq_client.py
-----------------------
Groq (groq.com) LLM client implementation for the RAG module.

NOTE: This is for Groq (groq.com) -- NOT xAI Grok (grok.com).
      Groq runs open-source models (llama-3.3-70b, mixtral, etc.)
      at extremely high speed via custom LPU hardware.
      The existing grok_client.py targets the xAI Grok API instead.

Implements the BaseLLM interface using Groq's OpenAI-compatible
Chat Completions API at https://api.groq.com/openai/v1.
"""

from __future__ import annotations

import time
from typing import Optional

import requests
from requests import Response
from requests.exceptions import RequestException, Timeout

from rag.config import settings
from rag.llm.base import BaseLLM
from rag.utils import get_logger

logger = get_logger(__name__)

# Groq's OpenAI-compatible endpoint
GROQ_API_BASE = "https://api.groq.com/openai/v1"

# HTTP 429 = rate limit exceeded
RATE_LIMIT_STATUS = 429


class GroqClient(BaseLLM):
    """
    Groq implementation of BaseLLM.

    Uses Groq's OpenAI-compatible Chat Completions REST API.
    Suitable for fast semantic query refinement within the RAG pipeline.

    Args:
        api_key:    Groq API key (GROQ_API_KEY or RAG_GROQ_API_KEY).
        model_name: Model to use (e.g. 'llama-3.3-70b-versatile').
                    Falls back to settings.llm_model if not provided.
        temperature: Sampling temperature (0.0 = deterministic).
        max_tokens:  Maximum tokens to generate.
        timeout:     Request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(
            model_name=model_name or settings.llm_model or "llama-3.3-70b-versatile",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self.api_key = api_key
        self.timeout = timeout or settings.ollama_timeout or 30

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    @property
    def chat_url(self) -> str:
        return f"{GROQ_API_BASE}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{GROQ_API_BASE}/models"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate a response using Groq.

        Args:
            prompt:        User prompt.
            system_prompt: Optional system-level instruction.

        Returns:
            str: Generated text.

        Raises:
            RuntimeError: If Groq returns an error or empty response.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        try:
            logger.debug(
                "Groq generate: model='%s'  prompt_len=%d",
                self.model_name,
                len(prompt),
            )

            response = self.session.post(
                self.chat_url,
                json=payload,
                timeout=self.timeout,
            )
            self._raise_for_status(response)

            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()

            if not text:
                raise RuntimeError("Groq returned an empty response.")

            logger.debug("Groq generate: success (model='%s')", self.model_name)
            return text

        except Timeout as exc:
            raise RuntimeError(
                f"Groq request timed out after {self.timeout}s."
            ) from exc

        except (RequestException, KeyError, IndexError) as exc:
            logger.exception("Groq generate failed.")
            raise RuntimeError(
                f"Groq API error: {exc}"
            ) from exc

    def is_rate_limited(self, response: Response) -> bool:
        """Return True if the response indicates a rate limit hit."""
        return response.status_code == RATE_LIMIT_STATUS

    def health_check(self) -> bool:
        """Return True if the Groq API is reachable with this key."""
        try:
            response = self.session.get(self.models_url, timeout=5)
            return response.status_code == 200
        except RequestException:
            return False

    @staticmethod
    def _raise_for_status(response: Response) -> None:
        """Raise RuntimeError for non-2xx responses."""
        try:
            response.raise_for_status()
        except RequestException as exc:
            body = ""
            try:
                body = response.json().get("error", {}).get("message", "")
            except Exception:
                pass
            raise RuntimeError(
                f"Groq request failed ({response.status_code})"
                + (f": {body}" if body else "")
            ) from exc
