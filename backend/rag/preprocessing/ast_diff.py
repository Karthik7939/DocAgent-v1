"""
AST symbol differences extraction.

Compares syntax trees of a file between two source code versions to detect
added, deleted, and modified symbols (classes, functions, and methods).
It ignores whitespace, formatting, comments, and import ordering.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from difflib import SequenceMatcher
from typing import Optional

from rag.parsing.symbol_extractor import ExtractedSymbol, SymbolExtractor
from rag.schemas.change import SymbolChange, SymbolType
from rag.config import settings


def python_ast_symbols(source: str) -> list[ExtractedSymbol]:
    """Return complete Python definition spans independent of parser fallback."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    symbols: list[ExtractedSymbol] = []

    def visit(body: list[ast.stmt], parent: str | None = None) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                symbols.append(
                    ExtractedSymbol(
                        name=node.name,
                        symbol_type="class",
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        parent=parent,
                        signature=lines[node.lineno - 1].strip(),
                    )
                )
                visit(node.body, parent=node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(
                    ExtractedSymbol(
                        name=node.name,
                        symbol_type="method" if parent else "function",
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        parent=parent,
                        signature=lines[node.lineno - 1].strip(),
                    )
                )
                visit(node.body, parent=parent)

    visit(tree.body)
    return symbols


def normalize_python_source(source_code: str) -> str:
    """
    Normalizes Python source code by removing comments, docstrings, and formatting/whitespaces.
    """
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source_code).readline)
        result = []
        for tok in tokens:
            token_type = tok.type
            token_string = tok.string

            if token_type == tokenize.COMMENT:
                continue

            if token_type == tokenize.STRING:
                s = token_string.strip()
                if s.startswith(('"""', "'''")):
                    continue

            if token_type in (
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENDMARKER,
            ):
                continue

            result.append(token_string)
        return "".join(result)
    except Exception:
        return normalize_generic_source(source_code)


def normalize_generic_source(source_code: str) -> str:
    """
    Generic fallback normalizer. Removes comments and whitespaces.
    """
    lines = source_code.splitlines()
    cleaned_lines = []
    for line in lines:
        if "#" in line:
            line = line.split("#", 1)[0]
        if "//" in line:
            line = line.split("//", 1)[0]
        cleaned_lines.append(line.strip())

    content = "\n".join(cleaned_lines)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return re.sub(r"\s+", "", content)


def get_symbol_source(
    source_lines: list[str],
    symbol: ExtractedSymbol,
    methods: list[ExtractedSymbol] = None,
) -> str:
    """
    Extracts the source text for a symbol, subtracting method bodies if the symbol is a class.
    """
    sym_lines = source_lines[symbol.start_line - 1 : symbol.end_line]
    sym_text = "\n".join(sym_lines)

    if symbol.symbol_type == "class" and methods:
        class_start = symbol.start_line
        class_lines = list(sym_lines)
        for m in sorted(methods, key=lambda x: x.start_line, reverse=True):
            if (
                m.parent == symbol.name
                and m.start_line >= class_start
                and m.end_line <= symbol.end_line
            ):
                start_idx = m.start_line - class_start
                end_idx = m.end_line - class_start
                for idx in range(start_idx, end_idx + 1):
                    if idx < len(class_lines):
                        class_lines[idx] = ""
        sym_text = "\n".join(class_lines)

    return sym_text


class ASTDiff:
    """
    Compares the AST structures of a file before and after changes.
    """

    def __init__(
        self,
        old_source: str,
        new_source: str,
        language: str,
    ) -> None:
        self.old_source = old_source
        self.new_source = new_source
        self.language = language

        self._added: list[SymbolChange] = []
        self._deleted: list[SymbolChange] = []
        self._modified: list[SymbolChange] = []
        self._unchanged: list[SymbolChange] = []
        self._imports_added: list[str] = []
        self._imports_removed: list[str] = []
        self._calls_added: list[str] = []
        self._operations_added: list[str] = []
        self._data_flows_added: list[str] = []
        self._renamed: list[dict[str, str]] = []
        self._structural_profile: dict[str, bool] = {}

    def compare(self) -> None:
        """
        Performs the comparison between old and new ASTs.
        """
        extractor = SymbolExtractor()

        old_res = extractor.extract(self.old_source, self.language)
        new_res = extractor.extract(self.new_source, self.language)

        old_lines = self.old_source.splitlines()
        new_lines = self.new_source.splitlines()

        def normalize(src: str) -> str:
            if self.language == "python":
                return normalize_python_source(src)
            return normalize_generic_source(src)

        old_symbol_list = python_ast_symbols(self.old_source) if self.language == "python" else old_res.all_symbols
        new_symbol_list = python_ast_symbols(self.new_source) if self.language == "python" else new_res.all_symbols
        old_syms = {
            (s.parent, s.name, s.symbol_type): s for s in old_symbol_list
        }
        new_syms = {
            (s.parent, s.name, s.symbol_type): s for s in new_symbol_list
        }

        # Deleted symbols
        for key, sym in old_syms.items():
            if key not in new_syms:
                symbol_type = (
                    SymbolType(sym.symbol_type)
                    if sym.symbol_type in [t.value for t in SymbolType]
                    else SymbolType.UNKNOWN
                )
                self._deleted.append(
                    SymbolChange(
                        name=sym.name,
                        symbol_type=symbol_type,
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                    )
                )

        # Added symbols
        for key, sym in new_syms.items():
            if key not in old_syms:
                symbol_type = (
                    SymbolType(sym.symbol_type)
                    if sym.symbol_type in [t.value for t in SymbolType]
                    else SymbolType.UNKNOWN
                )
                self._added.append(
                    SymbolChange(
                        name=sym.name,
                        symbol_type=symbol_type,
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                    )
                )

        # Modified & Unchanged symbols
        for key, sym_new in new_syms.items():
            if key in old_syms:
                sym_old = old_syms[key]

                old_text = get_symbol_source(old_lines, sym_old, old_res.methods)
                new_text = get_symbol_source(new_lines, sym_new, new_res.methods)

                symbol_type = (
                    SymbolType(sym_new.symbol_type)
                    if sym_new.symbol_type in [t.value for t in SymbolType]
                    else SymbolType.UNKNOWN
                )

                if normalize(old_text) != normalize(new_text):
                    self._modified.append(
                        SymbolChange(
                            name=sym_new.name,
                            symbol_type=symbol_type,
                            start_line=sym_new.start_line,
                            end_line=sym_new.end_line,
                        )
                    )
                else:
                    self._unchanged.append(
                        SymbolChange(
                            name=sym_new.name,
                            symbol_type=symbol_type,
                            start_line=sym_new.start_line,
                            end_line=sym_new.end_line,
                        )
                    )

        self._detect_renames(old_syms, new_syms, old_lines, new_lines, old_res.methods, new_res.methods)

        # Imports comparison
        old_imports = set(old_res.imports)
        new_imports = set(new_res.imports)
        self._imports_added = sorted(list(new_imports - old_imports))
        self._imports_removed = sorted(list(old_imports - new_imports))
        self._calls_added = sorted(list(set(new_res.calls) - set(old_res.calls)))
        self._operations_added = sorted(
            list(set(new_res.operations) - set(old_res.operations))
        )
        self._data_flows_added = sorted(
            list(set(new_res.data_flows) - set(old_res.data_flows))
        )
        self._structural_profile = {
            "control_flow_changed": set(old_res.operations) != set(new_res.operations),
            "external_calls_changed": set(old_res.calls) != set(new_res.calls),
            "signature_changed": any(
                old_syms[key].signature != new_syms[key].signature
                for key in old_syms.keys() & new_syms.keys()
            ),
        }

    def added_symbols(self) -> list[SymbolChange]:
        """
        Returns symbols added.
        """
        return self._added

    def deleted_symbols(self) -> list[SymbolChange]:
        """
        Returns symbols deleted.
        """
        return self._deleted

    def modified_symbols(self) -> list[SymbolChange]:
        """
        Returns symbols modified.
        """
        return self._modified

    def unchanged_symbols(self) -> list[SymbolChange]:
        """
        Returns symbols unchanged.
        """
        return self._unchanged

    def imports_added(self) -> list[str]:
        """
        Returns new imports introduced.
        """
        return self._imports_added

    def imports_removed(self) -> list[str]:
        """
        Returns imports removed.
        """
        return self._imports_removed

    def calls_added(self) -> list[str]:
        """
        Returns newly introduced call expressions.
        """
        return self._calls_added

    def operations_added(self) -> list[str]:
        """
        Returns newly introduced structural operations.
        """
        return self._operations_added

    def data_flows_added(self) -> list[str]:
        """Returns newly introduced generic assignment data-flow edges."""
        return self._data_flows_added

    def renamed_symbols(self) -> list[dict[str, str]]:
        """Returns structurally paired symbol rename mappings."""
        return self._renamed

    def structural_profile(self) -> dict[str, bool]:
        """Signals used to distinguish refactors from behavior changes."""
        return dict(self._structural_profile)

    def _detect_renames(self, old_syms, new_syms, old_lines, new_lines, old_methods, new_methods) -> None:
        """Pair removed and added symbols when their normalized bodies match."""
        deleted_by_name = {symbol.name: symbol for symbol in self._deleted}
        added_by_name = {symbol.name: symbol for symbol in self._added}
        old_lookup = {symbol.name: symbol for symbol in old_syms.values()}
        new_lookup = {symbol.name: symbol for symbol in new_syms.values()}
        consumed_old: set[str] = set()
        consumed_new: set[str] = set()

        for old_name, deleted in deleted_by_name.items():
            old_symbol = old_lookup.get(old_name)
            if old_symbol is None:
                continue
            old_body = self._normalized_symbol_body(get_symbol_source(old_lines, old_symbol, old_methods), old_name)
            best: tuple[float, str, SymbolChange] | None = None
            for new_name, added in added_by_name.items():
                if new_name in consumed_new or added.symbol_type != deleted.symbol_type:
                    continue
                new_symbol = new_lookup.get(new_name)
                if new_symbol is None:
                    continue
                new_body = self._normalized_symbol_body(get_symbol_source(new_lines, new_symbol, new_methods), new_name)
                score = SequenceMatcher(None, old_body, new_body).ratio()
                if score >= settings.symbol_rename_similarity_threshold and (best is None or score > best[0]):
                    best = (score, new_name, added)
            if best is not None:
                _, new_name, added = best
                consumed_old.add(old_name)
                consumed_new.add(new_name)
                self._renamed.append({"from": old_name, "to": new_name})
                self._modified.append(added)

        self._deleted = [symbol for symbol in self._deleted if symbol.name not in consumed_old]
        self._added = [symbol for symbol in self._added if symbol.name not in consumed_new]

    def _normalized_symbol_body(self, source: str, symbol_name: str) -> str:
        normalized = normalize_python_source(source) if self.language == "python" else normalize_generic_source(source)
        return re.sub(rf"\b{re.escape(symbol_name)}\b", "<symbol>", normalized)
