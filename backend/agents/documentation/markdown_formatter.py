"""
agents/documentation/markdown_formatter.py
--------------------------------------------
Markdown formatting utilities shared by all document generators.

Responsibilities:
- Sanitize raw LLM markdown output.
- Ensure consistent heading hierarchy.
- Fix common LLM formatting issues.
- Provide helper functions for building Markdown programmatically.
"""

import re


# ---------------------------------------------------------------------------
# Sanitisation
# ---------------------------------------------------------------------------

def sanitize_markdown(raw: str) -> str:
    """Clean raw LLM output to produce consistent Markdown.

    Operations performed:
    - Strip outer ```markdown or ``` wrappers if LLM enclosed whole response.
    - Strip leading/trailing whitespace.
    - Collapse 3+ consecutive blank lines to 2.
    - Ensure code fences are properly closed.
    - Remove null bytes.

    Args:
        raw: Raw text from the LLM.

    Returns:
        str: Cleaned Markdown string.
    """
    if not raw:
        return ""

    # Remove null bytes
    text = raw.replace("\x00", "")

    # Normalise Windows line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Strip outer code fences if the entire document was wrapped in ``` markdown ... ```
    if text.startswith("```"):
        first_line_end = text.find("\n")
        if first_line_end != -1:
            first_line = text[:first_line_end].strip()
            if first_line in ("```", "```markdown", "```md", "```text"):
                if text.endswith("```"):
                    text = text[first_line_end + 1:-3].strip()

    # Collapse 3+ consecutive blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Ensure code fences are balanced
    text = _balance_code_fences(text)

    return text.strip()


def _balance_code_fences(text: str) -> str:
    """Ensure every opening ``` has a matching closing ```.

    Args:
        text: Markdown text that may have unbalanced fences.

    Returns:
        str: Text with balanced code fences.
    """
    fence_pattern = re.compile(r"^```", re.MULTILINE)
    fences = fence_pattern.findall(text)
    if len(fences) % 2 != 0:
        text = text.rstrip() + "\n```"
    return text


# ---------------------------------------------------------------------------
# Heading helpers
# ---------------------------------------------------------------------------

def heading(level: int, text: str) -> str:
    """Generate a Markdown heading.

    Args:
        level: Heading level (1–6).
        text:  Heading text.

    Returns:
        str: Markdown heading line.
    """
    level = max(1, min(level, 6))
    return f"{'#' * level} {text}"


def h1(text: str) -> str:
    """Shorthand for a level-1 heading."""
    return heading(1, text)


def h2(text: str) -> str:
    """Shorthand for a level-2 heading."""
    return heading(2, text)


def h3(text: str) -> str:
    """Shorthand for a level-3 heading."""
    return heading(3, text)


# ---------------------------------------------------------------------------
# List helpers
# ---------------------------------------------------------------------------

def bullet_list(items: list[str]) -> str:
    """Build a Markdown unordered list.

    Args:
        items: List items.

    Returns:
        str: Markdown bullet list, or empty string if items is empty.
    """
    if not items:
        return ""
    return "\n".join(f"- {item}" for item in items if item.strip())


def numbered_list(items: list[str]) -> str:
    """Build a Markdown ordered list.

    Args:
        items: List items.

    Returns:
        str: Markdown numbered list, or empty string if items is empty.
    """
    if not items:
        return ""
    return "\n".join(
        f"{i}. {item}" for i, item in enumerate(items, start=1) if item.strip()
    )


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

def table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a Markdown table.

    Args:
        headers: Column header names.
        rows:    Data rows (each row must have same length as headers).

    Returns:
        str: Markdown table string.
    """
    if not headers:
        return ""

    separator = " | ".join(["---"] * len(headers))
    header_row = " | ".join(headers)
    data_rows = "\n".join(
        " | ".join(str(cell) for cell in row)
        for row in rows
    )
    return f"| {header_row} |\n| {separator} |\n" + "\n".join(
        f"| {' | '.join(str(c) for c in row)} |" for row in rows
    )


# ---------------------------------------------------------------------------
# Code block helpers
# ---------------------------------------------------------------------------

def code_block(code: str, language: str = "") -> str:
    """Wrap text in a fenced Markdown code block.

    Args:
        code:     Content of the code block.
        language: Optional language identifier (e.g. 'python', 'bash').

    Returns:
        str: Fenced code block string.
    """
    return f"```{language}\n{code.strip()}\n```"


def inline_code(text: str) -> str:
    """Wrap text in inline code backticks.

    Args:
        text: Text to wrap.

    Returns:
        str: Inline code string.
    """
    return f"`{text}`"


# ---------------------------------------------------------------------------
# Section builder
# ---------------------------------------------------------------------------

def section(title: str, content: str, level: int = 2) -> str:
    """Build a complete Markdown section with heading and content.

    Args:
        title:   Section heading text.
        content: Section body content.
        level:   Heading level (default 2).

    Returns:
        str: Complete section block.
    """
    if not content or not content.strip():
        content = "Not Available"
    return f"{heading(level, title)}\n\n{content.strip()}"


def join_sections(*sections_: str) -> str:
    """Join multiple Markdown sections with double newlines.

    Args:
        *sections_: Any number of section strings.

    Returns:
        str: Combined Markdown document.
    """
    return "\n\n".join(s for s in sections_ if s and s.strip())


# ---------------------------------------------------------------------------
# Mermaid helpers
# ---------------------------------------------------------------------------

def mermaid_flowchart(edges: dict[str, list[str]]) -> str:
    """Generate a simple Mermaid top-down flowchart from an edges dict.

    Args:
        edges: Mapping of source → list of targets.

    Returns:
        str: Fenced Mermaid code block, or empty string if edges is empty.
    """
    if not edges:
        return ""

    lines = ["```mermaid", "graph TD"]
    for source, targets in edges.items():
        for target in targets:
            safe_src = source.replace(" ", "_").replace("/", "_")
            safe_tgt = target.replace(" ", "_").replace("/", "_")
            lines.append(f'    {safe_src}["{source}"] --> {safe_tgt}["{target}"]')
    lines.append("```")
    return "\n".join(lines)
