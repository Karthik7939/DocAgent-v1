"""
rag/llm/multi_key_client.py
-----------------------------
Multi-key load balancer for Groq API clients.

Groq enforces per-key rate limits (RPM, TPM, RPD). When the RAG pipeline
runs semantic query refinement for multiple commits in parallel, a single
key can hit rate limits. This client distributes requests across multiple
API keys using round-robin selection and automatically retries with the
next available key on HTTP 429 (rate limit) responses.

Benefits:
  - 2 keys  -> 2x effective rate limit
  - N keys  -> N x effective rate limit
  - Automatic failover: if a key is rate-limited, the next key handles
    the request immediately with zero downtime
  - If ALL keys are rate-limited simultaneously, the client waits
    briefly and retries before raising an error

Usage::

    from rag.llm.multi_key_client import MultiKeyGroqClient

    client = MultiKeyGroqClient(
        api_keys=["gsk_key1...", "gsk_key2..."],
        model_name="llama-3.3-70b-versatile",
    )
    response = client.generate("Summarise the semantic changes in this commit...")
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from rag.llm.base import BaseLLM
from rag.llm.groq_client import GroqClient
from rag.utils import get_logger

logger = get_logger(__name__)

# If ALL keys are rate-limited, wait this many seconds before retrying
_RATE_LIMIT_BACKOFF_SECONDS = 5

# Maximum extra retry passes when all keys are exhausted
_MAX_EXHAUSTION_RETRIES = 3


class MultiKeyGroqClient(BaseLLM):
    """
    A round-robin load balancer across multiple Groq API keys.

    Each call to ``generate()`` uses the next available key in rotation.
    On an HTTP 429 (rate limit) response the client immediately advances
    to the next key and retries. If all keys are exhausted, it waits
    ``_RATE_LIMIT_BACKOFF_SECONDS`` before one more full rotation, up to
    ``_MAX_EXHAUSTION_RETRIES`` times before raising.

    This is thread-safe: multiple pipeline threads can call ``generate()``
    concurrently and each will claim a different key slot.

    Args:
        api_keys:   List of Groq API key strings. At least one is required.
        model_name: Groq model to use (e.g. 'llama-3.3-70b-versatile').
        temperature: Sampling temperature.
        max_tokens:  Maximum tokens to generate.
        timeout:     Per-request timeout in seconds.
    """

    def __init__(
        self,
        api_keys: list[str],
        model_name: str = "llama-3.3-70b-versatile",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        if not api_keys:
            raise ValueError("MultiKeyGroqClient requires at least one API key.")

        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Build one GroqClient per key
        self._clients: list[GroqClient] = [
            GroqClient(
                api_key=key,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            for key in api_keys
        ]

        self._num_keys = len(self._clients)
        self._lock = threading.Lock()
        self._index = 0  # current round-robin position

        logger.info(
            "MultiKeyGroqClient initialised with %d API key(s), model='%s'",
            self._num_keys,
            model_name,
        )

    # ------------------------------------------------------------------
    # BaseLLM interface
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate a response using round-robin key selection.

        Automatically retries with the next key on HTTP 429 rate limits.

        Args:
            prompt:        User prompt.
            system_prompt: Optional system-level instruction.

        Returns:
            str: Generated response text.

        Raises:
            RuntimeError: If all keys fail after all retry attempts.
        """
        exhaustion_retries = 0

        while exhaustion_retries <= _MAX_EXHAUSTION_RETRIES:
            # Try each key once per rotation
            for attempt in range(self._num_keys):
                client, key_index = self._next_client()

                try:
                    result = client.generate(prompt, system_prompt)
                    logger.debug(
                        "MultiKeyGroqClient: success on key #%d (attempt %d)",
                        key_index,
                        attempt + 1,
                    )
                    return result

                except RuntimeError as exc:
                    msg = str(exc)

                    # 429 rate limit — rotate to next key immediately
                    if "429" in msg or "rate limit" in msg.lower():
                        logger.warning(
                            "MultiKeyGroqClient: key #%d hit rate limit — "
                            "rotating to next key (attempt %d/%d)",
                            key_index,
                            attempt + 1,
                            self._num_keys,
                        )
                        continue  # try next key

                    # Non-rate-limit error — propagate immediately
                    logger.error(
                        "MultiKeyGroqClient: key #%d returned non-rate-limit "
                        "error: %s",
                        key_index,
                        exc,
                    )
                    raise

            # All keys were rate-limited in this rotation
            exhaustion_retries += 1
            if exhaustion_retries <= _MAX_EXHAUSTION_RETRIES:
                logger.warning(
                    "MultiKeyGroqClient: all %d key(s) are rate-limited. "
                    "Waiting %ds before retry %d/%d...",
                    self._num_keys,
                    _RATE_LIMIT_BACKOFF_SECONDS,
                    exhaustion_retries,
                    _MAX_EXHAUSTION_RETRIES,
                )
                time.sleep(_RATE_LIMIT_BACKOFF_SECONDS)

        raise RuntimeError(
            f"MultiKeyGroqClient: all {self._num_keys} API key(s) are "
            f"rate-limited. Exhausted {_MAX_EXHAUSTION_RETRIES} retry "
            f"rotations. Try again later or add more API keys."
        )

    def health_check(self) -> bool:
        """Return True if at least one key is healthy."""
        for i, client in enumerate(self._clients):
            if client.health_check():
                logger.debug("MultiKeyGroqClient: key #%d is healthy", i)
                return True
        logger.warning("MultiKeyGroqClient: no keys are healthy")
        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _next_client(self) -> tuple[GroqClient, int]:
        """
        Thread-safe round-robin: advance index and return next client.

        Returns:
            Tuple of (GroqClient, key_index).
        """
        with self._lock:
            index = self._index
            self._index = (self._index + 1) % self._num_keys

        return self._clients[index], index

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def num_keys(self) -> int:
        """Number of API keys in rotation."""
        return self._num_keys

    def key_health_summary(self) -> list[dict]:
        """
        Return health status for every key.

        Useful for admin/monitoring endpoints.

        Returns:
            list[dict]: Each entry has ``key_index`` and ``healthy``.
        """
        return [
            {"key_index": i, "healthy": client.health_check()}
            for i, client in enumerate(self._clients)
        ]
