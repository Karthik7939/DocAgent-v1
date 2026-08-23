"""
Abstract base classes for Large Language Model (LLM) providers.

All LLM implementations (Ollama, Grok, OpenAI, etc.) must inherit from
BaseLLM and implement the required interface.

The rest of the RAG pipeline should interact only with this abstraction,
making it easy to switch providers without changing pipeline logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class BaseLLM(ABC):
    """
    Abstract interface for all LLM providers.
    """

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> None:
        """
        Initialize the LLM provider.

        Parameters
        ----------
        model_name : str
            Name of the model.

        temperature : float, default=0.0
            Sampling temperature.

        max_tokens : int | None
            Maximum tokens to generate.
        """

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate a response from the language model.

        Parameters
        ----------
        prompt : str
            User prompt.

        system_prompt : str | None
            Optional system prompt.

        Returns
        -------
        str
            Generated text.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check whether the provider is available.

        Returns
        -------
        bool
            True if the provider is reachable.
        """
        raise NotImplementedError

    @property
    def provider_name(self) -> str:
        """
        Returns the provider name.

        Returns
        -------
        str
        """
        return self.__class__.__name__

    def __repr__(self) -> str:
        """
        Developer-friendly representation.
        """
        return (
            f"{self.provider_name}"
            f"(model='{self.model_name}')"
        )