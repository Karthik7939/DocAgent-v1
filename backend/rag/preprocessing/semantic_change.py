"""
Semantic change classification.

Classifies structural changes into Logic, API, Documentation, Refactoring,
Formatting, Comment, Rename, or Configuration changes, using heuristics
and LLM client fallbacks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from rag.config.constants import DOCUMENTATION_EXTENSIONS
from rag.config import settings
from rag.schemas.change import SymbolChange
from rag.utils import get_logger

logger = get_logger(__name__)


class SemanticChange:
    """
    Classifies structural changes into semantic categories.
    """

    def __init__(
        self,
        file_path: str,
        change_type_git: str,
        added_symbols: list[SymbolChange],
        modified_symbols: list[SymbolChange],
        removed_symbols: list[SymbolChange],
        imports_added: Optional[list[str]] = None,
        imports_removed: Optional[list[str]] = None,
        diff_text: str = "",
        language: str = "python",
        ast_profile: Optional[dict[str, bool]] = None,
        renamed_symbols: Optional[list[dict[str, str]]] = None,
    ) -> None:
        self.file_path = file_path
        self.change_type_git = change_type_git
        self.added_symbols = added_symbols
        self.modified_symbols = modified_symbols
        self.removed_symbols = removed_symbols
        self.imports_added = imports_added or []
        self.imports_removed = imports_removed or []
        self.diff_text = diff_text
        self.language = language
        self.ast_profile = ast_profile or {}
        self.renamed_symbols = renamed_symbols or []

        # Defaults
        self._classification = "logic"
        self._is_semantic_flag = True
        self._severity = "medium"
        self._needs_doc = True

    def classify(self) -> None:
        """
        Runs heuristics and optionally LLM queries to determine the classification.
        """
        # 1. Run local heuristics
        self._classify_heuristics()

        # Per-file classification is deterministic by default. Enabling this
        # optional call can add one model request per changed file, while the
        # downstream semantic-query refinement already performs the dedicated
        # documentation reasoning request.
        if self._is_semantic_flag and settings.enable_semantic_change_llm_classification:
            try:
                self._classify_llm()
            except Exception as e:
                logger.warning(
                    "LLM semantic classification failed, using heuristic results. Error: %s",
                    e,
                )

    def _classify_heuristics(self) -> None:
        ext = Path(self.file_path).suffix.lower()

        # Documentation files
        if ext in DOCUMENTATION_EXTENSIONS:
            self._classification = "documentation"
            self._is_semantic_flag = False
            self._severity = "low"
            self._needs_doc = False
            return

        # Configuration files
        config_files = {
            "package.json",
            "package-lock.json",
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "tsconfig.json",
            "dockerfile",
            "docker-compose.yml",
        }
        config_names = {"config", "settings", "setup", "env", "properties"}
        file_name = Path(self.file_path).name.lower()
        if (
            file_name in config_files
            or any(c in file_name for c in config_names)
            or ext
            in [
                ".json",
                ".yaml",
                ".yml",
                ".toml",
                ".ini",
                ".conf",
                ".properties",
            ]
        ):
            self._classification = "configuration"
            self._is_semantic_flag = True
            self._severity = "medium"
            self._needs_doc = False
            return

        diff_signals = self._diff_signals()

        if self.renamed_symbols:
            self._classification = "rename"
            self._is_semantic_flag = True
            self._severity = "low"
            self._needs_doc = False
            return

        if self._is_structural_refactor():
            self._classification = "refactor"
            self._is_semantic_flag = True
            self._severity = "low"
            self._needs_doc = False
            return

        # Rename detection: only when the change is primarily a path move.
        if (
            self.change_type_git == "renamed"
            and not self.added_symbols
            and not self.modified_symbols
            and not self.removed_symbols
            and not diff_signals["behavioral"]
        ):
            self._classification = "rename"
            self._is_semantic_flag = True
            self._severity = "low"
            self._needs_doc = False
            return

        # Empty lists: check diff text for whitespace/comments
        if (
            not self.added_symbols
            and not self.modified_symbols
            and not self.removed_symbols
            and not self.imports_added
            and not self.imports_removed
        ):
            if self.diff_text:
                lines = self.diff_text.splitlines()
                added_lines = [
                    line
                    for line in lines
                    if line.startswith("+") and not line.startswith("+++")
                ]
                removed_lines = [
                    line
                    for line in lines
                    if line.startswith("-") and not line.startswith("---")
                ]

                only_comments = True
                only_whitespace = True

                for line in added_lines + removed_lines:
                    content = line[1:].strip()
                    if not content:
                        continue
                    only_whitespace = False

                    is_comment = False
                    if self.language == "python" and content.startswith(
                        ("#", '"""', "'''")
                    ):
                        is_comment = True
                    elif self.language in (
                        "javascript",
                        "typescript",
                        "tsx",
                        "java",
                    ) and (
                        content.startswith("//")
                        or content.startswith("/*")
                        or content.startswith("*")
                    ):
                        is_comment = True

                    if not is_comment:
                        only_comments = False

                if only_whitespace:
                    self._classification = "formatting"
                    self._is_semantic_flag = False
                    self._severity = "low"
                    self._needs_doc = False
                    return
                elif only_comments:
                    self._classification = "comment"
                    self._is_semantic_flag = False
                    self._severity = "low"
                    self._needs_doc = False
                    return
            else:
                self._classification = "logic"
                self._is_semantic_flag = True
                self._severity = "low"
                self._needs_doc = False
                return

        # Check for logging-only additions
        if self.diff_text:
            lines = self.diff_text.splitlines()
            added_lines = [
                line
                for line in lines
                if line.startswith("+") and not line.startswith("+++")
            ]
            removed_lines = [
                line
                for line in lines
                if line.startswith("-") and not line.startswith("---")
            ]

            all_logging = True
            for line in added_lines + removed_lines:
                content = line[1:].strip()
                if not content:
                    continue
                is_log = any(
                    x in content
                    for x in [
                        "logger.",
                        "log.",
                        "logging.",
                        "print(",
                        "console.log",
                        "System.out.println",
                    ]
                )
                is_comment_or_ws = (
                    content.startswith(("#", "//", "/*", "*")) or not content
                )
                if not (is_log or is_comment_or_ws):
                    all_logging = False
                    break
            if added_lines and all_logging:
                self._classification = "logic"
                self._is_semantic_flag = True
                self._severity = "low"
                self._needs_doc = False
                return

        if diff_signals["helper"]:
            self._classification = "added_helper"
            self._is_semantic_flag = True
            self._severity = "medium"
            self._needs_doc = True
            return

        if diff_signals["organization"]:
            self._classification = "code_organization"
            self._is_semantic_flag = True
            self._severity = "medium"
            self._needs_doc = True
            return

        if diff_signals["refactor"]:
            self._classification = "refactor"
            self._is_semantic_flag = True
            self._severity = "medium"
            self._needs_doc = True
            return

        if self.added_symbols or self.removed_symbols:
            self._classification = "structural_update"
            self._is_semantic_flag = True
            self._severity = "high"
            self._needs_doc = True
            return

        if self.modified_symbols:
            self._classification = "structural_update"
            self._is_semantic_flag = True
            self._severity = "medium"
            self._needs_doc = True
            return

    def _classify_llm(self) -> None:
        from rag.llm.factory import LLMFactory

        try:
            llm = LLMFactory.create()
        except Exception:
            return

        system_prompt = (
            "You are an expert software engineering assistant. Your job is to classify the semantic nature "
            "of a code change in a repository. You must respond with a raw JSON object and nothing else."
        )

        added_sym_names = [s.name for s in self.added_symbols]
        mod_sym_names = [s.name for s in self.modified_symbols]
        rem_sym_names = [s.name for s in self.removed_symbols]

        prompt = f"""
Analyze the following code change:
File Path: {self.file_path}
Git Change Type: {self.change_type_git}
Language: {self.language}
Added Symbols: {added_sym_names}
Modified Symbols: {mod_sym_names}
Removed Symbols: {rem_sym_names}
Added Imports: {self.imports_added}
Removed Imports: {self.imports_removed}

Diff Sample (first 50 lines):
{self.diff_text[:3000]}

Classify this change. You must return a valid JSON object with the following fields:
- "classification": String. Must be exactly one of: ["documentation", "logic", "api", "configuration", "refactoring", "formatting", "comment", "rename"]
- "is_semantic": Boolean. True if the change alters runtime logic, config, or public signatures. False if it only changes formatting, spacing, comments, or is an internal refactoring/logger addition with no functional effect.
- "severity": String. Must be exactly one of: ["low", "medium", "high"]
- "needs_documentation": Boolean. True if the change warrants updating docstrings, READMEs, or user guides.
- "rationale": String. Brief reasoning.

Return ONLY the raw JSON object. Do not wrap it in markdown code block ticks.
"""
        response = llm.generate(prompt, system_prompt=system_prompt)

        cleaned_response = response.strip()
        if cleaned_response.startswith("```"):
            lines = cleaned_response.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_response = "\n".join(lines).strip()

        data = json.loads(cleaned_response)

        if (
            "classification" in data
            and data["classification"]
            in [
                "documentation",
                "logic",
                "api",
                "configuration",
                "refactor",
                "refactoring",
                "formatting",
                "comment",
                "rename",
                "code_organization",
                "added_helper",
                "structural_update",
                "logging_improvement",
            ]
        ):
            self._classification = data["classification"]
        if "is_semantic" in data:
            self._is_semantic_flag = bool(data["is_semantic"])
        if (
            "severity" in data
            and data["severity"] in ["low", "medium", "high"]
        ):
            self._severity = data["severity"]
        if "needs_documentation" in data:
            self._needs_doc = bool(data["needs_documentation"])

    def is_semantic(self) -> bool:
        """
        Returns True if the change is semantic.
        """
        return self._is_semantic_flag

    def change_type(self) -> str:
        """
        Returns classified change type (e.g. logic, api, config).
        """
        return self._classification

    def severity(self) -> str:
        """
        Returns classified severity level (low, medium, high).
        """
        return self._severity

    def needs_documentation(self) -> bool:
        """
        Returns True if the change requires updated/new documentation.
        """
        return self._needs_doc

    def _diff_signals(self) -> dict[str, bool]:
        """
        Extract lightweight, language-agnostic change signals from the diff.

        The goal is to distinguish move/reorganization/refactor-style changes
        from pure renames so the classifier does not collapse unrelated
        restructuring into a rename bucket.
        """
        text = self.diff_text.lower()
        symbol_names = " ".join(
            [s.name for s in self.added_symbols + self.modified_symbols + self.removed_symbols]
        ).lower()

        helper_tokens = {"helper", "util", "utility", "common", "shared", "internal", "private"}
        organization_tokens = {
            "reorganize",
            "reorganized",
            "reorganization",
            "organize",
            "organization",
            "move",
            "moved",
            "split",
            "split up",
            "extract",
            "relocate",
            "module",
            "package",
            "directory",
            "import order",
            "reorder import",
        }
        refactor_tokens = {
            "refactor",
            "refactored",
            "cleanup",
            "clean up",
            "simplify",
            "simplified",
            "consolidate",
            "consolidated",
            "extract helper",
            "deduplicate",
            "reduce duplication",
        }
        behavioral_tokens = {
            "poll",
            "watch",
            "monitor",
            "callback",
            "invoke",
            "sync",
            "state",
            "login",
            "logout",
            "session",
            "identity",
            "track",
            "activity",
            "window",
        }

        return {
            "helper": any(token in text or token in symbol_names for token in helper_tokens)
            and bool(self.added_symbols)
            and not self.modified_symbols,
            "organization": any(token in text for token in organization_tokens),
            "refactor": any(token in text for token in refactor_tokens)
            or (bool(self.modified_symbols) and any(token in text for token in behavioral_tokens)),
            "behavioral": any(token in text for token in behavioral_tokens),
        }

    def _is_structural_refactor(self) -> bool:
        """Recognize body-only rewrites that preserve observable structure."""
        if not self.ast_profile:
            return False
        if not self.modified_symbols or self.added_symbols or self.removed_symbols:
            return False
        if self.imports_added or self.imports_removed:
            return False
        return not any(
            self.ast_profile.get(signal, False)
            for signal in (
                "control_flow_changed",
                "external_calls_changed",
                "signature_changed",
            )
        )
