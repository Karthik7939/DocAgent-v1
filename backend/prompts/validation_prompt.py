"""
prompts/validation_prompt.py
------------------------------
Prompt templates for the Validation Agent.

Rules (SRS Part 8, Section 7):
- Prompts must NOT be embedded inside agent code.
- Each template uses {placeholder} slots.
"""


# ---------------------------------------------------------------------------
# Document validation prompt
# ---------------------------------------------------------------------------

DOCUMENT_VALIDATION_PROMPT: str = """\
You are a strict technical documentation reviewer.
Evaluate the following Markdown document against the repository facts provided.
Answer ONLY based on the provided facts. Do not invent issues or approve things not present.

Document Type: {document_type}
Repository: {repository_name}

Known Repository Facts:
- Languages: {languages}
- Frameworks: {frameworks}
- Architecture: {architecture_type}
- Modules: {modules}
- APIs: {apis}
- Folders: {folders}

Document to Validate:
{document_content}

Respond in this exact format:

COMPLETENESS_SCORE: <0-100>
ACCURACY_SCORE: <0-100>
FORMATTING_SCORE: <0-100>

ERRORS:
<List each critical error on its own line. If none, write: NONE>

WARNINGS:
<List each warning on its own line. If none, write: NONE>

MISSING_SECTIONS:
<List each missing expected section on its own line. If none, write: NONE>

HALLUCINATIONS:
<List each invented fact not supported by the repository facts. If none, write: NONE>

SUMMARY:
<One paragraph summary of the document quality>
"""


# ---------------------------------------------------------------------------
# Cross-document consistency prompt
# ---------------------------------------------------------------------------

CONSISTENCY_VALIDATION_PROMPT: str = """\
You are a strict technical documentation reviewer.
Check the following documents for cross-document consistency.
Report contradictions ONLY — do not invent problems.

Repository: {repository_name}

README states:
{readme_excerpt}

Architecture states:
{architecture_excerpt}

API states:
{api_excerpt}

List all contradictions found in this format:
CONTRADICTION | DOCUMENT_A | DOCUMENT_B | DESCRIPTION
One per line.
If no contradictions found, respond with: NO_CONTRADICTIONS
"""


# ---------------------------------------------------------------------------
# Faithfulness / groundedness prompt
# ---------------------------------------------------------------------------

FAITHFULNESS_VALIDATION_PROMPT: str = """\
You are auditing auto-generated documentation for hallucination risk.
Compare the DOCUMENT below against the RETRIEVED CODE CONTEXT it was generated
from. Judge ONLY whether the document's factual claims (component names, file
paths, API routes, function names, data-flow steps) are traceable to the
retrieved context — not whether the writing is good.

Repository: {repository_name}

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

=== DOCUMENT ({document_type}) ===
{document_content}
=== END DOCUMENT ===

Score how faithfully the document is grounded in the retrieved context, on a
0-100 scale:
- 100 = every checkable claim is directly traceable to the context.
- 50 = roughly half the claims are traceable; the rest are plausible but unverifiable.
- 0 = the document appears fabricated, contradicting or unrelated to the context.

A claim you simply cannot check against the given context (because the
context doesn't cover that area) is NOT the same as an unsupported claim —
only flag claims that are actually contradicted or clearly invented.

Respond in this exact format:

FAITHFULNESS_SCORE: <0-100>
UNSUPPORTED_CLAIMS:
<List each specific claim not supported by the context, one per line. If none, write: NONE>
"""
