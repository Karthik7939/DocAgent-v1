"""
Preprocessing stage package for RAG system.

Exposes GitDiff, ASTDiff, SemanticChange, and QueryBuilder.
"""

from .git_diff import GitDiff
from .ast_diff import ASTDiff
from .semantic_change import SemanticChange
from .query_builder import QueryBuilder

__all__ = [
    "GitDiff",
    "ASTDiff",
    "SemanticChange",
    "QueryBuilder",
]
