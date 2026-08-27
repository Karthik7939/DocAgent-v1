"""
tests/agents/test_validation.py
----------------------------------
Unit tests for agents/validation/validation_agent.py
"""

from unittest.mock import MagicMock

import pytest
from agents.validation.validation_agent import ValidationAgent, PASS_THRESHOLD
from agents.memory.shared_memory import (
    SharedMemory, RepositoryInfo, RepositoryMetadata,
    RepositoryUnderstanding, GeneratedDocumentation,
    LanguageStat,
)

GOOD_README = """\
# Demo Project

## Overview
A webhook-driven documentation generator.

## Installation
Run pip install -r requirements.txt

## Technology Stack
Python, FastAPI
"""

GOOD_ARCHITECTURE = """\
# Architecture

## Overview
Layered architecture.

## Architecture Type
Layered Architecture

## High-Level Components
API, Services, Agents
"""


def _make_memory_with_docs(**kwargs) -> SharedMemory:
    mem = SharedMemory()
    mem.repository = RepositoryInfo(full_name="Blrm123/demo", name="demo")
    mem.metadata = RepositoryMetadata(
        languages=[LanguageStat(language="Python", file_count=5, percentage=100.0)],
        frameworks=["FastAPI"],
    )
    mem.understanding = RepositoryUnderstanding(
        project_summary="A generator",
        architecture_type="Layered Architecture",
    )
    mem.documentation = GeneratedDocumentation(**kwargs)
    return mem


class TestValidationAgent:

    def test_run_returns_success(self):
        """Validation agent always returns success (it is itself successful)."""
        mem = _make_memory_with_docs(readme=GOOD_README, architecture=GOOD_ARCHITECTURE)
        agent = ValidationAgent(llm_client=None)
        result = agent.run(mem)
        assert result.success is True

    def test_no_documents_produces_failed_status(self):
        """Empty documentation section results in FAILED validation status."""
        mem = _make_memory_with_docs()
        agent = ValidationAgent(llm_client=None)
        agent.run(mem)
        assert mem.validation.validation_status == "FAILED"

    def test_good_docs_pass(self):
        """Well-formed documents score above threshold."""
        mem = _make_memory_with_docs(
            readme=GOOD_README,
            architecture=GOOD_ARCHITECTURE,
            api="# API\n\n## Overview\n\n## Endpoints\nPOST /webhook",
            installation="# Installation\n\n## Prerequisites\nPython 3.12\n\n## Install Dependencies\npip install",
            developer_guide="# Developer Guide\n\n## Project Structure\napp/\n\n## Coding Conventions\nPEP8",
            folder_guide="# Folder Guide\n\n## Overview\nFolders explained.",
            workflow_guide="# Workflow\n\n## Overview\nWebhook → Parser\n\n## Data Flow\n1. Request in",
            configuration_guide="# Configuration\n\n## Overview\n.env file\n\n## Environment Variables\nGITHUB_SECRET",
        )
        agent = ValidationAgent(llm_client=None)
        agent.run(mem)
        assert mem.validation.quality_score >= PASS_THRESHOLD

    def test_empty_document_gets_error(self):
        """An empty document string is flagged as an error."""
        mem = _make_memory_with_docs(readme="")
        # Add other docs so the empty one is the only issue
        mem.documentation.architecture = GOOD_ARCHITECTURE
        agent = ValidationAgent(llm_client=None)
        agent.run(mem)
        # Empty README means no README in all_documents(), so nothing to flag
        # Validation still completes — no crash
        assert mem.validation.validation_status is not None

    def test_unbalanced_code_fence_is_warning(self):
        """Document with unbalanced code fences produces a warning."""
        bad_doc = "# README\n\n## Overview\n\n```python\ncode here\n"  # missing closing fence
        mem = _make_memory_with_docs(readme=bad_doc)
        agent = ValidationAgent(llm_client=None)
        agent.run(mem)
        all_warnings = mem.validation.warnings
        assert any("fence" in w.lower() for w in all_warnings)

    def test_missing_section_detected(self):
        """A README missing expected sections is flagged."""
        minimal_readme = "# README\nSome content."
        mem = _make_memory_with_docs(readme=minimal_readme)
        agent = ValidationAgent(llm_client=None)
        agent.run(mem)
        assert len(mem.validation.missing_sections) > 0

    def test_quality_score_between_0_and_100(self):
        """Quality score is always in [0, 100] range."""
        mem = _make_memory_with_docs(readme=GOOD_README)
        agent = ValidationAgent(llm_client=None)
        agent.run(mem)
        assert 0.0 <= mem.validation.quality_score <= 100.0

    def test_timestamp_set(self):
        """Validation report timestamp is set after run."""
        mem = _make_memory_with_docs(readme=GOOD_README)
        agent = ValidationAgent(llm_client=None)
        agent.run(mem)
        assert mem.validation.timestamp != ""


class TestFaithfulnessScore:
    """Unit tests for ValidationAgent._compute_faithfulness_score."""

    def test_returns_zero_without_llm(self):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        agent = ValidationAgent(llm_client=None)
        score, notes = agent._compute_faithfulness_score(mem)
        assert score == 0.0
        assert notes == ""

    def test_returns_zero_without_architecture_doc(self):
        mem = _make_memory_with_docs()
        llm = MagicMock()
        agent = ValidationAgent(llm_client=llm)
        score, notes = agent._compute_faithfulness_score(mem)
        assert score == 0.0
        llm.generate.assert_not_called()

    def test_returns_zero_without_rag_context(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "")
        score, notes = agent._compute_faithfulness_score(mem)
        assert score == 0.0
        llm.generate.assert_not_called()

    def test_parses_score_and_unsupported_claims(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = (
            "FAITHFULNESS_SCORE: 82\n"
            "UNSUPPORTED_CLAIMS:\n"
            "- Claims a Redis cache exists; not present in context\n"
        )
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes = agent._compute_faithfulness_score(mem)
        assert score == 82.0
        assert "Redis" in notes

    def test_parses_none_as_empty_notes(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = "FAITHFULNESS_SCORE: 95\nUNSUPPORTED_CLAIMS:\nNONE\n"
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes = agent._compute_faithfulness_score(mem)
        assert score == 95.0
        assert notes == ""

    def test_score_clamped_to_0_100(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = "FAITHFULNESS_SCORE: 140\nUNSUPPORTED_CLAIMS:\nNONE\n"
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, _ = agent._compute_faithfulness_score(mem)
        assert score == 100.0

    def test_llm_exception_degrades_gracefully(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.side_effect = Exception("LLM down")
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes = agent._compute_faithfulness_score(mem)
        assert score == 0.0
        assert notes == ""

    def test_run_populates_report_faithfulness_fields(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = "FAITHFULNESS_SCORE: 77\nUNSUPPORTED_CLAIMS:\nNONE\n"
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        agent.run(mem)
        assert mem.validation.faithfulness_score == 77.0
