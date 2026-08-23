"""
agents/documentation/file_extractor.py
----------------------------------------
Token-aware file content extractor for the Documentation Agent.

Extracts a compact "skeleton" of a source file (imports + class/function
signatures + docstrings) that fits within a configurable character budget.
This prevents individual LLM calls from exceeding token limits on large files.

Gemini 1.5 Flash supports 1 M tokens, but we stay conservative (~1 500 tokens
per file) so each call is fast and cheap, and a large repo (300+ files) can
still be documented without hitting rate limits.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

# Default character budget for file skeletons.
# 1 token ≈ 4 chars; 6 000 chars ≈ 1 500 tokens — well within any provider limit.
MAX_FILE_CHARS: int = 6_000
SKELETON_INDENT: str = "    "


class FileContentExtractor:
    """
    Extracts an LLM-friendly skeleton of a source file within a character budget.

    Strategy (in priority order):
      1. AST-based skeleton for Python — imports + class/func signatures + docstrings.
      2. Regex-based skeleton for JS / TS / Java / Go / etc.
      3. Plain head-truncation as the final fallback.

    Args:
        max_chars: Maximum characters to include in the output (default: 6 000).
    """

    def __init__(self, max_chars: int = MAX_FILE_CHARS) -> None:
        self.max_chars = max_chars

    def extract(self, file_path: str, content: str) -> str:
        """
        Return a compact, LLM-ready representation of the file content.

        Args:
            file_path: Relative path — used only to detect the language extension.
            content:   Full source text of the file.

        Returns:
            str: Skeleton string within self.max_chars characters.
        """
        if not content or not content.strip():
            return ""

        ext = Path(file_path).suffix.lower()

        try:
            if ext == ".py":
                skeleton = self._python_skeleton(content)
            elif ext in {".js", ".jsx", ".ts", ".tsx"}:
                skeleton = self._js_skeleton(content)
            elif ext in {".java", ".kt", ".scala"}:
                skeleton = self._java_like_skeleton(content)
            elif ext == ".go":
                skeleton = self._go_skeleton(content)
            else:
                skeleton = self._head_truncate(content)

            result = self._truncate(skeleton)
            # If skeleton extraction produced very little, fall back to head
            if len(result.strip()) < 50:
                return self._head_truncate(content)
            return result

        except Exception as exc:
            logger.debug(
                "Skeleton extraction failed for %s (%s) — falling back to head truncation",
                file_path, exc,
            )
            return self._head_truncate(content)

    # ------------------------------------------------------------------
    # Python skeleton via stdlib ast module
    # ------------------------------------------------------------------

    def _python_skeleton(self, content: str) -> str:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._head_truncate(content)

        lines: list[str] = []

        # 1. Top-level imports
        import_lines: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                try:
                    import_lines.append(ast.unparse(node))
                except Exception:
                    pass
        if import_lines:
            lines.extend(import_lines)
            lines.append("")

        # 2. Top-level classes and functions
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                lines.append(self._python_class_skeleton(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lines.append(self._python_func_skeleton(node))

        return "\n".join(lines)

    @staticmethod
    def _python_class_skeleton(node: ast.ClassDef) -> str:
        try:
            bases = ", ".join(ast.unparse(b) for b in node.bases)
        except Exception:
            bases = ""
        header = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
        parts = [header]

        docstring = ast.get_docstring(node)
        if docstring:
            short_doc = docstring.split("\n")[0][:160]
            parts.append(f'    """{short_doc}"""')

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = FileContentExtractor._python_func_skeleton(item, indent=SKELETON_INDENT)
                parts.append(sig)

        if len(parts) == 1:
            parts.append("    ...")

        parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _python_func_skeleton(
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        indent: str = "",
    ) -> str:
        try:
            args = ast.unparse(node.args)
        except Exception:
            args = "..."

        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        try:
            returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        except Exception:
            returns = ""

        sig = f"{indent}{prefix} {node.name}({args}){returns}:"

        docstring = ast.get_docstring(node)
        if docstring:
            short_doc = docstring.split("\n")[0][:160]
            return f"{sig}\n{indent}    \"\"\"{short_doc}\"\"\"\n{indent}    ..."
        return f"{sig}\n{indent}    ..."

    # ------------------------------------------------------------------
    # JavaScript / TypeScript skeleton via regex
    # ------------------------------------------------------------------

    def _js_skeleton(self, content: str) -> str:
        lines: list[str] = []

        # Imports
        for m in re.finditer(r"^(import\s+.+?;?)\s*$", content, re.MULTILINE):
            lines.append(m.group(1))
        if lines:
            lines.append("")

        # Exported / top-level declarations
        patterns = [
            r"^export\s+(?:default\s+)?(?:async\s+)?function\s+\w+\s*\([^)]*\)[^{]*",
            r"^export\s+(?:default\s+)?class\s+\w+[^{]*",
            r"^(?:async\s+)?function\s+\w+\s*\([^)]*\)[^{]*",
            r"^class\s+\w+[^{]*",
            r"^export\s+(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\(",
            r"^export\s+(?:interface|type)\s+\w+[^{=;]*",
        ]
        for pattern in patterns:
            for m in re.finditer(pattern, content, re.MULTILINE):
                sig = m.group(0).strip()[:200]
                if sig:
                    lines.append(f"{sig} {{ ... }}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Java / Kotlin / Scala skeleton via regex
    # ------------------------------------------------------------------

    def _java_like_skeleton(self, content: str) -> str:
        lines: list[str] = []

        for m in re.finditer(r"^import\s+\S+;?\s*$", content, re.MULTILINE):
            lines.append(m.group(0).strip())
        if lines:
            lines.append("")

        patterns = [
            r"(?:public|private|protected|internal)?\s*(?:abstract\s+)?(?:data\s+)?(?:class|interface|object|enum)\s+\w+[^{]*",
            r"(?:public|private|protected|internal)?\s*(?:static\s+)?(?:final\s+)?(?:override\s+)?(?:\w[\w<>, ]+)\s+\w+\s*\([^)]*\)",
        ]
        for p in patterns:
            for m in re.finditer(p, content, re.MULTILINE):
                sig = m.group(0).strip()[:200]
                if sig and len(sig) > 5:
                    lines.append(f"{sig} {{ ... }}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Go skeleton via regex
    # ------------------------------------------------------------------

    def _go_skeleton(self, content: str) -> str:
        lines: list[str] = []

        for m in re.finditer(r'^import\s+"[^"]+"', content, re.MULTILINE):
            lines.append(m.group(0))
        for m in re.finditer(r"^import\s+\(.*?\)", content, re.MULTILINE | re.DOTALL):
            lines.append(m.group(0)[:400])
        if lines:
            lines.append("")

        for m in re.finditer(
            r"^(?:type\s+\w+\s+struct|func\s+(?:\(\w+\s+\*?\w+\)\s+)?\w+\s*\([^)]*\)[^{]*)",
            content,
            re.MULTILINE,
        ):
            sig = m.group(0).strip()[:200]
            if sig:
                lines.append(f"{sig} {{ ... }}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _head_truncate(self, content: str) -> str:
        """Return the first self.max_chars characters of the raw file."""
        truncated = content[: self.max_chars]
        if len(content) > self.max_chars:
            truncated += "\n... [truncated — file too large for full display]"
        return truncated

    def _truncate(self, text: str) -> str:
        """Ensure the final output does not exceed self.max_chars characters."""
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars] + "\n... [skeleton truncated for token budget]"
