"""Structured semantic analysis helpers for RAG query generation.

This module turns static-analysis output into clustered, language-agnostic
evidence that can be translated into documentation-oriented retrieval terms
by the local LLM.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NewType


# File paths are opaque routing values, not identifiers or display phrases.
# Keeping a distinct type makes accidental identifier normalization visible at
# call sites and prevents underscores from being rewritten in API payloads.
FilePath = NewType("FilePath", str)


def _clean_phrase(value: str) -> str:
    return " ".join(str(value).strip().replace("_", " ").split())


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for value in values:
        cleaned = _clean_phrase(value)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)

    return ordered


def _unique_identifiers(values: list[str]) -> list[str]:
    """Deduplicate code identifiers without changing spelling or casing."""
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        identifier = str(value).strip()
        key = identifier.lower()
        if not identifier or key in seen:
            continue
        seen.add(key)
        ordered.append(identifier)
    return ordered


def _unique_file_paths(values: list[FilePath | str]) -> list[str]:
    """Deduplicate opaque paths byte-for-byte apart from surrounding space."""
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        path = str(value)
        if not path or path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


@dataclass(slots=True)
class SemanticFileContext:
    file_path: str
    language: str
    change_type: str
    symbols: list[str] = field(default_factory=list)
    imports_added: list[str] = field(default_factory=list)
    imports_removed: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    data_flows: list[str] = field(default_factory=list)
    diff_text: str = ""
    semantic_change: str = "logic"

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_path": str(FilePath(self.file_path)),
            "language": self.language,
            "change_type": self.change_type,
            "symbols": _unique_identifiers(self.symbols),
            "imports_added": _unique(self.imports_added),
            "imports_removed": _unique(self.imports_removed),
            "calls": _unique_identifiers(self.calls),
            "operations": _unique(self.operations),
            "data_flows": _unique(self.data_flows),
            "diff_excerpt": self._diff_excerpt(),
            "semantic_change": self.semantic_change,
        }

    def _diff_excerpt(self, limit: int = 8) -> list[str]:
        lines: list[str] = []
        for raw_line in self.diff_text.splitlines():
            if not raw_line.startswith(("+", "-")):
                continue
            if raw_line.startswith(("+++", "---")):
                continue
            text = raw_line[1:].strip()
            if text:
                lines.append(text)
            if len(lines) >= limit:
                break
        return lines


@dataclass(slots=True)
class SemanticCluster:
    cluster_id: str
    files: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    data_flows: list[str] = field(default_factory=list)
    change_types: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "files": _unique_file_paths([FilePath(file_path) for file_path in self.files]),
            "languages": _unique(self.languages),
            "symbols": _unique_identifiers(self.symbols),
            "imports": _unique(self.imports),
            "calls": _unique_identifiers(self.calls),
            "operations": _unique(self.operations),
            "data_flows": _unique(self.data_flows),
            "change_types": _unique(self.change_types),
        }


class SemanticClusterer:
    """Build file-level clusters from dependency and structural overlap."""

    def __init__(self, graph_query: Any | None = None) -> None:
        self._graph_query = graph_query

    def cluster(
        self,
        file_contexts: list[SemanticFileContext],
        dependency_files: list[str],
    ) -> list[SemanticCluster]:
        if not file_contexts:
            return []

        contexts_by_file = {context.file_path: context for context in file_contexts}
        adjacency = self._build_adjacency(contexts_by_file, dependency_files)
        components = self._connected_components(list(contexts_by_file.keys()), adjacency)

        clusters: list[SemanticCluster] = []
        for index, component in enumerate(components, start=1):
            clustered_contexts = [
                contexts_by_file[file_path]
                for file_path in component
                if file_path in contexts_by_file
            ]
            if not clustered_contexts:
                continue

            clusters.append(self._build_cluster(index, clustered_contexts))

        return clusters

    def _build_adjacency(
        self,
        contexts_by_file: dict[str, SemanticFileContext],
        dependency_files: list[str],
    ) -> dict[str, set[str]]:
        adjacency: dict[str, set[str]] = {file_path: set() for file_path in contexts_by_file}

        if self._graph_query is not None:
            for file_path in contexts_by_file:
                neighbors: set[str] = set()
                if hasattr(self._graph_query, "get_neighbors"):
                    neighbors = set(self._graph_query.get_neighbors(file_path))
                elif hasattr(self._graph_query, "affected_files"):
                    neighbors = set(self._graph_query.affected_files([file_path]))
                for neighbor in neighbors:
                    # Do not merge call evidence across language boundaries.
                    # A dependency relationship remains available in semantic
                    # evidence, while each cluster retains calls proven by its
                    # own file's AST.
                    if (
                        neighbor in adjacency
                        and neighbor != file_path
                        and contexts_by_file[neighbor].language == contexts_by_file[file_path].language
                    ):
                        adjacency[file_path].add(neighbor)
                        adjacency[neighbor].add(file_path)

        files = list(contexts_by_file.values())
        for index, left in enumerate(files):
            left_signals = self._signals(left)
            for right in files[index + 1 :]:
                if left.language != right.language:
                    continue
                overlap = left_signals & self._signals(right)
                if len(overlap) >= 2:
                    adjacency[left.file_path].add(right.file_path)
                    adjacency[right.file_path].add(left.file_path)

        for file_path in dependency_files:
            adjacency.setdefault(file_path, set())

        return adjacency

    @staticmethod
    def _signals(context: SemanticFileContext) -> set[str]:
        signals = set()
        signals.update(item.lower() for item in context.calls)
        signals.update(item.lower() for item in context.operations)
        signals.update(item.lower() for item in context.data_flows)
        signals.update(item.lower() for item in context.imports_added)
        return {signal for signal in signals if signal}

    @staticmethod
    def _connected_components(
        nodes: list[str],
        adjacency: dict[str, set[str]],
    ) -> list[list[str]]:
        seen: set[str] = set()
        components: list[list[str]] = []

        for node in nodes:
            if node in seen:
                continue

            stack = [node]
            component: list[str] = []
            seen.add(node)

            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in adjacency.get(current, set()):
                    if neighbor in seen:
                        continue
                    seen.add(neighbor)
                    stack.append(neighbor)

            components.append(sorted(component))

        return components

    def _build_cluster(
        self,
        cluster_index: int,
        file_contexts: list[SemanticFileContext],
    ) -> SemanticCluster:
        return SemanticCluster(
            cluster_id=f"cluster_{cluster_index}",
            files=[str(FilePath(context.file_path)) for context in file_contexts],
            languages=_unique([context.language for context in file_contexts]),
            symbols=_unique_identifiers([symbol for context in file_contexts for symbol in context.symbols]),
            imports=_unique(
                [
                    import_name
                    for context in file_contexts
                    for import_name in context.imports_added + context.imports_removed
                ]
            ),
            calls=_unique_identifiers([call for context in file_contexts for call in context.calls]),
            operations=_unique([operation for context in file_contexts for operation in context.operations]),
            data_flows=_unique([flow for context in file_contexts for flow in context.data_flows]),
            change_types=_unique([context.change_type for context in file_contexts]),
        )


class SemanticEvidenceBuilder:
    """Assemble the structured evidence packet consumed by the LLM."""

    def __init__(self, graph_query: Any | None = None) -> None:
        self._clusterer = SemanticClusterer(graph_query=graph_query)

    def build(
        self,
        file_contexts: list[SemanticFileContext],
        changed_files: list[str],
        changed_symbols: list[str],
        dependency_files: list[str],
        dependency_symbols: dict[str, list[str]],
        imports_added: list[str],
        imports_removed: list[str],
        calls: list[str],
        operations: list[str],
        data_flows: list[str],
        change_type: str,
    ) -> dict[str, Any]:
        clusters = self._clusterer.cluster(file_contexts, dependency_files)
        structural_summary = self._structural_summary(
            file_contexts=file_contexts,
            changed_files=changed_files,
            changed_symbols=changed_symbols,
            imports_added=imports_added,
            imports_removed=imports_removed,
            calls=calls,
            operations=operations,
            data_flows=data_flows,
            change_type=change_type,
        )

        return {
            "module_type": self._module_type(file_contexts, clusters),
            "behaviors": self._behaviors(file_contexts, operations, calls, data_flows),
            "responsibilities": [],
            "workflow": self._workflow(file_contexts, operations),
            "technical_concepts": self._technical_concepts(file_contexts, imports_added, operations, calls, data_flows),
            "domain_concepts": [],
            "dependencies": self._dependencies(dependency_files, dependency_symbols),
            "clusters": [cluster.as_dict() for cluster in clusters],
            "structural_summary": structural_summary,
            "traceability": {
                "changed_files": _unique_file_paths([FilePath(file_path) for file_path in changed_files]),
                "modified_symbols": _unique_identifiers(changed_symbols),
                "dependency_symbols": {
                    str(FilePath(file_path)): _unique_identifiers(symbols)
                    for file_path, symbols in dependency_symbols.items()
                },
            },
        }

    @staticmethod
    def _module_type(
        file_contexts: list[SemanticFileContext],
        clusters: list[SemanticCluster],
    ) -> str:
        if len(clusters) > 1:
            return "multi-file change"
        if len(file_contexts) > 1:
            return "multi-file module"
        if not file_contexts:
            return "module"
        context = file_contexts[0]
        if context.symbols and len(context.symbols) > 3:
            return "symbol-rich module"
        return f"{context.language or 'source'} module"

    @staticmethod
    def _behaviors(
        file_contexts: list[SemanticFileContext],
        operations: list[str],
        calls: list[str],
        data_flows: list[str],
    ) -> list[str]:
        phrases: list[str] = []
        phrases.extend(operations)
        phrases.extend(calls)
        phrases.extend(data_flows)
        phrases.extend(
            context.semantic_change
            for context in file_contexts
            if context.semantic_change
        )
        return _unique(phrases)

    @staticmethod
    def _workflow(
        file_contexts: list[SemanticFileContext],
        operations: list[str],
    ) -> list[str]:
        if not file_contexts:
            return _unique(operations)

        ordered: list[str] = []
        for context in file_contexts:
            ordered.extend(context.operations)
            ordered.extend(context.calls)
            ordered.extend(context.data_flows)
        if not ordered:
            ordered = list(operations)
        return _unique(ordered)

    @staticmethod
    def _technical_concepts(
        file_contexts: list[SemanticFileContext],
        imports_added: list[str],
        operations: list[str],
        calls: list[str],
        data_flows: list[str],
    ) -> list[str]:
        concepts: list[str] = []
        concepts.extend(imports_added)
        concepts.extend(operations)
        concepts.extend(calls)
        concepts.extend(data_flows)
        concepts.extend(
            context.language for context in file_contexts if context.language
        )
        return _unique(concepts)

    @staticmethod
    def _dependencies(
        dependency_files: list[str],
        dependency_symbols: dict[str, list[str]],
    ) -> list[str]:
        dependency_phrases = _unique_file_paths([FilePath(file_path) for file_path in dependency_files])
        dependency_phrases.extend(
            symbol
            for symbols in dependency_symbols.values()
            for symbol in _unique_identifiers(symbols)
        )
        return _unique_identifiers(dependency_phrases)

    @staticmethod
    def _structural_summary(
        file_contexts: list[SemanticFileContext],
        changed_files: list[str],
        changed_symbols: list[str],
        imports_added: list[str],
        imports_removed: list[str],
        calls: list[str],
        operations: list[str],
        data_flows: list[str],
        change_type: str,
    ) -> dict[str, Any]:
        file_types = Counter()
        languages = Counter()
        for context in file_contexts:
            language = context.language or Path(context.file_path).suffix.lstrip(".") or "unknown"
            file_types[language] += 1
            languages[language] += 1

        return {
            "change_type": change_type,
            "file_count": len(_unique(changed_files)),
            "symbol_count": len(_unique(changed_symbols)),
            "language_count": len([language for language in languages if language]),
            "imports_added_count": len(_unique(imports_added)),
            "imports_removed_count": len(_unique(imports_removed)),
            "call_count": len(_unique(calls)),
            "operation_count": len(_unique(operations)),
            "data_flow_count": len(_unique(data_flows)),
            "file_types": dict(sorted(file_types.items())),
            "languages": dict(sorted(languages.items())),
        }
