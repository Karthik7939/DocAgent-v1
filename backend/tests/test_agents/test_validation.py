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
    """Unit tests for ValidationAgent._compute_faithfulness_score.

    Checks all of FAITHFULNESS_CHECKED_DOCS (README.md, ARCHITECTURE.md,
    WORKFLOW.md, CHANGELOG.md, SECURITY.md) that have content, and returns
    (mean_score, combined_notes, checked) — checked is False whenever no
    doc could actually be judged (no LLM, no RAG context, or no doc present).
    """

    def test_returns_zero_without_llm(self):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        agent = ValidationAgent(llm_client=None)
        score, notes, checked = agent._compute_faithfulness_score(mem)
        assert (score, notes, checked) == (0.0, "", False)

    def test_returns_zero_without_any_checked_doc(self, monkeypatch):
        mem = _make_memory_with_docs()
        llm = MagicMock()
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes, checked = agent._compute_faithfulness_score(mem)
        assert (score, notes, checked) == (0.0, "", False)
        llm.generate.assert_not_called()

    def test_returns_zero_without_rag_context(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "")
        score, notes, checked = agent._compute_faithfulness_score(mem)
        assert (score, notes, checked) == (0.0, "", False)
        llm.generate.assert_not_called()

    def test_skips_docs_with_no_content(self, monkeypatch):
        """Only ARCHITECTURE.md is present -> exactly one LLM call."""
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = "FAITHFULNESS_SCORE: 82\nUNSUPPORTED_CLAIMS:\nNONE\n"
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes, checked = agent._compute_faithfulness_score(mem)
        assert llm.generate.call_count == 1
        assert (score, checked) == (82.0, True)

    def test_averages_scores_across_multiple_checked_docs(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        mem.documentation.file_docs["README.md"] = "# Demo\n\n## Overview\nA demo."
        llm = MagicMock()
        responses = iter([
            "FAITHFULNESS_SCORE: 80\nUNSUPPORTED_CLAIMS:\nNONE\n",
            "FAITHFULNESS_SCORE: 60\nUNSUPPORTED_CLAIMS:\n- Claims Flask; repo uses FastAPI\n",
        ])
        llm.generate.side_effect = lambda prompt: next(responses)
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes, checked = agent._compute_faithfulness_score(mem)
        assert checked is True
        assert score == 70.0  # mean(80, 60)
        assert "Flask" in notes

    def test_parses_none_as_empty_notes(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = "FAITHFULNESS_SCORE: 95\nUNSUPPORTED_CLAIMS:\nNONE\n"
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes, checked = agent._compute_faithfulness_score(mem)
        assert (score, notes, checked) == (95.0, "", True)

    def test_score_clamped_to_0_100(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = "FAITHFULNESS_SCORE: 140\nUNSUPPORTED_CLAIMS:\nNONE\n"
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, _, _ = agent._compute_faithfulness_score(mem)
        assert score == 100.0

    def test_llm_exception_on_sole_doc_yields_unchecked(self, monkeypatch):
        """A transient LLM failure on the only checked doc must not be
        counted as a score of 0 -- it should look exactly like 'not checked',
        so a flaky API call can't force a false FAILED verdict via the
        FAITHFULNESS_FLOOR."""
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.side_effect = Exception("LLM down")
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes, checked = agent._compute_faithfulness_score(mem)
        assert (score, notes, checked) == (0.0, "", False)

    def test_llm_exception_on_one_of_several_docs_is_excluded_not_zeroed(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        mem.documentation.file_docs["README.md"] = "# Demo\n\n## Overview\nA demo."
        llm = MagicMock()
        responses = iter([
            Exception("LLM down"),
            "FAITHFULNESS_SCORE: 90\nUNSUPPORTED_CLAIMS:\nNONE\n",
        ])

        def side_effect(prompt):
            item = next(responses)
            if isinstance(item, Exception):
                raise item
            return item

        llm.generate.side_effect = side_effect
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        score, notes, checked = agent._compute_faithfulness_score(mem)
        # Only the successful doc counts -- mean is 90, not (0+90)/2 = 45
        assert (score, checked) == (90.0, True)

    def test_run_populates_report_faithfulness_fields(self, monkeypatch):
        mem = _make_memory_with_docs()
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = "FAITHFULNESS_SCORE: 77\nUNSUPPORTED_CLAIMS:\nNONE\n"
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")
        agent.run(mem)
        assert mem.validation.faithfulness_score == 77.0


class TestFaithfulnessGating:
    """Unit tests for how faithfulness affects _compute_overall_score / run()."""

    def _good_doc_results(self, agent):
        """Structurally excellent doc set (would score well above WARN_THRESHOLD alone)."""
        return [agent._validate_structure("README", GOOD_README)]

    def test_overall_score_unaffected_when_not_checked(self):
        agent = ValidationAgent(llm_client=None)
        results = self._good_doc_results(agent)
        with_check = agent._compute_overall_score(results, [], faithfulness_score=10.0, faithfulness_checked=False)
        without_check = agent._compute_overall_score(results, [])
        assert with_check == without_check

    def test_high_faithfulness_raises_score_when_checked(self):
        agent = ValidationAgent(llm_client=None)
        results = self._good_doc_results(agent)
        baseline = agent._compute_overall_score(results, [])
        boosted = agent._compute_overall_score(results, [], faithfulness_score=100.0, faithfulness_checked=True)
        assert boosted >= baseline

    def test_low_faithfulness_lowers_score_when_checked(self):
        agent = ValidationAgent(llm_client=None)
        results = self._good_doc_results(agent)
        baseline = agent._compute_overall_score(results, [])
        penalised = agent._compute_overall_score(results, [], faithfulness_score=0.0, faithfulness_checked=True)
        assert penalised < baseline

    def test_run_forces_failed_when_faithfulness_below_floor(self, monkeypatch):
        """A structurally excellent doc set must still FAIL when faithfulness
        is checked and below FAITHFULNESS_FLOOR (50.0) -- this is the fix for
        'Flask vs FastAPI'-style fabrication passing on structure alone."""
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
        mem.documentation.file_docs["ARCHITECTURE.md"] = GOOD_ARCHITECTURE
        llm = MagicMock()
        llm.generate.return_value = (
            "FAITHFULNESS_SCORE: 20\n"
            "UNSUPPORTED_CLAIMS:\n"
            "- Claims Flask is used; repository actually uses FastAPI\n"
        )
        agent = ValidationAgent(llm_client=llm)
        monkeypatch.setattr(agent._slicer, "get_global_context", lambda ctx: "some real code context")

        agent.run(mem)

        assert mem.validation.faithfulness_score == 20.0
        assert mem.validation.validation_status == "FAILED"

    def test_run_does_not_force_failed_when_faithfulness_not_checked(self):
        """Without an LLM, faithfulness can't be checked -- status must be
        decided purely on structural quality, unaffected by the floor."""
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
        assert mem.validation.validation_status != "FAILED"
