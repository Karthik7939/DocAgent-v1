"""
prompts/chat_prompt.py
------------------------
Prompt template for the documentation chatbot's general Q&A path.

Only used when ChatService classifies a question as "general" — i.e. not
a file-history or raw-file-content question, both of which are answered
deterministically without an LLM call. See services/chat_service.py.
"""

CHAT_ANSWER_PROMPT: str = """\
You are a helpful assistant answering questions about the repository '{repository_name}'.

CRITICAL RULES:
- Answer using ONLY the documentation and code context provided below.
- If the answer is not covered by the context, say so plainly instead of guessing.
- Reference specific files or documentation sections when relevant.
- Keep the answer concise and in Markdown.

=== GENERATED DOCUMENTATION ===
{doc_context}
=== END DOCUMENTATION ===

=== RETRIEVED CODE CONTEXT ===
{code_context}
=== END CODE CONTEXT ===

{history_block}
User question: {question}

Answer:
"""
