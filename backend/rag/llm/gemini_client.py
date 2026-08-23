"""
rag/llm/gemini_client.py
--------------------------
Google Gemini LLM client implementation for the RAG module.

Implements the BaseLLM interface using the google-generativeai SDK
(installed as part of langchain-google-genai). This allows the RAG
semantic query refinement pipeline to use Gemini when Groq is not
configured.
"""

from __future__ import annotations

from typing import Optional

from rag.llm.base import BaseLLM
from rag.utils import get_logger

logger = get_logger(__name__)


class GeminiClient(BaseLLM):
    """
    Google Gemini implementation of BaseLLM for the RAG module.

    Uses the google-generativeai Python SDK. Compatible with any
    Gemini text model (gemini-1.5-flash, gemini-1.5-pro, etc.).

    Args:
        api_key:    Google Gemini API key (GEMINI_API_KEY).
        model_name: Gemini model to use.
        temperature: Sampling temperature (0.0 = deterministic).
        max_tokens:  Maximum output tokens.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-1.5-flash",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self.api_key = api_key
        self._client = None  # lazy init

    def _get_client(self):
        """Lazy-initialise the Gemini GenerativeModel client."""
        if self._client is None:
            try:
                import google.generativeai as genai  # type: ignore
            except ImportError as exc:
                raise ImportError(
                    "google-generativeai is required for GeminiClient. "
                    "Install it with: pip install langchain-google-genai"
                ) from exc

            genai.configure(api_key=self.api_key)
            generation_config = {
                "temperature": self.temperature,
            }
            if self.max_tokens is not None:
                generation_config["max_output_tokens"] = self.max_tokens

            self._client = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config,
            )
            logger.info(
                "GeminiClient: initialised model='%s'", self.model_name
            )
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate a response using Google Gemini.

        Args:
            prompt:        User prompt.
            system_prompt: Optional system-level instruction
                           (prepended to the user prompt).

        Returns:
            str: Generated text.

        Raises:
            RuntimeError: If Gemini returns an error or empty response.
        """
        client = self._get_client()

        # Gemini 1.x doesn't have a dedicated system role in the basic API.
        # Prepend the system prompt to the user prompt when provided.
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        try:
            logger.debug(
                "GeminiClient.generate: model='%s'  prompt_len=%d",
                self.model_name,
                len(full_prompt),
            )
            response = client.generate_content(full_prompt)
            text = response.text.strip() if response.text else ""

            if not text:
                raise RuntimeError("Gemini returned an empty response.")

            logger.debug(
                "GeminiClient.generate: success (model='%s')", self.model_name
            )
            return text

        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception("GeminiClient.generate failed.")
            raise RuntimeError(f"Gemini API error: {exc}") from exc

    def health_check(self) -> bool:
        """Return True if the Gemini API is reachable with this key."""
        try:
            client = self._get_client()
            response = client.generate_content("ping")
            return bool(response.text)
        except Exception:
            return False
