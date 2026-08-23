"""
tests/agents/test_documentation.py
-------------------------------------
Unit tests for agents/documentation/documentation_agent.py
All LLM calls are mocked.
"""

import pytest
from unittest.mock import MagicMock

from agents.documentation.documentation_agent import DocumentationAgent
from agents.memory.shared_memory import (
    SharedMemory, RepositoryInfo, RepositoryMetadata,
    RepositoryUnderstanding, LanguageStat, ModuleInfo, APIEndpoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_populated_memory() -> SharedMemory:
    """Return SharedMemory with understanding and metadata filled."""
    mem = SharedMemory()
    mem.repository = RepositoryInfo(
        name="demo", full_name="Blrm123/demo", path="/tmp/demo",
        branch="main", commit_sha="abc123",
    )
    mem.metadata = RepositoryMetadata(
        languages=[LanguageStat(language="Python", file_count=10, percentage=100.0)],
        frameworks=["FastAPI"],
        dependencies=["fastapi", "uvicorn"],
        directory_tree="demo/\n├── app/\n└── tests/",
    )
    mem.understanding = RepositoryUnderstanding(
        project_summary="A webhook-driven documentation generator.",
        project_purpose="Automates documentation from code.",
        architecture_type="Layered Architecture",
        modules=[ModuleInfo(name="API", responsibility="HTTP handling")],
        apis=[APIEndpoint(method="POST", route="/webhook/github", purpose="Receive webhook")],
        data_flow=["GitHub → Webhook → Parser → Coordinator"],
        folder_responsibilities={"app": "FastAPI layer", "services": "Business logic"},
    )
    return mem


def _make_llm_client(response: str = "# Generated Document\n\n## Overview\n\nContent here."):
    """Return a mock LLM client that returns the given response for every call."""
    client = MagicMock()
    client.generate.return_value = response
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDocumentationAgent:

    def test_run_success(self):
        """Agent returns success when LLM generates all documents."""
        mem = _make_populated_memory()
        llm = _make_llm_client()
        agent = DocumentationAgent(llm_client=llm)
        result = agent.run(mem)
        assert result.success is True

    def test_run_fails_without_understanding(self):
        """Agent fails if understanding section is empty."""
        mem = SharedMemory()
        mem.repository = RepositoryInfo(name="demo", full_name="Blrm123/demo")
        llm = _make_llm_client()
        agent = DocumentationAgent(llm_client=llm)
        result = agent.run(mem)
        assert result.success is False
        assert result.recoverable is False

    def test_all_documents_generated(self):
        """SharedMemory.documentation has all 8 documents after run."""
        mem = _make_populated_memory()
        llm = _make_llm_client()
        agent = DocumentationAgent(llm_client=llm)
        agent.run(mem)
        docs = mem.documentation.all_documents()
        assert len(docs) == 8

    def test_readme_content_set(self):
        """README content is a non-empty string."""
        mem = _make_populated_memory()
        agent = DocumentationAgent(llm_client=_make_llm_client())
        agent.run(mem)
        assert len(mem.documentation.readme) > 0

    def test_llm_called_eight_times(self):
        """LLM generate() is called once per document type."""
        mem = _make_populated_memory()
        llm = _make_llm_client()
        agent = DocumentationAgent(llm_client=llm)
        agent.run(mem)
        assert llm.generate.call_count == 8

    def test_generator_failure_produces_warning_not_crash(self):
        """A failing generator produces a warning but the agent still returns success."""
        mem = _make_populated_memory()
        llm = MagicMock()
        llm.generate.side_effect = Exception("LLM error")
        agent = DocumentationAgent(llm_client=llm)
        result = agent.run(mem)
        assert result.success is True
        assert len(result.warnings) > 0

    def test_generator_failure_sets_placeholder(self):
        """A failing generator sets a placeholder string, not empty string."""
        mem = _make_populated_memory()
        llm = MagicMock()
        llm.generate.side_effect = Exception("LLM error")
        agent = DocumentationAgent(llm_client=llm)
        agent.run(mem)
        # all_documents() should still return 8 entries (placeholder text counts)
        docs = mem.documentation.all_documents()
        assert len(docs) == 8
