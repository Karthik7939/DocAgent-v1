"""
LLM provider implementations for the RAG system.

This package provides a provider-agnostic interface for interacting with
Large Language Models (LLMs). New providers can be added by implementing
the BaseLLM interface and registering them in the LLMFactory.

Supported providers:
  groq   -- Groq (groq.com), fast LPU-based inference. Supports
             dual-key round-robin load balancing via MultiKeyGroqClient.
  grok   -- xAI Grok (grok.com), OpenAI-compatible API.
  ollama -- Local Ollama server, no API key required.
"""

from .base import BaseLLM
from .factory import LLMFactory
from .grok_client import GrokClient
from .groq_client import GroqClient
from .multi_key_client import MultiKeyGroqClient
from .ollama_client import OllamaClient

__all__ = [
    "BaseLLM",
    "OllamaClient",
    "GrokClient",
    "GroqClient",
    "MultiKeyGroqClient",
    "LLMFactory",
]