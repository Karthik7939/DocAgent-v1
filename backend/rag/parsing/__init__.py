"""
Repository parsing utilities for the RAG system.

This package performs static analysis of source code, including language
detection, AST parsing, symbol extraction, and dependency graph management.

Modules
-------
language_detector
    Detect programming language from file extensions.

ast_parser
    Parse source code into Tree-sitter syntax trees.

symbol_extractor
    Extract classes, functions, methods, and imports from ASTs.

dependency_graph
    Build, query, update, and persist file-level dependency graphs.
"""

from .ast_parser import ASTParser
from .dependency_graph import (
    DependencyGraphBuilder,
    DependencyGraphQuery,
    DependencyGraphUpdater,
    GraphPersistence,
)
from .language_detector import LanguageDetector
from .symbol_extractor import (
    ExtractedSymbol,
    ExtractionResult,
    SymbolExtractor,
)

__all__ = [
    # Language Detection
    "LanguageDetector",

    # AST Parsing
    "ASTParser",

    # Symbol Extraction
    "ExtractedSymbol",
    "ExtractionResult",
    "SymbolExtractor",

    # Dependency Graph
    "DependencyGraphBuilder",
    "DependencyGraphQuery",
    "DependencyGraphUpdater",
    "GraphPersistence",
]
