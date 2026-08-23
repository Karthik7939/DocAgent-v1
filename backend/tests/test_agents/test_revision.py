"""
tests/agents/test_revision.py
--------------------------------
Unit tests for agents/revision/revision_agent.py
"""

import pytest
from unittest.mock import MagicMock

from agents.revision.revision_agent import RevisionAgent
from agents.memory.shared_memory import (
    SharedMemory, RepositoryInfo, GeneratedDocumentation, ValidationReport,
)

BROKEN_DOC = "# README\n\n## Overview\n\n```python\ncode\n"  # unbalanced fence
FIXED_DOC = "# README\n\n## Overview\n\n```python\ncode\n```"


def _make_memory(status: str = "PASSED_WITH_WARNINGS", score: float = 65.0) -> SharedMemory:
    mem = SharedMemory()
    mem.repository = RepositoryInfo(name="demo", full_name="Blrm123/demo")
    mem.documentation = GeneratedDocumentation(
        readme=BROKEN_DOC,
        architecture="# Architecture\n\n## Overview\nOK.",
    )
    mem.validation = ValidationReport(
        validation_status=status,
        quality_score=score,
        errors=["README: Missing section '## Installation'"],
        warnings=["README: Unbalanced code fences (count=1)"],
    )
    return mem


class TestRevisionAgent:

    def test_run_returns_success(self):
        """Revision agent returns success after revision."""
        mem = _make_memory()
        agent = RevisionAgent(llm_client=None)
        result = agent.run(mem)
        assert result.success is True

    def test_skip_if_already_passed(self):
        """Agent skips revision if validation already passed."""
        mem = _make_memory(status="PASSED", score=90.0)
        agent = RevisionAgent(llm_client=None)
        result = agent.run(mem)
        assert result.success is True
        assert "skipped" in result.message.lower()

    def test_fails_without_validation_report(self):
        """Agent fails if no validation report is in shared memory."""
        mem = SharedMemory()
        mem.repository = RepositoryInfo(name="demo")
        agent = RevisionAgent(llm_client=None)
        result = agent.run(mem)
        assert result.success is False

    def test_revision_count_incremented(self):
        """Revision count in shared memory is incremented after run."""
        mem = _make_memory()
        assert mem.revision.revision_count == 0
        agent = RevisionAgent(llm_client=None)
        agent.run(mem)
        assert mem.revision.revision_count == 1

    def test_revision_history_appended(self):
        """A revision record is appended to revision history."""
        mem = _make_memory()
        agent = RevisionAgent(llm_client=None)
        agent.run(mem)
        assert len(mem.revision.records) == 1
        record = mem.revision.records[0]
        assert record.revision_number == 1
        assert record.timestamp != ""

    def test_rule_based_fence_fix_applied(self):
        """Unbalanced code fence in README is fixed by rule-based correction."""
        mem = _make_memory()
        agent = RevisionAgent(llm_client=None)
        agent.run(mem)
        # After rule-based fix, fence count should be even
        import re
        fence_count = len(re.findall(r"^```", mem.documentation.readme, re.MULTILINE))
        assert fence_count % 2 == 0

    def test_last_revision_timestamp_set(self):
        """Last revision timestamp is updated after revision."""
        mem = _make_memory()
        agent = RevisionAgent(llm_client=None)
        agent.run(mem)
        assert mem.revision.last_revision_timestamp != ""

    def test_llm_revision_applied(self):
        """When LLM is available, revised content replaces original."""
        mem = _make_memory()
        llm = MagicMock()
        llm.generate.return_value = FIXED_DOC
        agent = RevisionAgent(llm_client=llm)
        agent.run(mem)
        # LLM should have been called for the README (has errors)
        assert llm.generate.called
