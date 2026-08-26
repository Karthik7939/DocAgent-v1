"""
agents/documentation/code_reports.py
--------------------------------------
Deterministic, code-driven analysis reports — no LLM calls.

Both reports operate on ``RepositoryUnderstanding.dependency_graph``
(component -> [dependencies]), which the Understanding Agent already builds
from RAG-grounded LLM analysis. Everything below it is pure graph
algorithms, so results are reproducible and don't hallucinate.

  - find_circular_dependencies(): DFS-based cycle detection.
  - find_unreferenced_components(): components nothing else depends on,
    excluding known entry points. This is a heuristic over the identified
    dependency graph, not a full cross-file reference analysis — it flags
    candidates for review, not confirmed dead code.
"""

from __future__ import annotations

from typing import Dict, List


def find_circular_dependencies(dependency_graph: Dict[str, List[str]]) -> List[List[str]]:
    """Return every distinct dependency cycle found in the graph.

    Each cycle is a list of component names in traversal order, e.g.
    ``["A", "B", "C", "A"]`` for A -> B -> C -> A.
    """
    cycles: List[List[str]] = []
    seen_cycle_keys: set[frozenset] = set()

    visiting: set[str] = set()
    visited: set[str] = set()
    path: List[str] = []

    def dfs(node: str) -> None:
        visiting.add(node)
        path.append(node)

        for dep in dependency_graph.get(node, []):
            if dep in visiting:
                cycle_start = path.index(dep)
                cycle = path[cycle_start:] + [dep]
                key = frozenset(cycle)
                if key not in seen_cycle_keys:
                    seen_cycle_keys.add(key)
                    cycles.append(cycle)
            elif dep not in visited and dep in dependency_graph:
                dfs(dep)

        path.pop()
        visiting.discard(node)
        visited.add(node)

    for component in dependency_graph:
        if component not in visited:
            dfs(component)

    return cycles


def find_unreferenced_components(
    dependency_graph: Dict[str, List[str]],
    entry_points: List[str],
) -> List[str]:
    """Return components that no other identified component depends on.

    Excludes declared entry points (they are meant to have zero inbound
    edges) and components with no outbound edges either (leaf-only nodes
    with a single mention are too ambiguous to flag reliably).
    """
    referenced: set[str] = set()
    for deps in dependency_graph.values():
        referenced.update(deps)

    entry_point_names = {ep.strip().lower() for ep in entry_points}

    unreferenced = [
        component
        for component, deps in dependency_graph.items()
        if component not in referenced
        and deps
        and component.strip().lower() not in entry_point_names
    ]
    return sorted(unreferenced)


def render_reports_markdown(
    repo_name: str,
    dependency_graph: Dict[str, List[str]],
    entry_points: List[str],
) -> str:
    """Render the full REPORTS.md content from the dependency graph."""
    lines: List[str] = [f"# Reports — {repo_name}", ""]
    lines.append(
        "Deterministic, code-derived analysis of the component dependency "
        "graph identified by the Understanding Agent. No LLM calls are used "
        "to produce this document, so results are reproducible run-to-run."
    )
    lines.append("")

    if not dependency_graph:
        lines.append(
            "## Dependency Graph\n\nNo dependency relationships were "
            "identified for this repository yet."
        )
        return "\n".join(lines)

    # --- Circular Dependencies ---
    lines.append("## Circular Dependencies")
    cycles = find_circular_dependencies(dependency_graph)
    if cycles:
        lines.append(
            f"\n{len(cycles)} circular dependency chain(s) detected:\n"
        )
        for cycle in cycles:
            lines.append(f"- `{' → '.join(cycle)}`")
    else:
        lines.append("\nNo circular dependencies detected in the identified component graph.")
    lines.append("")

    # --- Unreferenced Components ---
    lines.append("## Unreferenced Components")
    unreferenced = find_unreferenced_components(dependency_graph, entry_points)
    if unreferenced:
        lines.append(
            "\nComponents that no other identified component depends on "
            "and that are not declared entry points. These are candidates "
            "for review — not confirmed dead code:\n"
        )
        for component in unreferenced:
            lines.append(f"- `{component}`")
    else:
        lines.append("\nEvery identified component is referenced by at least one other component.")
    lines.append("")

    # --- Raw Graph ---
    lines.append("## Full Dependency Graph")
    lines.append("")
    for component, deps in dependency_graph.items():
        if deps:
            for dep in deps:
                lines.append(f"- `{component}` → `{dep}`")
    lines.append("")

    return "\n".join(lines)
