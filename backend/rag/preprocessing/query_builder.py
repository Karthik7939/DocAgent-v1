"""
Query construction for RAG retrieval.

Constructs a structured SemanticQuery from language-neutral static analysis:
changed files, symbols, imports, implementation terms, and dependency context.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from rag.config.constants import SUPPORTED_LANGUAGES
from rag.config import settings
from rag.schemas.change import SymbolChange
from rag.schemas.query import SemanticQuery
from rag.preprocessing.semantic_context import SemanticContextBuilder
from rag.preprocessing.semantic_refiner import SemanticQueryRefiner


class QueryBuilder:
    """
    Constructs a SemanticQuery from code change metadata.

    The final query is assembled from structured code metadata rather than a
    commit-style summary. Every stage consumes language-neutral extraction
    output so adding a new language only requires improving the extraction
    layer, not changing query assembly.
    """

    _SYNTAX_STOP_WORDS = {
        "a",
        "an",
        "and",
        "as",
        "by",
        "class",
        "def",
        "else",
        "for",
        "from",
        "function",
        "if",
        "import",
        "in",
        "is",
        "method",
        "module",
        "not",
        "of",
        "or",
        "private",
        "protected",
        "public",
        "return",
        "self",
        "static",
        "the",
        "this",
        "while",
    }

    _PATH_STOP_WORDS = {
        "app",
        "backend",
        "build",
        "dist",
        "docs",
        "doc",
        "lib",
        "main",
        "src",
        "spec",
        "test",
        "tests",
    }

    _WEAK_KEYWORDS = {
        "api",
        "backend",
        "boolean",
        "change",
        "code",
        "count",
        "date",
        "false",
        "logic",
        "model",
        "module",
        "modified",
        "new",
        "number",
        "string",
        "true",
        "update",
        "value",
        "values",
    }

    def __init__(
        self,
        repository: str,
        commit_sha: str,
        dependency_graph_query: Optional[Any] = None,
    ) -> None:
        self.repository = repository
        self.commit_sha = commit_sha
        self.graph_query = dependency_graph_query

        self._changed_files: list[str] = []
        self._changed_symbols: list[str] = []
        self._change_type: str = "logic"
        self._expanded_symbols: list[str] = []
        self._dependency_files: list[str] = []
        self._keywords: list[str] = []
        self._dependency_symbols: dict[str, list[str]] = {}
        self._changed_file_summaries: list[str] = []
        self._dependency_summaries: list[str] = []
        self._module_responsibility_summaries: list[str] = []
        self._imports_added: list[str] = []
        self._imports_removed: list[str] = []
        self._diff_texts: list[str] = []
        self._implementation_terms: list[str] = []
        self._technical_concepts: list[str] = []
        self._workflow_steps: list[str] = []
        self._domain_concepts: list[str] = []
        self._semantic_refinement: dict[str, list[str] | str] = {}
        self._calls: list[str] = []
        self._structural_operations: list[str] = []
        self._data_flows: list[str] = []
        self._file_contexts: list[dict[str, Any]] = []
        self._semantic_context: dict[str, Any] = {}
        self._symbol_scope_scores: dict[str, int] = {}

    def build(
        self,
        changed_files: list[str],
        changed_symbols: list[SymbolChange],
        change_type: str,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        metadata_filters: Optional[dict[str, str]] = None,
        imports_added: Optional[list[str]] = None,
        imports_removed: Optional[list[str]] = None,
        diff_texts: Optional[list[str]] = None,
        implementation_terms: Optional[list[str]] = None,
        calls: Optional[list[str]] = None,
        structural_operations: Optional[list[str]] = None,
        data_flows: Optional[list[str]] = None,
        renamed_symbols: Optional[list[dict[str, str]]] = None,
        file_contexts: Optional[list[dict[str, Any]]] = None,
    ) -> SemanticQuery:
        """
        Builds and returns a SemanticQuery.
        """
        self._changed_files = changed_files

        self._changed_symbols = self._normalize_symbol_names(changed_symbols)
        self._symbol_scope_scores = {
            self._clean_symbol_name(str(symbol.name)).lower(): max(
                int(getattr(symbol, "end_line", 0))
                - int(getattr(symbol, "start_line", 0)),
                0,
            )
            for symbol in changed_symbols
            if hasattr(symbol, "name")
        }
        self._change_type = self._normalize_change_type(change_type)
        self._imports_added = self._ordered_unique_phrases(imports_added or [])
        self._imports_removed = self._ordered_unique_phrases(imports_removed or [])
        self._diff_texts = [text for text in (diff_texts or []) if text]
        self._implementation_terms = self._ordered_unique_phrases(
            implementation_terms or []
        )
        self._calls = self._ordered_unique_display(calls or [])
        self._structural_operations = self._ordered_unique_display(
            structural_operations or []
        )
        self._data_flows = self._ordered_unique_display(data_flows or [])
        self._file_contexts = file_contexts or []
        rename_mappings = renamed_symbols or []
        resolved_top_k, resolved_threshold = self._resolve_retrieval_parameters(
            len(self._changed_symbols), top_k, similarity_threshold
        )

        # 1. Expand dependencies and collect graph context.
        self.expand_dependencies()
        self._dependency_symbols = self._collect_dependency_symbols()

        # 2. Extract retrieval concepts from changed-code metadata.
        self._technical_concepts = self._extract_technical_concepts()
        self._workflow_steps = self._infer_workflow_steps()
        self._domain_concepts = self._infer_domain_concepts()
        self._semantic_context = SemanticContextBuilder(
            changed_files=self._changed_files,
            changed_symbols=changed_symbols,
            imports_added=self._imports_added,
            imports_removed=self._imports_removed,
            dependencies=self._dependency_files,
            dependency_symbols=self._dependency_symbols,
            calls=self._calls,
            operations=self._structural_operations or self._implementation_terms,
            data_flows=self._data_flows,
            change_type=self._change_type,
            file_contexts=self._file_contexts,
            graph_query=self.graph_query,
        ).build()
        self._semantic_refinement = self._refine_semantics()

        # 3. Build implementation-oriented descriptions.
        self._module_responsibility_summaries = self._infer_module_responsibilities()
        self._changed_file_summaries = self._summarize_changed(
            changed_files=self._changed_files,
            modified_symbols=changed_symbols,
            ast_diff=None,
        )
        self._dependency_summaries = self._summarize_dependencies(
            self._dependency_files,
        )

        # 4. Generate keywords
        self._keywords = self.keywords()

        # 5. Construct query text
        query_text = self._build_query_text()
        if not query_text:
            query_text = f"Code changes in commit {self.commit_sha}"

        # Identify extensions & languages
        extensions = sorted(
            list({Path(f).suffix for f in changed_files if Path(f).suffix})
        )
        languages = sorted(
            list(
                {
                    SUPPORTED_LANGUAGES[ext]
                    for ext in extensions
                    if ext in SUPPORTED_LANGUAGES
                }
            )
        )

        return SemanticQuery(
            repository=self.repository,
            commit_sha=self.commit_sha,
            query_text=query_text,
            changed_files=self._changed_files,
            modified_symbols=self._changed_symbols,
            renamed_symbols=rename_mappings,
            keywords=self._keywords,
            semantic_context=self._semantic_context,
            semantic_sections=self._semantic_sections(),
            cluster_summaries=self._semantic_context.get("semantic", {}).get("clusters", []),
            file_extensions=extensions,
            languages=languages,
            dependency_files=self._dependency_files,
            top_k=resolved_top_k,
            similarity_threshold=resolved_threshold,
            metadata_filters=metadata_filters or {},
        )

    def _normalize_change_type(self, change_type: str) -> str:
        change_type = (change_type or "logic").strip().lower().replace(" ", "_")
        return change_type or "logic"

    def _normalize_symbol_names(self, changed_symbols: list[SymbolChange]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for sym in changed_symbols:
            if not hasattr(sym, "name"):
                continue

            name = self._clean_symbol_name(str(sym.name))
            if not name:
                continue

            key = name.lower()
            if key in seen:
                continue

            seen.add(key)
            normalized.append(name)

        return normalized

    @staticmethod
    def _clean_symbol_name(name: str) -> str:
        return re.sub(r"[\s:;(),]+$", "", name.strip())

    @staticmethod
    def _split_identifier(identifier: str) -> list[str]:
        parts: list[str] = []

        for chunk in re.split(r"[._/\\-]+", identifier):
            if not chunk:
                continue

            chunk = re.sub(r"[^0-9A-Za-z]+", " ", chunk)
            chunk = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", chunk)
            chunk = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", chunk)

            for token in chunk.split():
                token = token.strip().lower()
                if token:
                    parts.append(token)

        return parts

    @classmethod
    def symbol_keyword_variants(cls, symbol: str) -> list[str]:
        """Return the canonical searchable forms for every symbol.

        This intentionally preserves every identifier token. Relevance-specific
        filtering belongs to a separate caller policy, never this tokenizer.
        """
        tokens = cls._split_identifier(symbol)
        if not tokens:
            return []
        phrase = " ".join(tokens)
        squashed = "".join(tokens)
        variants = [phrase, squashed] if phrase != squashed else [phrase]
        window = settings.query_keyword_ngram_size
        if window and len(tokens) >= window:
            variants.extend(
                " ".join(tokens[index : index + window])
                for index in range(len(tokens) - window + 1)
            )
        return cls._ordered_unique_static(variants)

    @staticmethod
    def _ordered_unique_static(values: list[str]) -> list[str]:
        seen: set[str] = set()
        return [
            value for value in values
            if value and not (value.lower() in seen or seen.add(value.lower()))
        ]

    @staticmethod
    def _resolve_retrieval_parameters(
        symbol_count: int,
        requested_top_k: Optional[int],
        requested_threshold: Optional[float],
    ) -> tuple[int, float]:
        """Derive retrieval breadth from change scope unless explicitly set."""
        additional_symbols = max(
            symbol_count - settings.query_scope_baseline_symbol_count,
            0,
        )
        top_k = requested_top_k
        if top_k is None:
            top_k = min(
                settings.query_top_k_max,
                settings.top_k + additional_symbols * settings.query_top_k_symbol_increment,
            )
        threshold = requested_threshold
        if threshold is None:
            threshold = max(
                settings.query_similarity_threshold_min,
                settings.similarity_threshold
                - additional_symbols * settings.query_similarity_threshold_symbol_step,
            )
        return top_k, QueryBuilder._serialize_similarity_threshold(threshold)

    @staticmethod
    def _serialize_similarity_threshold(value: float) -> float:
        """Stabilize derived threshold serialization using configured precision."""
        return round(value, settings.query_similarity_threshold_precision)

    def _extract_meaningful_terms(self, text: str) -> list[str]:
        tokens = self._split_identifier(text)
        return [
            token
            for token in tokens
            if len(token) > 1
            and token not in self._SYNTAX_STOP_WORDS
            and token not in self._PATH_STOP_WORDS
            and token not in self._WEAK_KEYWORDS
        ]

    def _extract_phrase_candidates(self, text: str) -> list[str]:
        tokens = self._extract_meaningful_terms(text)
        if not tokens:
            return []

        candidates: list[str] = []

        for size in (1, 2, 3):
            if len(tokens) < size:
                continue

            for index in range(len(tokens) - size + 1):
                phrase = " ".join(tokens[index : index + size]).strip()
                if phrase and phrase not in candidates:
                    candidates.append(phrase)

        return candidates

    def _collect_concept_counts(self) -> Counter[str]:
        """Count identifier-derived concepts without treating paths as terms."""
        counts: Counter[str] = Counter()

        for symbol in self._changed_symbols:
            for phrase in self._extract_phrase_candidates(symbol):
                counts[phrase] += 3 if " " in phrase else 1

        for keyword in self._change_type.replace("_", " ").split():
            if len(keyword) > 1:
                counts[keyword.lower()] += 1

        return counts

    def _infer_module_responsibilities(self) -> list[str]:
        """
        Infer one responsibility sentence per changed file from the changed-side
        metadata only.

        This step intentionally does not inspect dependency-neighbor symbols so
        that unrelated helper functions never leak into the core change summary.
        """
        summaries: list[str] = []

        for file_path in self._changed_files:
            stem = Path(file_path).stem.replace("_", " ").strip()
            action_phrases = self._select_phrases_by_overlap(
                [self._symbol_action_phrase(symbol) for symbol in self._changed_symbols],
                limit=3,
            )

            concepts = self._format_list_phrase((self._domain_concepts + self._technical_concepts)[:4])
            workflow = self._format_workflow()
            symbol_text = self._format_list_phrase(action_phrases)

            parts = []
            if stem:
                parts.append(stem)
            if concepts:
                parts.append(f"implements {concepts}")
            if symbol_text:
                parts.append(f"through {symbol_text}")
            if workflow:
                parts.append(f"with workflow {workflow}")

            if parts:
                summaries.append(" ".join(parts) + ".")

        return summaries

    def _summarize_changed(
        self,
        changed_files: list[str],
        modified_symbols: list[SymbolChange],
        ast_diff: Any = None,
    ) -> list[str]:
        """
        Build the core change summary using only changed-file context.

        The changed summary carries the majority of the query weight. Dependency
        context is intentionally excluded here so the semantic query reflects
        what was actually modified before any related-file relationships are
        appended.
        """
        summaries: list[str] = []

        if self._module_responsibility_summaries:
            summaries.extend(self._module_responsibility_summaries[:3])

        purpose = self._build_purpose_sentence()
        if purpose:
            summaries.append(purpose)

        workflow = self._format_workflow()
        if workflow:
            summaries.append(f"Processing workflow: {workflow}.")

        symbol_phrases = self._select_phrases_by_overlap(
            [self._symbol_action_phrase(symbol.name) if hasattr(symbol, "name") else "" for symbol in modified_symbols],
            limit=4,
        )
        if symbol_phrases:
            summaries.append(
                f"Modified symbols: {self._format_list_phrase(symbol_phrases)}."
            )

        if changed_files:
            file_phrases = [Path(file_path).stem.replace("_", " ") for file_path in changed_files[:3]]
            summaries.append(
                f"Modified files: {self._format_list_phrase(file_phrases)}."
            )

        return self._ordered_unique_phrases(summaries)

    def _summarize_dependencies(self, dependency_files: list[str]) -> list[str]:
        """
        Summarize dependency-neighbor files with one short relationship sentence
        each.

        Dependency text is capped and purpose-driven: it may explain how a file
        relates to the change, but it must never become a symbol dump or take
        over the main change summary.
        """
        summaries: list[str] = []

        for file_path in dependency_files:
            summaries.append(self._dependency_role_phrase(file_path))

        return self._ordered_unique_phrases(summaries)

    def _collect_dependency_symbols(self) -> dict[str, list[str]]:
        symbols_by_file: dict[str, list[str]] = {}
        graph = getattr(self.graph_query, "_graph", None)

        if not graph or not hasattr(graph, "get_node"):
            return symbols_by_file

        for file_path in self._dependency_files:
            node = graph.get_node(file_path)
            if node is None:
                continue

            symbols = getattr(node, "symbols", None) or []
            cleaned = [self._clean_symbol_name(str(symbol)) for symbol in symbols]
            symbols_by_file[file_path] = [symbol for symbol in cleaned if symbol]

        return symbols_by_file

    def _symbol_action_phrase(self, symbol: str) -> str:
        # Identifier phrases must preserve every token. In particular, filtering
        # syntax words here used to turn "watch_session_for_changes" into the
        # non-contiguous and misleading "watch session changes".
        variants = self.symbol_keyword_variants(symbol)
        return variants[0] if variants else ""

    def _collect_behavior_phrases(self) -> list[str]:
        phrases: list[str] = []

        for symbol in self._changed_symbols:
            phrase = self._symbol_action_phrase(symbol)
            if phrase:
                phrases.append(phrase)

        for symbols in self._dependency_symbols.values():
            for symbol in symbols:
                phrase = self._symbol_action_phrase(symbol)
                if phrase:
                    phrases.append(phrase)

        ordered = self._ordered_unique_phrases(phrases)
        filtered: list[str] = []

        for phrase in ordered:
            phrase_tokens = set(self._extract_meaningful_terms(phrase))
            if not phrase_tokens:
                continue

            if any(len(phrase_tokens & set(self._extract_meaningful_terms(existing))) >= len(phrase_tokens) for existing in filtered):
                continue

            filtered.append(phrase)

        return filtered

    def _select_behavior_phrases(self, limit: int = 4) -> list[str]:
        scored = []

        for phrase in self._collect_behavior_phrases():
            tokens = self._extract_meaningful_terms(phrase)
            if not tokens:
                continue

            score = len(tokens)
            if any(token in self._SYNTAX_STOP_WORDS for token in tokens):
                score -= 1
            scored.append((score, phrase))

        scored.sort(key=lambda item: (-item[0], item[1]))

        selected: list[str] = []
        for _, phrase in scored:
            phrase_tokens = set(self._extract_meaningful_terms(phrase))
            if not phrase_tokens:
                continue

            if any(
                len(phrase_tokens & set(self._extract_meaningful_terms(existing))) > 1
                for existing in selected
            ):
                continue

            selected.append(phrase)
            if len(selected) >= limit:
                break

        return selected

    def _dependency_role_phrase(self, file_path: str) -> str:
        stem = Path(file_path).stem.replace("_", " ").strip()
        symbols = self._dependency_symbols.get(file_path, [])

        behavior_phrases = [self._symbol_action_phrase(symbol) for symbol in symbols]
        behavior_phrases = [phrase for phrase in behavior_phrases if phrase]

        if behavior_phrases:
            selected = self._select_phrases_by_overlap(behavior_phrases, limit=2)
            if selected:
                if stem:
                    return f"{stem} code that {self._format_list_phrase(selected)}"
                return self._format_list_phrase(selected)

        if stem:
            return f"{stem} dependency"

        return "related code"

    def _build_purpose_sentence(self) -> str:
        refined = self._refined_text("high_level_purpose")
        if refined:
            return refined if refined.endswith(".") else f"{refined}."

        symbols = self._format_list_phrase(self._purpose_symbol_phrases())
        files = self._format_list_phrase(self._changed_files[:8])
        if symbols and files:
            return f"This change modifies {symbols} in {files}."
        if symbols:
            return f"This change modifies {symbols}."
        if files:
            return f"This change modifies code in {files}."
        return ""

    def _semantic_sections(self) -> dict[str, list[str] | str]:
        """Expose the structured sections that are rendered into query_text."""
        sections: dict[str, list[str] | str] = {}
        purpose = self._build_purpose_sentence()
        if purpose:
            sections["high_level_purpose"] = purpose
        workflow = self._format_workflow()
        if workflow:
            sections["processing_workflow"] = workflow
        if self._changed_symbols:
            sections["modified_symbols"] = self._purpose_symbol_phrases()
        if self._changed_files:
            sections["changed_files"] = list(self._changed_files)
        if self._dependency_summaries:
            sections["dependencies"] = list(self._dependency_summaries)
        return sections

    def _purpose_symbol_phrases(self) -> list[str]:
        """Apply the explicit, configurable purpose-summary inclusion policy."""
        ranked_symbols = sorted(
            self._changed_symbols,
            key=lambda symbol: (-self._symbol_scope_scores.get(symbol.lower(), 0), symbol.lower()),
        )
        variants = [self.symbol_keyword_variants(symbol) for symbol in ranked_symbols]
        phrases = [variant[0] for variant in variants if variant]
        return self._ordered_unique_phrases(
            phrases[: settings.query_purpose_symbol_ceiling]
        )

    def _extract_technical_concepts(self) -> list[str]:
        # These labels come from the parser's structural operation IR, not from
        # identifier splitting. Richer documentation terminology is inferred by
        # SemanticQueryRefiner from the complete evidence packet.
        return self._ordered_unique_display(self._structural_operations)

    def _infer_workflow_steps(self) -> list[str]:
        return self._ordered_unique_phrases(self._structural_operations)

    def _infer_domain_concepts(self) -> list[str]:
        # Domain inference is necessarily contextual.  Avoid treating path and
        # identifier fragments as domain terminology when the LLM is unavailable.
        return []

    def _import_concept_phrases(self, import_name: str) -> list[str]:
        normalized = import_name.strip().strip("\"'`")
        package = normalized.split("?", 1)[0].split("#", 1)[0]
        package = package.replace("@", " ").replace("/", " ").replace(".", " ")
        return self._semantic_phrases_from_identifier(package)

    def _semantic_phrases_from_identifier(self, value: str) -> list[str]:
        tokens = self._extract_meaningful_terms(value)
        if not tokens:
            return []

        phrases: list[str] = []
        if len(tokens) == 1:
            phrases.append(tokens[0])
        else:
            phrases.append(" ".join(tokens[:4]))
            for size in (2, 3):
                for index in range(len(tokens) - size + 1):
                    phrases.append(" ".join(tokens[index : index + size]))

        return self._ordered_unique_phrases(phrases)

    def _added_code_lines(self) -> list[str]:
        lines: list[str] = []
        for diff_text in self._diff_texts:
            for line in diff_text.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    stripped = line[1:].strip()
                    if stripped and not stripped.startswith(("//", "#", "/*", "*")):
                        lines.append(stripped)
        return lines[:80]

    def _format_workflow(self) -> str:
        refined = self._refined_list("processing_workflow")
        if refined:
            return " -> ".join(refined[:8])

        if not self._workflow_steps:
            return ""
        return " -> ".join(self._workflow_steps[:8])

    def _refine_semantics(self) -> dict[str, list[str] | str]:
        evidence = self._semantic_evidence()
        return SemanticQueryRefiner().refine(evidence)

    def _semantic_evidence(self) -> dict[str, Any]:
        return {
            "semantic_context": self._semantic_context,
            "deterministic_technical_terms": self._technical_concepts[:30],
            "deterministic_workflow_signals": self._workflow_steps[:20],
        }

    def _semantic_terms_from_added_code(self) -> list[str]:
        terms: list[str] = []
        for line in self._added_code_lines():
            terms.extend(self._semantic_phrases_from_identifier(line))
        return self._ordered_unique_phrases(terms)

    def _refined_list(self, field: str) -> list[str]:
        value = self._semantic_refinement.get(field)
        if not isinstance(value, list):
            return []
        return self._ordered_unique_display([str(item) for item in value])

    def _refined_text(self, field: str) -> str:
        value = self._semantic_refinement.get(field)
        return value.strip() if isinstance(value, str) else ""

    def _select_phrases_by_overlap(self, phrases: list[str], limit: int = 3) -> list[str]:
        selected: list[str] = []

        for phrase in phrases:
            tokens = set(self._extract_meaningful_terms(phrase))
            if not tokens:
                continue

            if any(
                len(tokens & set(self._extract_meaningful_terms(existing))) > 1
                for existing in selected
            ):
                continue

            selected.append(phrase)
            if len(selected) >= limit:
                break

        return selected

    def _ordered_unique_phrases(self, phrases: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []

        for phrase in phrases:
            cleaned = phrase.strip().lower()
            if not cleaned or cleaned in seen:
                continue

            seen.add(cleaned)
            ordered.append(cleaned)

        return ordered

    def _ordered_unique_display(self, phrases: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []

        for phrase in phrases:
            cleaned = phrase.strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue

            seen.add(key)
            ordered.append(cleaned)

        return ordered

    def _format_list_phrase(self, phrases: list[str]) -> str:
        phrases = self._ordered_unique_phrases(phrases)
        if not phrases:
            return ""
        if len(phrases) == 1:
            return phrases[0]
        if len(phrases) == 2:
            return f"{phrases[0]} and {phrases[1]}"
        return f"{', '.join(phrases[:-1])}, and {phrases[-1]}"

    def _format_display_list(self, phrases: list[str]) -> str:
        phrases = self._ordered_unique_display(phrases)
        if not phrases:
            return ""
        if len(phrases) == 1:
            return phrases[0]
        if len(phrases) == 2:
            return f"{phrases[0]} and {phrases[1]}"
        return f"{', '.join(phrases[:-1])}, and {phrases[-1]}"

    def _build_query_text(self) -> str:
        sections: list[str] = []

        purpose = self._build_purpose_sentence()
        if purpose:
            sections.append(f"High-Level Purpose: {purpose}")

        workflow = self._format_workflow()
        if workflow:
            sections.append(f"Processing Workflow: {workflow}.")

        responsibilities = self._refined_list("implementation_responsibilities")
        if responsibilities:
            sections.append(
                "Implementation Responsibilities: "
                f"{self._format_display_list(responsibilities[:8])}."
            )

        technical = self._refined_list("technical_concepts") or self._technical_concepts
        if technical:
            sections.append(f"Technical Concepts: {self._format_display_list(technical[:12])}.")

        architectural = self._refined_list("architectural_concepts")
        if architectural:
            sections.append(
                f"Architectural Concepts: {self._format_display_list(architectural[:10])}."
            )

        domain = self._refined_list("domain_concepts") or self._domain_concepts
        if domain:
            sections.append(f"Domain Concepts: {self._format_display_list(domain[:10])}.")

        if self._changed_symbols:
            symbols = self._purpose_symbol_phrases()
            sections.append(f"Modified Symbols: {self._format_list_phrase(symbols)}.")

        if self._changed_files:
            files = self._format_list_phrase(self._changed_files[:8])
            sections.append(f"Code Metadata: files {files}.")

        if self._dependency_summaries:
            sections.append(
                f"Dependencies: {self._format_list_phrase(self._dependency_summaries[:4])}."
            )

        if self._keywords:
            sections.append(f"Keywords: {', '.join(self._keywords[:20])}.")

        return " ".join(self._ordered_unique_display(sections)).strip()

    def expand_symbols(self) -> None:
        """
        Breaks down changed symbols into sub-identifiers (camelCase and snake_case).
        """
        expanded = set()
        for sym in self._changed_symbols:
            expanded.add(sym)
            parts = sym.split(".")
            for part in parts:
                expanded.add(part)
                # camelCase split
                camel_parts = re.sub(
                    "([a-z0-9])([A-Z])", r"\1 \2", part
                ).split()
                for cp in camel_parts:
                    expanded.add(cp.lower())
                # snake_case split
                snake_parts = part.split("_")
                for sp in snake_parts:
                    expanded.add(sp.lower())

        self._expanded_symbols = sorted(
            list({x for x in expanded if len(x) > 1})
        )

    def expand_dependencies(self) -> None:
        """
        Pre-populate dependency files from the graph before retrieval.

        This is intentionally query-build-time work: the resulting file list
        is part of ``SemanticQuery`` and is consumed later by dependency-aware
        retrieval. ``affected_files`` includes both import directions, so a
        changed imported file also includes its importers.
        """
        if not self.graph_query:
            return

        # Query dependency graph query object
        if hasattr(self.graph_query, "affected_files"):
            affected = self.graph_query.affected_files(self._changed_files)
            deps = set(affected) - set(self._changed_files)
            self._dependency_files = sorted(list(deps))

    def keywords(self) -> list[str]:
        """
        Prepare a small keyword set that mirrors the weighted summary.

        Semantic refinement keywords come first when local Ollama is available.
        Static-analysis terms are retained as a deterministic fallback and for
        exact BM25 matches on important symbols and dependencies.
        """
        # Changed-code signals and dependency signals are intentionally kept in
        # separate channels until the final assembly. Do not add filenames or
        # directory/repository segments here: they are routing metadata, not
        # code-change keywords.
        changed_symbol_keywords = [
            variant
            for symbol in self._changed_symbols
            for variant in self.symbol_keyword_variants(symbol)
        ]
        changed_supporting_keywords = (
            self._refined_list("keywords")
            + self._refined_list("implementation_responsibilities")
            + self._refined_list("technical_concepts")
            + self._refined_list("architectural_concepts")
            + self._refined_list("domain_concepts")
            + self._technical_concepts
            + self._domain_concepts
            + self._workflow_steps
            + self._imports_added
        )
        dependency_keywords = self._dependency_keyword_candidates()

        changed_channel = self._filter_keyword_channel(changed_supporting_keywords)
        # Canonical changed-symbol forms are a contract and are never trimmed.
        changed_channel = self._ordered_unique_phrases(
            changed_channel[: settings.query_keyword_limit] + changed_symbol_keywords
        )
        dependency_cap = min(
            settings.query_dependency_keyword_cap,
            len(self._changed_symbols),
        )
        dependency_channel = self._filter_keyword_channel(dependency_keywords)[:dependency_cap]
        return self._ordered_unique_phrases(changed_channel + dependency_channel)

    def _dependency_keyword_candidates(self) -> list[str]:
        """Interleave dependency files so an early file cannot monopolize a cap."""
        queues = [
            [
                variant
                for symbol in self._dependency_symbols.get(file_path, [])
                for variant in self.symbol_keyword_variants(symbol)[:1]
            ]
            for file_path in self._dependency_files
        ]
        candidates: list[str] = []
        while any(queues):
            for queue in queues:
                if queue:
                    candidates.append(queue.pop(0))
        return candidates

    def _filter_keyword_channel(self, keywords: list[str]) -> list[str]:
        """Normalize one keyword channel without mixing source provenance."""
        filtered: list[str] = []
        for keyword in keywords:
            cleaned = keyword.strip().lower()
            if not cleaned or cleaned in self._SYNTAX_STOP_WORDS:
                continue
            if cleaned in self._PATH_STOP_WORDS or cleaned in self._WEAK_KEYWORDS:
                continue
            if not self._extract_meaningful_terms(cleaned):
                continue
            if any(self._keyword_redundant(cleaned, existing) for existing in filtered):
                continue
            filtered.append(cleaned)
        return filtered

    def _keyword_redundant(self, candidate: str, existing: str) -> bool:
        candidate_tokens = set(self._extract_meaningful_terms(candidate))
        existing_tokens = set(self._extract_meaningful_terms(existing))
        if not candidate_tokens or not existing_tokens:
            return False
        if candidate_tokens == existing_tokens:
            return True
        if len(candidate_tokens) == 1 and candidate_tokens <= existing_tokens:
            return True
        if len(existing_tokens) == 1 and existing_tokens <= candidate_tokens:
            return False
        return len(candidate_tokens & existing_tokens) > 1
