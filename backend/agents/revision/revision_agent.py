"""
agents/revision/revision_agent.py
-----------------------------------
Revision Agent — automatic documentation corrector.

Responsibilities (SRS Part 6, Sections 22–37):
- Read the ValidationReport from SharedMemory.
- Read generated documents from SharedMemory.
- Fix issues identified by the Validation Agent.
- Update documents in SharedMemory.
- Record revision history.
- Return control to the Coordinator for re-validation.

This agent MUST NOT:
- Generate entirely new documentation.
- Re-analyze repository files.
- Modify SharedMemory outside documentation and revision fields.
- Use Git.
- Save files to disk.
- Introduce unsupported repository claims.

Allowed revisions (SRS Part 6, Section 29):
- Fix Markdown formatting.
- Fix grammar.
- Remove hallucinated content.
- Complete missing headings.
- Improve cross-document consistency.
- Correct broken links.
- Merge duplicate sections.
"""

import logging
import re
import time
from datetime import datetime

from agents.coordinator.coordinator import AgentResult
from agents.memory.shared_memory import SharedMemory, RevisionRecord
from agents.documentation.markdown_formatter import sanitize_markdown
from prompts.revision_prompt import DOCUMENT_REVISION_PROMPT, FORMATTING_REVISION_PROMPT

logger = logging.getLogger(__name__)


class RevisionAgent:
    """
    Automatically corrects documentation issues found by the Validation Agent.

    Args:
        llm_client: Object implementing generate(prompt: str) -> str.
                    If None, only rule-based formatting fixes are applied.
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def run(self, shared_memory: SharedMemory) -> AgentResult:
        """
        Read the validation report and revise all documents with errors.

        Reads:  shared_memory.validation, .documentation, .understanding
        Writes: shared_memory.documentation (updated), .revision

        Args:
            shared_memory: The shared memory object.

        Returns:
            AgentResult: Success or failure result for the Coordinator.
        """
        start = time.monotonic()
        repo_name = shared_memory.repository.full_name or shared_memory.repository.name
        logger.info("Revision started: %s", repo_name)

        validation = shared_memory.validation
        if not validation.validation_status:
            return AgentResult(
                success=False,
                message="No validation report found — run ValidationAgent first",
                recoverable=False,
            )

        if validation.validation_status in ("PASSED",):
            logger.info("Validation already passed — no revision needed")
            return AgentResult(
                success=True,
                message="Revision skipped — validation already passed",
            )

        docs = shared_memory.documentation.all_documents()
        if not docs:
            logger.info("No file docs to revise — skipping revision")
            return AgentResult(
                success=True,
                message="Revision skipped: no file docs to revise",
            )

        logger.info("Revision report loaded")
        modified_docs: list[str] = []
        warnings: list[str] = []

        # Group errors/warnings by file path
        issues_by_doc = self._group_issues(validation)

        for file_path, content in docs.items():
            doc_issues = issues_by_doc.get(file_path, [])
            formatting_issues = [
                i for i in validation.warnings if file_path in i
            ]

            if not doc_issues and not formatting_issues:
                continue

            revised = self._revise_document(
                doc_type=file_path,
                content=content,
                issues=doc_issues,
                formatting_issues=formatting_issues,
                repo_name=repo_name,
            )

            if revised and revised != content:
                shared_memory.documentation.file_docs[file_path] = revised
                modified_docs.append(file_path)
                logger.info("%s revised", file_path)
            else:
                warnings.append(f"{file_path}: No changes made during revision")

        # Apply rule-based fixes regardless of LLM availability
        self._apply_rule_based_fixes(shared_memory)

        # Record revision history
        revision_number = shared_memory.revision.revision_count + 1
        record = RevisionRecord(
            revision_number=revision_number,
            timestamp=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            reason=f"Validation status: {validation.validation_status} "
                   f"(score={validation.quality_score:.1f})",
            modified_documents=modified_docs,
            summary=f"Revised {len(modified_docs)} document(s): {', '.join(modified_docs) or 'none'}",
        )
        shared_memory.revision.revision_count = revision_number
        shared_memory.revision.records.append(record)
        shared_memory.revision.last_revision_timestamp = record.timestamp

        duration = time.monotonic() - start
        logger.info(
            "Revision completed in %.2fs: %d document(s) revised",
            duration, len(modified_docs),
        )

        return AgentResult(
            success=True,
            message=f"Revision completed: {len(modified_docs)} document(s) updated",
            execution_time=duration,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Issue grouping
    # ------------------------------------------------------------------

    def _group_issues(self, validation) -> dict[str, list[str]]:
        """Group all validation errors by document type.

        Parses errors/warnings that start with 'DocumentType: ...' and
        groups them so each document gets only its own relevant issues.

        Args:
            validation: ValidationReport from SharedMemory.

        Returns:
            dict[str, list[str]]: document_type → list of issue strings.
        """
        groups: dict[str, list[str]] = {}

        all_issues = validation.errors + validation.hallucination_findings

        for issue in all_issues:
            # Issues formatted as "DocType: description"
            if ":" in issue:
                doc_type = issue.split(":")[0].strip()
                groups.setdefault(doc_type, []).append(issue)
            else:
                # Unattributed issue — add to all documents
                for doc_type in ["README", "Architecture", "API"]:
                    groups.setdefault(doc_type, []).append(issue)

        return groups

    # ------------------------------------------------------------------
    # Document revision
    # ------------------------------------------------------------------

    def _revise_document(
        self,
        doc_type: str,
        content: str,
        issues: list[str],
        formatting_issues: list[str],
        repo_name: str,
    ) -> str:
        """Revise a single document.

        Uses LLM if available, otherwise applies rule-based fixes only.

        Args:
            doc_type:          Document type name.
            content:           Current Markdown content.
            issues:            Critical issues from validation.
            formatting_issues: Formatting warnings from validation.
            repo_name:         Full repository name.

        Returns:
            str: Revised document content.
        """
        if self._llm and issues:
            issues_str = "\n".join(f"- {i}" for i in issues)
            prompt = DOCUMENT_REVISION_PROMPT.format(
                document_type=doc_type,
                repository_name=repo_name,
                issues=issues_str,
                document_content=content[:4000],
            )
            try:
                raw = self._llm.generate(prompt)
                revised = sanitize_markdown(raw)
                logger.info("Formatting fixed: %s", doc_type)
                logger.info("Hallucinations removed: %s", doc_type)
                logger.info("Consistency improved: %s", doc_type)
                return revised
            except Exception as exc:
                logger.warning("LLM revision failed for %s: %s", doc_type, exc)

        # Fallback: rule-based fixes only
        return self._apply_formatting_rules(content)

    # ------------------------------------------------------------------
    # Rule-based fixes
    # ------------------------------------------------------------------

    def _apply_rule_based_fixes(self, shared_memory: SharedMemory) -> None:
        """Apply deterministic formatting fixes to all documents."""
        docs = shared_memory.documentation
        if docs.readme:
            docs.readme = self._apply_formatting_rules(docs.readme)
        if docs.architecture:
            docs.architecture = self._apply_formatting_rules(docs.architecture)
        if docs.changelog:
            docs.changelog = self._apply_formatting_rules(docs.changelog)
        if docs.system_overview:
            docs.system_overview = self._apply_formatting_rules(docs.system_overview)

        for file_path, content in list(docs.file_docs.items()):
            fixed = self._apply_formatting_rules(content)
            if fixed != content:
                docs.file_docs[file_path] = fixed

    @staticmethod
    def _apply_formatting_rules(content: str) -> str:
        """Apply deterministic Markdown formatting corrections.

        Args:
            content: Markdown text to fix.

        Returns:
            str: Corrected Markdown text.
        """
        if not content:
            return content

        # Normalise line endings
        text = content.replace("\r\n", "\n").replace("\r", "\n")

        # Collapse 3+ blank lines → 2
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Balance code fences
        fence_count = len(re.findall(r"^```", text, re.MULTILINE))
        if fence_count % 2 != 0:
            text = text.rstrip() + "\n```"

        # Remove trailing spaces from each line
        text = "\n".join(line.rstrip() for line in text.splitlines())

        return text.strip()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------


