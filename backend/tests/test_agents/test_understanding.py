"""
tests/agents/test_understanding.py
-------------------------------------
Unit tests for agents/understanding/understanding_agent.py
All LLM and RAG calls are mocked.
"""

import pytest
from unittest.mock import MagicMock, patch

from agents.understanding.understanding_agent import UnderstandingAgent
from agents.memory.shared_memory import SharedMemory, RepositoryInfo, RepositoryMetadata, LanguageStat
from services.rag_service import RAGService, _RetrievalResult as RetrievalResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_RESPONSE = """\
PROJECT_SUMMARY:
A webhook-driven documentation generator.

PROJECT_PURPOSE:
Generates documentation from GitHub repositories automatically.

ARCHITECTURE_TYPE:
Layered Architecture

MODULES:
API | Handles HTTP endpoints | Services
Services | Business logic | Utils

SERVICES:
WebhookService | Process GitHub events | Payload | Repository data

DATA_FLOW:
GitHub -> Webhook -> Git Service -> Parser -> Coordinator

CODING_STYLE:
Python type hints used. Clear layer separation.
"""

API_RESPONSE = """\
POST | /webhook/github | Receive GitHub webhook | WebhookPayload | WebhookResponse
GET | /health | Health check | None | HealthResponse
"""

FOLDER_RESPONSE = """\
app | FastAPI application layer | main.py, routes | Services
services | Business logic | github_service.py | app
"""

DEP_RESPONSE = """\
API -> Services
Services -> Utils
"""


def _make_shared_memory(repo_path: str = "repositories/test") -> SharedMemory:
    mem = SharedMemory()
    mem.repository = RepositoryInfo(
        name="demo", full_name="Blrm123/demo", path=repo_path, branch="main"
    )
    mem.metadata = RepositoryMetadata(
        languages=[LanguageStat(language="Python", file_count=10, percentage=100.0)],
        frameworks=["FastAPI"],
        directory_tree="demo/\n└── app/",
    )
    return mem


def _make_agent(llm_responses: list[str], indexed: bool = True):
    """Build an UnderstandingAgent with mocked RAG and LLM."""
    rag = MagicMock(spec=RAGService)
    rag.index_repository.return_value = MagicMock(total_files=5, total_chunks=20)
    rag.retrieve.return_value = RetrievalResult(
        query="test", chunks=[], context="mock context"
    )

    llm = MagicMock()
    llm.generate.side_effect = llm_responses

    return UnderstandingAgent(rag_service=rag, llm_client=llm)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUnderstandingAgent:

    def test_run_success(self, tmp_path):
        """Agent returns success when RAG and LLM work correctly."""
        mem = _make_shared_memory(str(tmp_path))
        # Create at least one file so RAG can index
        (tmp_path / "main.py").write_text("from fastapi import FastAPI")

        agent = _make_agent([PROJECT_RESPONSE, API_RESPONSE, FOLDER_RESPONSE, DEP_RESPONSE])
        result = agent.run(mem)
        assert result.success is True

    def test_run_empty_path_returns_failure(self):
        """Agent fails immediately if repository path is empty."""
        mem = SharedMemory()
        mem.repository = RepositoryInfo(path="")
        agent = _make_agent([])
        result = agent.run(mem)
        assert result.success is False
        assert result.recoverable is False

    def test_project_summary_populated(self, tmp_path):
        """Understanding section has project_summary after run."""
        mem = _make_shared_memory(str(tmp_path))
        agent = _make_agent([PROJECT_RESPONSE, API_RESPONSE, FOLDER_RESPONSE, DEP_RESPONSE])
        agent.run(mem)
        assert "documentation generator" in mem.understanding.project_summary.lower()

    def test_architecture_type_extracted(self, tmp_path):
        """Architecture type is parsed from structured LLM response."""
        mem = _make_shared_memory(str(tmp_path))
        agent = _make_agent([PROJECT_RESPONSE, API_RESPONSE, FOLDER_RESPONSE, DEP_RESPONSE])
        agent.run(mem)
        assert mem.understanding.architecture_type == "Layered Architecture"

    def test_apis_parsed(self, tmp_path):
        """API endpoints are parsed from API_DISCOVERY response."""
        mem = _make_shared_memory(str(tmp_path))
        agent = _make_agent([PROJECT_RESPONSE, API_RESPONSE, FOLDER_RESPONSE, DEP_RESPONSE])
        agent.run(mem)
        assert len(mem.understanding.apis) == 2
        assert mem.understanding.apis[0].method == "POST"
        assert mem.understanding.apis[0].route == "/webhook/github"

    def test_modules_parsed(self, tmp_path):
        """Modules are parsed from project understanding response."""
        mem = _make_shared_memory(str(tmp_path))
        agent = _make_agent([PROJECT_RESPONSE, API_RESPONSE, FOLDER_RESPONSE, DEP_RESPONSE])
        agent.run(mem)
        module_names = [m.name for m in mem.understanding.modules]
        assert "API" in module_names

    def test_dependency_graph_parsed(self, tmp_path):
        """Dependency graph is parsed from DEPENDENCY_GRAPH response."""
        mem = _make_shared_memory(str(tmp_path))
        agent = _make_agent([PROJECT_RESPONSE, API_RESPONSE, FOLDER_RESPONSE, DEP_RESPONSE])
        agent.run(mem)
        assert "API" in mem.understanding.dependency_graph

    def test_llm_failure_returns_recoverable_error(self, tmp_path):
        """RuntimeError from LLM results in a recoverable AgentResult failure."""
        mem = _make_shared_memory(str(tmp_path))
        rag = MagicMock(spec=RAGService)
        rag.index_repository.return_value = MagicMock()
        rag.retrieve.return_value = RetrievalResult(query="q", chunks=[], context="ctx")

        llm = MagicMock()
        llm.generate.side_effect = Exception("LLM timeout")

        agent = UnderstandingAgent(rag_service=rag, llm_client=llm)
        result = agent.run(mem)
        assert result.success is False
        assert result.recoverable is True
