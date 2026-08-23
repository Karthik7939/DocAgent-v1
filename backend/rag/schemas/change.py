"""
Schemas representing semantic code changes detected between two commits.

These models are produced by the preprocessing stage and consumed by the
query builder, retrieval pipeline, and incremental indexer.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ChangeType(str, Enum):
    """Type of file change detected by Git."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class SymbolType(str, Enum):
    """Supported source code symbol types."""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    MODULE = "module"
    VARIABLE = "variable"
    IMPORT = "import"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    STRUCT = "struct"
    TRAIT = "trait"
    UNKNOWN = "unknown"


class SymbolChange(BaseModel):
    """
    Represents a single symbol that changed within a source file.

    Examples
    --------
    Function added

        retry_connection()

    Class modified

        DatabaseManager
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ...,
        description="Name of the changed symbol.",
    )

    symbol_type: SymbolType = Field(
        default=SymbolType.UNKNOWN,
        description="Type of source code symbol.",
    )

    start_line: Optional[int] = Field(
        default=None,
        ge=1,
        description="Starting line number.",
    )

    end_line: Optional[int] = Field(
        default=None,
        ge=1,
        description="Ending line number.",
    )


class CodeChange(BaseModel):
    """
    Represents all semantic changes detected in a single file.

    Produced after combining Git diff information with AST analysis.
    """

    model_config = ConfigDict(frozen=True)

    repository: str = Field(
        ...,
        description="Repository name.",
    )

    file_path: str = Field(
        ...,
        description="Current file path.",
    )

    old_file_path: Optional[str] = Field(
        default=None,
        description="Previous file path (used for renamed files).",
    )

    change_type: ChangeType = Field(
        ...,
        description="Type of file change.",
    )

    previous_commit: str = Field(
        ...,
        description="Previous commit SHA.",
    )

    current_commit: str = Field(
        ...,
        description="Current commit SHA.",
    )

    language: str = Field(
        ...,
        description="Programming language.",
    )

    added_symbols: list[SymbolChange] = Field(
        default_factory=list,
        description="Symbols added in the file.",
    )

    modified_symbols: list[SymbolChange] = Field(
        default_factory=list,
        description="Symbols modified in the file.",
    )

    removed_symbols: list[SymbolChange] = Field(
        default_factory=list,
        description="Symbols removed from the file.",
    )

    renamed_symbols: list[dict[str, str]] = Field(
        default_factory=list,
        description="Structural symbol rename mappings with from and to names.",
    )

    imports_added: list[str] = Field(
        default_factory=list,
        description="New imports introduced.",
    )

    imports_removed: list[str] = Field(
        default_factory=list,
        description="Imports removed.",
    )

    is_semantic_change: bool = Field(
        default=True,
        description="False if only formatting/comments changed.",
    )

    summary: Optional[str] = Field(
        default=None,
        description="Optional natural language summary of the change.",
    )

    @property
    def has_symbol_changes(self) -> bool:
        """
        Returns True if at least one symbol changed.
        """
        return bool(
            self.added_symbols
            or self.modified_symbols
            or self.removed_symbols
        )

    @property
    def total_changed_symbols(self) -> int:
        """
        Total number of changed symbols.
        """
        return (
            len(self.added_symbols)
            + len(self.modified_symbols)
            + len(self.removed_symbols)
        )

    @property
    def is_new_file(self) -> bool:
        """True if the file was newly added."""
        return self.change_type == ChangeType.ADDED

    @property
    def is_deleted_file(self) -> bool:
        """True if the file was deleted."""
        return self.change_type == ChangeType.DELETED

    @property
    def is_renamed_file(self) -> bool:
        """True if the file was renamed."""
        return self.change_type == ChangeType.RENAMED

    @property
    def has_import_changes(self) -> bool:
        """
        Returns True if imports were modified.
        """
        return bool(self.imports_added or self.imports_removed)
