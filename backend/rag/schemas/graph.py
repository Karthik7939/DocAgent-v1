"""
Schemas representing the repository dependency graph.

These models define the persisted graph structure used for dependency-based
retrieval. Graph construction and traversal logic are implemented separately
in parsing/dependency_graph.py.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DependencyType(str, Enum):
    """
    Supported dependency relationship types.
    """

    IMPORT = "import"
    CALL = "call"
    INHERITANCE = "inheritance"
    IMPLEMENTS = "implements"
    COMPOSITION = "composition"
    REFERENCE = "reference"


class DependencyEdge(BaseModel):
    """
    Represents a directed dependency between two files.
    """

    model_config = ConfigDict(frozen=True)

    source: str = Field(
        ...,
        description="Source file.",
    )

    target: str = Field(
        ...,
        description="Target file.",
    )

    dependency_type: DependencyType = Field(
        ...,
        description="Relationship between the source and target.",
    )


class DependencyNode(BaseModel):
    """
Represents a repository file in the dependency graph.

Nodes contain only file-specific metadata. Relationships between files
are represented exclusively by DependencyEdge objects.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(
        ...,
        description="Repository-relative file path.",
    )

    language: str = Field(
        ...,
        description="Programming language.",
    )


    symbols: list[str] = Field(
    default_factory=list,
    description="Symbols defined in this file.",
)
    
    # imports: list[str] = Field(
    #     default_factory=list,
    #     description="Files imported by this file.",
    # )

    # imported_by: list[str] = Field(
    #     default_factory=list,
    #     description="Files importing this file.",
    # )


class DependencyGraph(BaseModel):
    """
    Repository dependency graph.

    Stores nodes using an adjacency-list representation for efficient lookup.
    """

    model_config = ConfigDict(frozen=True)

    repository: str = Field(
        ...,
        description="Repository name.",
    )

    commit_sha: str = Field(
        ...,
        description="Commit SHA corresponding to this graph.",
    )

    nodes: dict[str, DependencyNode] = Field(
        default_factory=dict,
        description="Mapping of file paths to dependency nodes.",
    )

    edges: list[DependencyEdge] = Field(
        default_factory=list,
        description="Directed dependency edges.",
    )

    @property
    def total_nodes(self) -> int:
        """
        Returns the total number of nodes.
        """
        return len(self.nodes)

    @property
    def total_edges(self) -> int:
        """
        Returns the total number of dependency edges.
        """
        return len(self.edges)

    def has_node(self, file_path: str) -> bool:
        """
        Checks whether a file exists in the graph.

        Parameters
        ----------
        file_path : str
            Repository-relative file path.

        Returns
        -------
        bool
            True if the node exists.
        """
        return file_path in self.nodes

    def get_node(self, file_path: str) -> DependencyNode | None:
        """
        Returns the dependency node for a file.

        Parameters
        ----------
        file_path : str
            Repository-relative file path.

        Returns
        -------
        DependencyNode | None
            The corresponding node if present.
        """
        return self.nodes.get(file_path)