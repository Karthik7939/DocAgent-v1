"""
prompts/revision_prompt.py
----------------------------
Prompt templates for the Revision Agent.

Rules (SRS Part 8, Section 7):
- Prompts must NOT be embedded inside agent code.
- Templates use {placeholder} slots filled by the Revision Agent.
"""


# ---------------------------------------------------------------------------
# Document revision prompt
# ---------------------------------------------------------------------------

DOCUMENT_REVISION_PROMPT: str = """\
You are a technical documentation editor. Revise the document below based on the issues listed.
Fix ONLY the issues listed. Do not add new content. Do not invent information.
Preserve all correct content exactly as it is.

Document Type: {document_type}
Repository: {repository_name}

Issues to fix:
{issues}

Original document:
{document_content}

Return the complete revised document. Output ONLY the Markdown document — no explanation.
"""


# ---------------------------------------------------------------------------
# Formatting-only revision prompt (used when only structural issues exist)
# ---------------------------------------------------------------------------

FORMATTING_REVISION_PROMPT: str = """\
You are a Markdown editor. Fix only the formatting issues listed below in this document.
Do not change any content or add new information.

Document Type: {document_type}

Formatting issues:
{formatting_issues}

Original document:
{document_content}

Return the complete corrected document. Output ONLY the Markdown — no explanation.
"""
