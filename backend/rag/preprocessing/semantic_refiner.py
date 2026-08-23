"""
Semantic refinement for documentation retrieval queries.

This module is intentionally downstream of static analysis. It does not parse
source code and it does not decide what changed. It receives a structured
semantic evidence packet and optionally asks a local Ollama model to translate
that evidence into documentation-oriented retrieval terminology.
"""

from __future__ import annotations

import json
from typing import Any

from rag.config import settings
from rag.llm.factory import LLMFactory
from rag.utils import get_logger

logger = get_logger(__name__)


class SemanticQueryRefiner:
    """
    Optional local-LLM semantic refinement for retrieval query assembly.
    """

    _FIELDS = {
        "high_level_purpose",
        "implementation_responsibilities",
        "processing_workflow",
        "technical_concepts",
        "architectural_concepts",
        "domain_concepts",
        "modified_symbols",
        "dependencies",
        "metadata",
        "keywords",
    }

    def refine(self, evidence: dict[str, Any]) -> dict[str, list[str] | str]:
        """
        Refine structured static-analysis evidence into retrieval terminology.

        Returns an empty dictionary when refinement is disabled, unavailable,
        or invalid. Callers should treat this as an optional enhancement.
        """

        if not settings.enable_semantic_query_refinement:
            return {}

        if settings.llm_provider.lower() != "ollama":
            logger.info(
                "Semantic query refinement skipped: provider is not local Ollama."
            )
            return {}

        try:
            llm = LLMFactory.create()
        except Exception as exc:
            logger.info("Semantic query refinement skipped: %s", exc)
            return {}

        try:
            if not llm.health_check():
                logger.info("Semantic query refinement skipped: Ollama unavailable.")
                return {}
        except Exception as exc:
            logger.info("Semantic query refinement health check failed: %s", exc)
            return {}

        try:
            response = llm.generate(
                prompt=self._build_prompt(evidence),
                system_prompt=self._system_prompt(),
            )
            return self._parse_response(response)
        except Exception as exc:
            logger.warning("Semantic query refinement failed: %s", exc)
            return {}

    def _system_prompt(self) -> str:
        return (
            "You are a software architect refining retrieval queries for documentation RAG. "
            "Use only the supplied structured static-analysis evidence. "
            "Infer responsibilities, execution workflow, architectural role, technical concepts, domain concepts, and retrieval keywords from clusters, behaviors, control flow, calls, imports, dependencies, and structural relationships. "
            "Traceability names are evidence only: do not split, paraphrase, or restate identifiers unless an exact public API name is essential. "
            "Do not summarize a commit, repeat paths, describe syntax, or invent frameworks, products, files, or features. "
            "Return only a raw JSON object."
        )

    def _build_prompt(self, evidence: dict[str, Any]) -> str:
        payload = json.dumps(evidence, indent=2, sort_keys=True)
        return f"""
Structured static-analysis evidence:
{payload}

Create concise documentation-retrieval semantics.

Return exactly this JSON shape:
{{
  "high_level_purpose": "one concise sentence describing the component purpose",
  "implementation_responsibilities": ["responsibility phrase", "..."],
  "processing_workflow": ["execution step", "..."],
  "technical_concepts": ["technical concept", "..."],
  "architectural_concepts": ["architectural concept", "..."],
  "domain_concepts": ["domain concept", "..."],
    "modified_symbols": ["exact public symbol names or concise symbol references", "..."],
    "dependencies": ["dependency relationship or related file role", "..."],
    "metadata": ["change metadata that improves retrieval", "..."],
  "keywords": ["ranked retrieval keyword", "..."]
}}

Rules:
- Each phrase must improve BM25 or dense retrieval.
- Prefer documentation terminology over source identifiers.
- Treat `semantic.semantic_context` as the primary evidence. Use `traceability` only to resolve relationships, never as a terminology source.
- Use `clusters` to keep unrelated changes separate; do not merge unrelated responsibilities into one phrase.
- Describe workflow as behavioral execution steps, not call order or identifier names.
- Omit a field when the evidence cannot support a useful abstraction.
- Keep phrases short: 2 to 6 words when possible.
- Use identifiers only when they are public API names or essential exact-match terms.
- Exclude primitive types, punctuation, generic verbs, and implementation trivia.
- If evidence is insufficient for a field, return an empty list or an empty string.
""".strip()

    def _parse_response(self, response: str) -> dict[str, list[str] | str]:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return {}

        refined: dict[str, list[str] | str] = {}
        for field in self._FIELDS:
            value = data.get(field)
            if isinstance(value, str):
                cleaned_value = value.strip()
                if cleaned_value:
                    refined[field] = cleaned_value
            elif isinstance(value, list):
                cleaned_items = [
                    str(item).strip()
                    for item in value
                    if str(item).strip()
                ]
                if cleaned_items:
                    refined[field] = cleaned_items[:12]

        return refined
