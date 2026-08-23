"""
agents/validation/validation_agent.py
---------------------------------------
Validation Agent — documentation quality assurance.

Responsibilities (SRS Part 6):
- Validate every generated document for completeness, accuracy,
  consistency, formatting, and hallucinations.
- Produce a structured validation report.
- Compute an overall quality score (0–100).
- Write the report into SharedMemory.validation.
- Return PASSED, PASSED_WITH_WARNINGS, or FAILED status.

This agent MUST NOT:
- Modify or rewrite documentation.
- Read repository files directly.
- Use Git.
- Save files to disk.
- Generate new documentation.
"""

import logging
import re
import time
from dataclasses import dataclass, field

from agents.coordinator.coordinator import AgentResult
from agents.memory.shared_memory import SharedMemory, ValidationReport
from prompts.validation_prompt import DOCUMENT_VALIDATION_PROMPT, CONSISTENCY_VALIDATION_PROMPT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds  (SRS Part 6, Section 19)
# ---------------------------------------------------------------------------

PASS_THRESHOLD: float = 70.0          # minimum score to PASS
WARN_THRESHOLD: float = 85.0          # score above this = PASSED, below = PASSED_WITH_WARNINGS

# ---------------------------------------------------------------------------
# Quality score weights  (SRS Part 6, Section 16)
# ---------------------------------------------------------------------------

WEIGHT_COMPLETENESS: float = 0.25
WEIGHT_ACCURACY: float = 0.30
WEIGHT_CONSISTENCY: float = 0.20
WEIGHT_MARKDOWN: float = 0.10
WEIGHT_COVERAGE: float = 0.10
WEIGHT_READABILITY: float = 0.05

# ---------------------------------------------------------------------------
# Expected sections in every per-file document
# ---------------------------------------------------------------------------

FILE_DOC_EXPECTED_SECTIONS: list[str] = [
    "## Overview",
    "## Change Summary",
    "## Key Components",
]


# ---------------------------------------------------------------------------
# Per-document validation result
# ---------------------------------------------------------------------------

@dataclass
class DocumentValidationResult:
    """Result of validating a single document."""

    document_type: str
    completeness_score: float = 0.0
    accuracy_score: float = 0.0
    formatting_score: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    hallucinations: list[str] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Validation Agent
# ---------------------------------------------------------------------------

class ValidationAgent:
    """
    Evaluates every generated document and produces a quality report.

    Args:
        llm_client: Object implementing generate(prompt: str) -> str.
                    Pass None to use rule-based validation only (no LLM scoring).
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def run(self, shared_memory: SharedMemory) -> AgentResult:
        """
        Validate all per-file documents in SharedMemory and write the report.

        Reads:  shared_memory.documentation.file_docs
        Writes: shared_memory.validation

        Args:
            shared_memory: The shared memory object.

        Returns:
            AgentResult: Success result (agent itself succeeds even if docs fail).
        """
        start = time.monotonic()
        repo_name = shared_memory.repository.full_name or shared_memory.repository.name
        logger.info("Validation started: %s", repo_name)

        docs = shared_memory.documentation.all_documents()
        if not docs:
            report = ValidationReport(
                validation_status="FAILED",
                quality_score=0.0,
                errors=["No documents were generated in shared memory"],
                timestamp=_now(),
            )
            shared_memory.validation = report
            return AgentResult(
                success=True,
                message="Validation completed: FAILED (no documents in shared memory)",
                errors=["No documents found in shared memory"],
            )

        # 1 — Rule-based structural validation (no LLM needed)
        doc_results: list[DocumentValidationResult] = []
        for file_path, content in docs.items():
            result = self._validate_structure(file_path, content)
            doc_results.append(result)
            logger.info(
                "File doc validation completed: %s  formatting=%.0f",
                file_path, result.formatting_score,
            )

        # 2 — LLM-based content validation (if LLM is available)
        if self._llm:
            self._validate_content_with_llm(shared_memory, doc_results)
            logger.info("LLM content validation completed")

        # 3 — Compute overall score
        overall_score = self._compute_overall_score(doc_results)

        # 4 — Determine status
        if overall_score >= WARN_THRESHOLD:
            status = "PASSED"
        elif overall_score >= PASS_THRESHOLD:
            status = "PASSED_WITH_WARNINGS"
        else:
            status = "FAILED"

        # 5 — Aggregate results
        all_errors = [e for r in doc_results for e in r.errors]
        all_warnings = [w for r in doc_results for w in r.warnings]
        all_missing = [m for r in doc_results for m in r.missing_sections]
        all_hallucinations = [h for r in doc_results for h in r.hallucinations]

        per_doc_scores = {
            r.document_type: round(
                (r.completeness_score + r.accuracy_score + r.formatting_score) / 3, 1
            )
            for r in doc_results
        }

        report = ValidationReport(
            validation_status=status,
            quality_score=overall_score,
            errors=all_errors,
            warnings=all_warnings,
            missing_sections=all_missing,
            hallucination_findings=all_hallucinations,
            per_document_scores=per_doc_scores,
            timestamp=_now(),
        )
        shared_memory.validation = report

        duration = time.monotonic() - start
        logger.info(
            "Validation report generated: status=%s  score=%.1f  duration=%.2fs",
            status, overall_score, duration,
        )
        logger.info("Validation completed: %s", repo_name)

        return AgentResult(
            success=True,
            message=f"Validation completed: {status}  score={overall_score:.1f}",
            execution_time=duration,
            warnings=all_warnings,
            errors=all_errors,
        )

    # ------------------------------------------------------------------
    # Rule-based structural validation (no LLM)
    # ------------------------------------------------------------------

    def _validate_structure(self, file_path: str, content: str) -> DocumentValidationResult:
        """Validate a per-file document's structure without using an LLM.

        Checks:
        - Content is not empty.
        - Expected sections are present (Overview, Change Summary, Key Components).
        - Code fences are balanced.
        - No empty headings.

        Args:
            file_path: Relative file path used as the document identifier.
            content:   Markdown content string.

        Returns:
            DocumentValidationResult: Structural validation result.
        """
        result = DocumentValidationResult(document_type=file_path)
        errors: list[str] = []
        warnings: list[str] = []
        missing: list[str] = []

        # Empty content check
        if not content or not content.strip():
            errors.append(f"{file_path}: Document is empty")
            result.errors = errors
            result.formatting_score = 0.0
            result.completeness_score = 0.0
            result.accuracy_score = 0.0
            return result

        # Expected sections
        is_file_doc = file_path.startswith("files/") or "/" in file_path
        if is_file_doc:
            expected = FILE_DOC_EXPECTED_SECTIONS
        else:
            expected = ["## Overview"]

        for section in expected:
            if section.lower() not in content.lower():
                # If ## Overview missing but has any ## section, don't penalize top-level docs
                if not is_file_doc and "## " in content:
                    continue
                missing.append(f"{file_path}: Missing section '{section}'")

        # Balanced code fences
        fence_count = len(re.findall(r"^```", content, re.MULTILINE))
        if fence_count % 2 != 0:
            warnings.append(f"{file_path}: Unbalanced code fences (count={fence_count})")

        # Empty headings
        empty_headings = re.findall(r"^#{1,6}\s*$", content, re.MULTILINE)
        if empty_headings:
            warnings.append(f"{file_path}: {len(empty_headings)} empty heading(s) found")

        # Formatting score
        deductions = len(warnings) * 5 + len(errors) * 15
        formatting_score = max(0.0, 100.0 - deductions)

        # Completeness score based on missing sections
        total_expected = len(FILE_DOC_EXPECTED_SECTIONS)
        completeness_score = max(
            0.0, 100.0 - (len(missing) / total_expected) * 100
        ) if total_expected else 100.0

        result.formatting_score = formatting_score
        result.completeness_score = completeness_score
        result.accuracy_score = 80.0   # Default — updated by LLM validation if available
        result.errors = errors
        result.warnings = warnings
        result.missing_sections = missing
        return result

    # ------------------------------------------------------------------
    # LLM-based content validation
    # ------------------------------------------------------------------

    def _validate_content_with_llm(
        self,
        shared_memory: SharedMemory,
        doc_results: list[DocumentValidationResult],
    ) -> None:
        """Use the LLM to validate content accuracy and detect hallucinations.

        Updates doc_results in-place.

        Args:
            shared_memory: Full shared memory.
            doc_results:   List of structural results to update.
        """
        meta = shared_memory.metadata
        und = shared_memory.understanding
        repo = shared_memory.repository
        docs = shared_memory.documentation.file_docs

        modules_str = ", ".join(m.name for m in und.modules) or "Unknown"
        apis_str = ", ".join(f"{e.method} {e.route}" for e in und.apis) or "None"
        folders_str = ", ".join(und.folder_responsibilities.keys()) or "Unknown"

        for result in doc_results:
            content = docs.get(result.document_type, "")
            if not content:
                continue

            # Truncate large documents to keep prompt manageable
            excerpt = content[:3000]

            prompt = DOCUMENT_VALIDATION_PROMPT.format(
                document_type=result.document_type,
                repository_name=repo.full_name,
                languages=", ".join(ls.language for ls in meta.languages) or "Unknown",
                frameworks=", ".join(meta.frameworks) or "Unknown",
                architecture_type=und.architecture_type,
                modules=modules_str,
                apis=apis_str,
                folders=folders_str,
                document_content=excerpt,
            )

            try:
                raw = self._llm.generate(prompt)
                self._parse_llm_validation(raw, result)
            except Exception as exc:
                logger.warning(
                    "LLM validation failed for %s: %s", result.document_type, exc
                )

    def _parse_llm_validation(
        self, raw: str, result: DocumentValidationResult
    ) -> None:
        """Parse the LLM validation response and update the result in-place.

        Args:
            raw:    Raw LLM response text.
            result: DocumentValidationResult to update.
        """
        def _extract_score(label: str) -> float:
            match = re.search(rf"{label}:\s*(\d+)", raw)
            return float(match.group(1)) if match else result.accuracy_score

        def _extract_list(label: str) -> list[str]:
            match = re.search(rf"{label}:\n(.*?)(?=\n[A-Z_]+:|$)", raw, re.DOTALL)
            if not match:
                return []
            block = match.group(1).strip()
            if block.upper() == "NONE":
                return []
            return [line.strip("- ").strip() for line in block.splitlines() if line.strip()]

        result.accuracy_score = _extract_score("ACCURACY_SCORE")

        llm_errors = _extract_list("ERRORS")
        llm_warnings = _extract_list("WARNINGS")
        llm_missing = _extract_list("MISSING_SECTIONS")
        llm_hallucinations = _extract_list("HALLUCINATIONS")

        result.errors.extend(llm_errors)
        result.warnings.extend(llm_warnings)
        result.missing_sections.extend(llm_missing)
        result.hallucinations.extend(llm_hallucinations)

        summary_match = re.search(r"SUMMARY:\n(.*?)$", raw, re.DOTALL)
        if summary_match:
            result.summary = summary_match.group(1).strip()

    # ------------------------------------------------------------------
    # Score computation
    # ------------------------------------------------------------------

    def _compute_overall_score(
        self, doc_results: list[DocumentValidationResult]
    ) -> float:
        """Compute the weighted overall quality score.

        Args:
            doc_results: Per-document validation results.

        Returns:
            float: Score from 0 to 100, rounded to one decimal place.
        """
        if not doc_results:
            return 0.0

        avg_completeness = sum(r.completeness_score for r in doc_results) / len(doc_results)
        avg_accuracy = sum(r.accuracy_score for r in doc_results) / len(doc_results)
        avg_formatting = sum(r.formatting_score for r in doc_results) / len(doc_results)

        # Readability: inverse of total warnings count (capped)
        total_warnings = sum(len(r.warnings) for r in doc_results)
        readability = max(0.0, 100.0 - total_warnings * 5)

        # Consistency: penalise hallucinations
        total_hallucinations = sum(len(r.hallucinations) for r in doc_results)
        consistency = max(0.0, 100.0 - total_hallucinations * 10)

        score = (
            avg_completeness * WEIGHT_COMPLETENESS
            + avg_accuracy * WEIGHT_ACCURACY
            + consistency * WEIGHT_CONSISTENCY
            + avg_formatting * WEIGHT_MARKDOWN
            + readability * WEIGHT_READABILITY
        )
        return round(min(score, 100.0), 1)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _now() -> str:
    """Return current UTC time as an ISO 8601 string."""
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
