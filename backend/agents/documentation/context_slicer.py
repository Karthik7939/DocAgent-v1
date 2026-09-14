"""
agents/documentation/context_slicer.py
----------------------------------------
Slices the RAG ContextPackage into file-scoped and global context strings
for injection into LLM documentation prompts.

Keeps each extracted context within a configurable character budget so that
LLM calls stay well within provider token limits — critical for large repos
where the full context package may contain hundreds of chunks.
"""

from __future__ import annotations

import logging
from typing import Optional, cast

logger = logging.getLogger(__name__)

# Character budgets per context type. Sized to comfortably hold several full
# retrieved chunks (RAG_MAX_CHUNK_TOKENS=1024, ~4,096 chars/chunk, up to
# RAG_TOP_K=10 chunks retrieved) rather than truncating to a fraction of one
# chunk — too-small budgets starve the Documentation Agent of evidence and
# it fills the gap by fabricating claims from training data instead of the
# actual repository. Gemini's context window has ample room for this.
MAX_FILE_CONTEXT_CHARS: int = 12_000    # ~3 000 tokens — file-specific RAG chunks
MAX_GLOBAL_CONTEXT_CHARS: int = 20_000  # ~5 000 tokens — repo-level RAG chunks

# MMR relevance/diversity balance: 1.0 = pure relevance (original rank
# order, no diversity effect), 0.0 = pure diversity (ignores relevance
# entirely). 0.7 keeps relevance dominant while still demoting near-
# duplicate chunks that would otherwise eat the character budget with
# redundant content instead of covering more of the repository.
MMR_LAMBDA: float = 0.7


class ContextSlicer:
    """
    Slices a RAG ContextPackage into targeted context strings for LLM prompts.

    Each documentation call (per-file, per-module, repo-level) gets only the
    chunks that are relevant to *that specific document*, keeping prompts
    focused and token-efficient.

    Usage::

        slicer = ContextSlicer()
        file_ctx  = slicer.get_chunks_for_file("app/api/webhook.py", ctx_pkg)
        global_ctx = slicer.get_global_context(ctx_pkg)
    """

    def __init__(
        self,
        max_file_chars: int = MAX_FILE_CONTEXT_CHARS,
        max_global_chars: int = MAX_GLOBAL_CONTEXT_CHARS,
    ) -> None:
        self.max_file_chars = max_file_chars
        self.max_global_chars = max_global_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_chunks_for_file(
        self,
        file_path: str,
        context_package,
        max_chars: Optional[int] = None,
    ) -> str:
        """
        Return formatted RAG chunks relevant to a specific file.

        Matching order:
          1. Chunks whose file_path exactly matches the target.
          2. Chunks whose retrieval_reason mentions the target filename.
          3. Empty string if no match found.

        Args:
            file_path:       Relative file path to scope the search.
            context_package: ContextPackage from the RAG pipeline.
            max_chars:       Override the default character budget.

        Returns:
            str: Formatted context string within the budget, or "".
        """
        if context_package is None:
            return ""

        budget = max_chars if max_chars is not None else self.max_file_chars
        results = self._get_results(context_package)
        if not results:
            return ""

        norm_target = file_path.replace("\\", "/").lower()

        # Priority 1: exact file match
        matching = [r for r in results if self._matches_file(r, norm_target)]

        # Priority 2: retrieval_reason mentions the file
        if not matching:
            matching = [r for r in results if self._mentions_file(r, norm_target)]

        return self._format(self._mmr_reorder(matching), budget)

    def get_chunks_for_module(
        self,
        module_path: str,
        context_package,
        max_chars: Optional[int] = None,
    ) -> str:
        """
        Return formatted RAG chunks relevant to an entire module directory.

        Args:
            module_path:     Relative directory path, e.g. "agents/documentation".
            context_package: ContextPackage from the RAG pipeline.
            max_chars:       Override the default character budget.

        Returns:
            str: Formatted context string within the budget, or "".
        """
        if context_package is None:
            return ""

        budget = max_chars if max_chars is not None else self.max_file_chars
        results = self._get_results(context_package)
        if not results:
            return ""

        norm_module = module_path.replace("\\", "/").lower().rstrip("/") + "/"

        matching = [
            r for r in results
            if self._chunk_file_path(r).startswith(norm_module)
        ]
        return self._format(self._mmr_reorder(matching), budget)

    def get_global_context(
        self,
        context_package,
        max_chars: Optional[int] = None,
    ) -> str:
        """
        Return the top-ranked RAG chunks across all files for repo-level docs.

        Args:
            context_package: ContextPackage from the RAG pipeline.
            max_chars:       Override the default character budget.

        Returns:
            str: Formatted context string within the budget, or "".
        """
        if context_package is None:
            return ""

        budget = max_chars if max_chars is not None else self.max_global_chars
        results = self._get_results(context_package)
        if not results:
            return ""

        # Sort by rank (rank 1 = best), take top 30 before applying budget
        top = sorted(results, key=lambda r: getattr(r, "rank", 999))[:30]
        return self._format(self._mmr_reorder(top), budget)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_results(context_package) -> list:
        """Safely extract the list of retrieval results from a ContextPackage."""
        try:
            return list(context_package.retrieval_results.results)
        except Exception:
            return []

    @staticmethod
    def _chunk_file_path(item) -> str:
        """Return the normalised file path of a retrieval item's chunk."""
        try:
            return item.chunk.metadata.file_path.replace("\\", "/").lower()
        except Exception:
            return ""

    @staticmethod
    def _matches_file(item, norm_target: str) -> bool:
        """True when the chunk's file_path matches (exact or suffix) the target."""
        chunk_path = ContextSlicer._chunk_file_path(item)
        return chunk_path == norm_target or chunk_path.endswith(f"/{norm_target}")

    @staticmethod
    def _mentions_file(item, norm_target: str) -> bool:
        """True when retrieval_reason text mentions the target filename."""
        try:
            reason = (item.retrieval_reason or "").lower()
            filename = norm_target.split("/")[-1]
            return norm_target in reason or filename in reason
        except Exception:
            return False

    @staticmethod
    def _cosine_similarity(a: list, b: list) -> float:
        """Cosine similarity between two equal-length embedding vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _mmr_reorder(items: list, lambda_mult: float = MMR_LAMBDA) -> list:
        """
        Reorder items with Maximal Marginal Relevance so near-duplicate
        chunks don't crowd out coverage of different parts of the file/repo.

        Greedily picks, at each step, the remaining item that best balances
        staying close to the incoming relevance order against being
        dissimilar to what's already been selected — using each chunk's
        embedding (already computed during retrieval, no extra model call)
        for the diversity comparison. The top-ranked item is always kept
        first.

        Falls back to the original order unchanged when any chunk is
        missing an embedding, or there's nothing to reorder.

        Args:
            items:       Retrieval results already in relevance/rank order.
            lambda_mult: Relevance/diversity balance — see MMR_LAMBDA.

        Returns:
            list: Reordered items (same items, no filtering).
        """
        n = len(items)
        if n <= 1:
            return items

        raw_embeddings = [getattr(item.chunk, "embedding", None) for item in items]
        if any(not e for e in raw_embeddings):
            return items
        embeddings = cast("list[list[float]]", raw_embeddings)

        # Relevance proxy from incoming rank order: 1.0 (best) .. ~0 (worst).
        relevance = [1.0 - (i / n) for i in range(n)]

        selected: list[int] = [0]
        remaining = list(range(1, n))

        while remaining:
            best_idx, best_score = remaining[0], float("-inf")
            for idx in remaining:
                max_sim = max(
                    ContextSlicer._cosine_similarity(embeddings[idx], embeddings[s])
                    for s in selected
                )
                score = lambda_mult * relevance[idx] - (1 - lambda_mult) * max_sim
                if score > best_score:
                    best_idx, best_score = idx, score
            selected.append(best_idx)
            remaining.remove(best_idx)

        return [items[i] for i in selected]

    @staticmethod
    def _format(items: list, budget: int) -> str:
        """
        Render retrieval items as a text block, stopping when budget is reached.

        Format per chunk::

            [File: path | Lines: 10-50 | Source: faiss | Rank: 1]
            [Reason: ...]
            <chunk content>
            ---
        """
        if not items:
            return ""

        parts: list[str] = []
        used = 0

        for item in items:
            try:
                meta = item.chunk.metadata
                header = (
                    f"[File: {meta.file_path}"
                    f" | Lines: {meta.start_line}-{meta.end_line}"
                    f" | Source: {item.retrieval_source.value}"
                    f" | Rank: {item.rank}]"
                )
                if item.retrieval_reason:
                    header += f"\n[Reason: {item.retrieval_reason}]"
                block = f"{header}\n{item.chunk.content}\n---"
                if used + len(block) > budget:
                    break
                parts.append(block)
                used += len(block)
            except Exception:
                continue

        return "\n".join(parts) if parts else ""
