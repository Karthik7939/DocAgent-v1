"""
Shared data schemas used throughout the RAG system.

This package contains immutable Pydantic models that define the
data contracts exchanged between different RAG components.

Modules
-------
change
    Models representing semantic code changes.

chunk
    Models representing semantic code chunks.

query
    Semantic retrieval query models.

retrieval
    Retrieval result models.

graph
    Dependency graph models.

context
    Final context package passed to the agent pipeline.
"""

from .change import (
    ChangeType,
    CodeChange,
    SymbolChange,
    SymbolType,
)
from .chunk import (
    Chunk,
    ChunkCollection,
    ChunkMetadata,
    ChunkType,
)
from .context import (
    ContextMetadata,
    ContextPackage,
    PipelineResult,
)
from .graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyType,
)
from .query import SemanticQuery
from .retrieval import (
    RetrievalResult,
    RetrievalResults,
    RetrievalSource,
)

__all__ = [
    # Change
    "ChangeType",
    "SymbolType",
    "SymbolChange",
    "CodeChange",

    # Chunk
    "ChunkType",
    "ChunkMetadata",
    "Chunk",
    "ChunkCollection",

    # Query
    "SemanticQuery",

    # Retrieval
    "RetrievalSource",
    "RetrievalResult",
    "RetrievalResults",

    # Graph
    "DependencyType",
    "DependencyEdge",
    "DependencyNode",
    "DependencyGraph",

    # Context
    "ContextMetadata",
    "ContextPackage",
    "PipelineResult",
]