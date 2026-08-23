"""
services/llm_service.py
------------------------
LLM Service — powered by LangChain.

Replaces the former raw-httpx implementation with proper LangChain
chat model integration. The public generate(prompt) interface is
preserved so all agents remain unchanged.

Provider priority (first key found wins):
  1. Groq  — GROQ_API_KEY  → langchain_groq.ChatGroq
  2. Gemini — GEMINI_API_KEY → langchain_google_genai.ChatGoogleGenerativeAI
  3. OpenAI — OPENAI_API_KEY → langchain_openai.ChatOpenAI
  4. Mock  — no key found    → deterministic stub for local development

LangChain advantages over raw httpx:
  - Built-in retry with exponential back-off
  - Streaming support (via .stream())
  - Chain composition with | operator
  - Consistent HumanMessage / AIMessage contract
  - Provider-agnostic interface
"""

import logging
import os
import re
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)


class LLMService:
    """
    Centralised LLM service backed by LangChain chat models.

    Usage (from agents)::

        llm = LLMService()
        response: str = llm.generate("Explain this code...")

    Usage (building chains)::

        llm = LLMService()
        chain = some_prompt | llm.get_langchain_llm() | StrOutputParser()
        result = chain.invoke({...})

    Attributes:
        model:        Active model name loaded from LLM_MODEL env var.
        groq_key:     Groq API key (GROQ_API_KEY).
        gemini_key:   Gemini API key (GEMINI_API_KEY).
        openai_key:   OpenAI API key (OPENAI_API_KEY).
        max_retries:  Number of retries on transient failures (MAX_RETRIES).
    """

    def __init__(self) -> None:
        self.gemini_key: str = os.getenv("GEMINI_API_KEY", "")
        self.groq_key: str   = os.getenv("GROQ_API_KEY", "")
        self.openai_key: str = os.getenv("OPENAI_API_KEY", "")
        self.max_retries: int = int(os.getenv("MAX_RETRIES", "3"))

        # Provider priority: Gemini → Groq → OpenAI → Mock
        # Gemini 1.5 Flash has a 1 M token context window — ideal for large repos.
        if self.gemini_key:
            default_model = "gemini-3.5-flash-lite"
        elif self.groq_key:
            default_model = "llama-3.3-70b-specdec"
        else:
            default_model = "gemini-3.5-flash-lite"
        self.model: str = os.getenv("LLM_MODEL", default_model)

        # Build the underlying LangChain LLM
        self._llm = self._build_langchain_llm()

        # Pre-build a simple str-output chain for generate()
        self._chain = (self._llm | StrOutputParser()) if self._llm is not None else None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(self, prompt: str) -> str:
        """
        Send a prompt to the configured LLM and return the response text.

        This is the primary interface used by all agents. The prompt is
        wrapped in a HumanMessage and sent through the LangChain chain.

        Args:
            prompt: Complete prompt string (may include retrieved context).

        Returns:
            str: Raw LLM response text.

        Raises:
            RuntimeError: If the LLM call fails after all retries.
        """
        if self._chain is not None:
            try:
                logger.info(
                    "LLMService.generate: invoking %s (model=%s)",
                    type(self._llm).__name__, self.model,
                )
                raw = self._chain.invoke([HumanMessage(content=prompt)])
                return self._strip_thinking_tags(raw)
            except Exception as exc:
                logger.error("LangChain LLM call failed: %s", exc)
                raise RuntimeError(f"LLM call failed: {exc}") from exc

        # No real LLM configured — use mock fallback
        logger.warning(
            "LLMService: no API key found (GROQ_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY). "
            "Falling back to mock generator."
        )
        return self._mock_generate(prompt)

    @staticmethod
    def _strip_thinking_tags(text: str) -> str:
        """Remove <think>...</think> reasoning blocks from LLM output.

        Some models (e.g. Qwen3, DeepSeek-R1) emit internal chain-of-thought
        wrapped in ``<think>`` tags before the actual structured answer.  Our
        section parsers only recognise lines like ``SECTION_NAME:`` so the
        thinking content must be stripped before returning to callers.

        Handles two cases:
        1. Full block: ``<think>...</think>answer`` → returns ``answer``.
        2. Unclosed tag: ``<think>thinking only`` (model hit token limit
           mid-thought) → the response contains no real answer; returns ``""``.

        Args:
            text: Raw LLM response text, possibly containing <think> blocks.

        Returns:
            str: Response with all <think>...</think> content removed and
                 leading/trailing whitespace stripped. May be empty string if
                 the entire response was a thinking block.
        """
        # Case 1: properly closed — strip complete blocks, keep what follows
        if "</think>" in text:
            cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            return cleaned.strip()

        # Case 2: unclosed tag — entire response is thinking, no real answer yet
        if "<think>" in text:
            logger.warning(
                "LLMService: LLM response contains only an unclosed <think> block "
                "(model likely hit token limit mid-thought). Returning empty string."
            )
            return ""

        # No thinking tags — return as-is
        return text.strip()

    def get_langchain_llm(self):
        """
        Return the underlying LangChain BaseChatModel instance.

        Use this when building custom LangChain chains or LangGraph nodes
        that need direct access to the chat model.

        Returns:
            BaseChatModel | None: Configured LangChain LLM, or None if mock.
        """
        return self._llm

    # ------------------------------------------------------------------
    # Provider construction
    # ------------------------------------------------------------------

    def _build_langchain_llm(self):
        """
        Detect available API keys and construct the appropriate LangChain LLM.

        Priority: Gemini → Groq → OpenAI → None (mock fallback).

        Returns:
            BaseChatModel | None: LangChain chat model, or None if no key found.
        """
        if self.gemini_key:
            llm = self._build_gemini()
            if llm is not None:
                return llm

        if self.groq_key:
            return self._build_groq()

        if self.openai_key:
            llm = self._build_openai()
            if llm is not None:
                return llm

        return None


    def _build_groq(self):
        """Build ChatGroq from langchain-groq.

        Returns:
            ChatGroq: Configured Groq chat model.

        Raises:
            ImportError: If langchain-groq is not installed.
        """
        try:
            from langchain_groq import ChatGroq  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "langchain-groq is required. "
                "Install it with: pip install langchain-groq"
            ) from exc

        logger.info(
            "LLMService: initialised ChatGroq (model=%s, max_retries=%d)",
            self.model, self.max_retries,
        )
        return ChatGroq(
            model=self.model,
            groq_api_key=self.groq_key,
            temperature=0.2,
            max_retries=self.max_retries,
        )

    def _build_gemini(self):
        """Build ChatGoogleGenerativeAI from langchain-google-genai.

        Returns:
            ChatGoogleGenerativeAI | None: Gemini model, or None if not installed.
        """
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
        except ImportError:
            logger.warning(
                "langchain-google-genai not installed. "
                "Install it with: pip install langchain-google-genai"
            )
            return None

        model = self.model if "gemini" in self.model else "gemini-1.5-flash"
        logger.info("LLMService: initialised ChatGoogleGenerativeAI (model=%s)", model)
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=self.gemini_key,
            temperature=0.2,
        )

    def _build_openai(self):
        """Build ChatOpenAI from langchain-openai.

        Returns:
            ChatOpenAI | None: OpenAI model, or None if not installed.
        """
        try:
            from langchain_openai import ChatOpenAI  # type: ignore
        except ImportError:
            logger.warning(
                "langchain-openai not installed. "
                "Install it with: pip install langchain-openai"
            )
            return None

        model = self.model if "gpt" in self.model else "gpt-4o-mini"
        logger.info("LLMService: initialised ChatOpenAI (model=%s)", model)
        return ChatOpenAI(
            model=model,
            openai_api_key=self.openai_key,
            temperature=0.2,
            max_retries=self.max_retries,
        )

    # ------------------------------------------------------------------
    # Mock fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_generate(prompt: str) -> str:
        """
        Return a stub response for local development when no API key is set.

        This path is only taken when GROQ_API_KEY / GEMINI_API_KEY /
        OPENAI_API_KEY are all absent from the environment.

        Args:
            prompt: The prompt that would have been sent to a real LLM.

        Returns:
            str: A minimal placeholder string.
        """
        logger.warning(
            "LLMService._mock_generate called — no LLM API key configured. "
            "Set GROQ_API_KEY in your .env to use the real LLM."
        )
        return (
            "## Overview\n\nNo LLM API key configured. "
            "Set GROQ_API_KEY in your .env file.\n\n"
            "## Change Summary\n\nN/A\n\n"
            "## Key Components\n\nN/A\n"
        )
