"""Language-neutral evidence assembly for semantic retrieval refinement.

This module records what static analysis observed and packages it into a
cluster-aware evidence structure for the semantic refiner.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from rag.preprocessing.semantic_analysis import (
    SemanticEvidenceBuilder,
    SemanticFileContext,
)
from rag.schemas.change import SymbolChange


@dataclass(slots=True)
class SemanticContextBuilder:
    """Build a stable semantic evidence packet from static-analysis output."""

    changed_files: list[str]
    changed_symbols: list[SymbolChange]
    imports_added: list[str]
    imports_removed: list[str]
    dependencies: list[str]
    dependency_symbols: dict[str, list[str]]
    calls: list[str]
    operations: list[str]
    data_flows: list[str]
    change_type: str
    file_contexts: list[dict[str, Any]] = field(default_factory=list)
    graph_query: Any | None = None

    def build(self) -> dict[str, Any]:
        symbol_types = Counter(
            str(
                getattr(
                    getattr(symbol, "symbol_type", "unknown"),
                    "value",
                    getattr(symbol, "symbol_type", "unknown"),
                )
            )
            for symbol in self.changed_symbols
        )

        file_contexts = self._file_contexts()
        # When per-file contexts are available, they are the authoritative
        # provenance for execution signals. The pipeline-level aggregates are
        # useful only for the synthetic fallback and must not be used to infer
        # calls for a different language or file.
        scoped_calls = (
            [call for context in file_contexts for call in context.calls]
            if self.file_contexts
            else self.calls
        )
        scoped_operations = (
            [operation for context in file_contexts for operation in context.operations]
            if self.file_contexts
            else self.operations
        )
        scoped_data_flows = (
            [flow for context in file_contexts for flow in context.data_flows]
            if self.file_contexts
            else self.data_flows
        )
        semantic = SemanticEvidenceBuilder(graph_query=self.graph_query).build(
            file_contexts=file_contexts,
            changed_files=self.changed_files,
            changed_symbols=[str(getattr(symbol, "name", "")) for symbol in self.changed_symbols],
            dependency_files=self.dependencies,
            dependency_symbols=self.dependency_symbols,
            imports_added=self.imports_added,
            imports_removed=self.imports_removed,
            calls=scoped_calls,
            operations=scoped_operations,
            data_flows=scoped_data_flows,
            change_type=self.change_type,
        )

        structure = {
            "changed_files": self.changed_files[:12],
            "changed_file_count": len(self.changed_files),
            "imports_added": self.imports_added[:20],
            "imports_removed": self.imports_removed[:20],
            "control_flow_and_execution": self._unique(scoped_operations)[:20],
            "call_targets": self._unique(scoped_calls)[:30],
            "data_flow_edges": self._unique(scoped_data_flows)[:30],
            "dependency_edges": [
                {
                    "file": file_path,
                    "available_symbol_count": len(symbols),
                }
                for file_path, symbols in list(self.dependency_symbols.items())[:12]
            ],
            "cluster_count": len(semantic.get("clusters", [])),
        }

        return {
            "change": {
                "classification": self.change_type,
                "changed_file_count": len(self.changed_files),
                "changed_symbol_types": dict(sorted(symbol_types.items())),
            },
            "structure": structure,
            "semantic": semantic,
        }

    def _file_contexts(self) -> list[SemanticFileContext]:
        if self.file_contexts:
            contexts: list[SemanticFileContext] = []
            for context in self.file_contexts:
                contexts.append(
                    SemanticFileContext(
                        file_path=str(context.get("file_path", "")),
                        language=str(context.get("language", "")),
                        change_type=str(context.get("change_type", self.change_type)),
                        symbols=[str(symbol) for symbol in context.get("symbols", [])],
                        imports_added=[str(item) for item in context.get("imports_added", [])],
                        imports_removed=[str(item) for item in context.get("imports_removed", [])],
                        calls=[str(item) for item in context.get("calls", [])],
                        operations=[str(item) for item in context.get("operations", [])],
                        data_flows=[str(item) for item in context.get("data_flows", [])],
                        diff_text=str(context.get("diff_text", "")),
                        semantic_change=str(context.get("semantic_change", self.change_type)),
                    )
                )
            return [context for context in contexts if context.file_path]

        synthetic_context = SemanticFileContext(
            file_path=self.changed_files[0] if self.changed_files else "<unknown>",
            language="unknown",
            change_type=self.change_type,
            symbols=[str(getattr(symbol, "name", "")) for symbol in self.changed_symbols],
            imports_added=list(self.imports_added),
            imports_removed=list(self.imports_removed),
            calls=list(self.calls),
            operations=list(self.operations),
            data_flows=list(self.data_flows),
            semantic_change=self.change_type,
        )
        return [synthetic_context]

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            cleaned = str(value).strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                result.append(cleaned)
        return result
